/**
 * Grok Build CLI helpers for Ask AI.
 *
 * Installer and flags are taken from the docs checked for 1.1.17:
 * - https://docs.x.ai/build/overview
 * - https://docs.x.ai/build/cli/headless-scripting
 * - https://docs.x.ai/build/cli/reference
 * - https://docs.x.ai/build/features/sandbox
 * - https://docs.x.ai/build/features/permissions
 * - https://docs.x.ai/build/enterprise
 * - https://docs.x.ai/build/features/sessions (JSON field sessionId only)
 *
 * The app never reads or stores credentials. XAI_API_KEY is stripped from
 * child environments so a paid API key is not used.
 */

const fs = require('fs')
const os = require('os')
const path = require('path')

/** Same chat needles as backend/tests/test_parser.py _CHAT. */
const CHAT_LINE_NEEDLES = [
  " says, '",
  " say, '",
  " shouts, '",
  " shout, '",
  " auctions, '",
  " auction, '",
  'out of character',
  "told you, '",
  "tells you, '",
  'you told ',
  'tells the guild',
  'tells the group',
  'tells the raid',
]

const SYSTEM_PROMPT = [
  'You answer questions about the player\'s EverQuest Legends gear, parses, and upgrades.',
  'Use only the context in the user prompt. If a number, rule, or item stat is not in that context, say it is unknown.',
  'Do not invent item stats, mob data, log lines, or game rules.',
  'Do not use tools, read files, or write files.',
].join(' ')

/** Our cap, not a CLI limit. -p is the documented way to pass the prompt. */
const PROMPT_ARGV_MAX = 6000
/** Low turn cap. The flag exists; the number is ours. */
const MAX_TURNS = 2
const ASK_TIMEOUT_MS = 90000
const INSTALL_TIMEOUT_MS = 120000
const DETECT_TIMEOUT_MS = 8000

const NOT_INSTALLED = 'Grok Build CLI was not found on PATH.'
const TIMEOUT_TEXT = 'Grok took too long and was stopped. Copy the context and open Grok in the browser.'
const CANCEL_TEXT = 'The Grok run was cancelled. Copy the context and open Grok in the browser.'
const LOGIN_TEXT = 'Grok sign-in started. Finish it in the browser with your own account. This app does not see the password.'

/**
 * Flags verified in the docs above.
 * --tools exists in the CLI reference, but the built-in names it accepts are
 * not listed. --permission-mode dontAsk with no --allow denies every tool
 * (enterprise docs). --tools is not passed.
 */
const VERIFIED_HEADLESS_FLAGS = [
  '--no-auto-update',
  '--no-alt-screen',
  '-p',
  '--output-format',
  '--cwd',
  '--sandbox',
  '--permission-mode',
  '--max-turns',
  '--no-memory',
  '--no-plan',
  '--no-subagents',
  '--disable-web-search',
  '--system-prompt-override',
]

const FORBIDDEN_FLAGS = [
  '--always-approve',
  '--yolo',
  '--dangerously-skip-permissions',
  '--tools',
  '--allow',
  '--experimental-memory',
]

const children = new Set()

function isChatLine(line) {
  const lowered = String(line || '').toLowerCase()
  return CHAT_LINE_NEEDLES.some((needle) => lowered.includes(needle))
}

function scrubChat(text) {
  return String(text || '')
    .split(/\r?\n/)
    .filter((line) => !isChatLine(line))
    .join('\n')
    .trim()
}

function redactSecrets(text) {
  return String(text || '')
    .replace(/Bearer\s+\S+/gi, 'Bearer [redacted]')
    .replace(/(access_token|refresh_token|api_key|XAI_API_KEY)\s*[=:]\s*\S+/gi, '$1=[redacted]')
}

function childEnv(base) {
  const env = { ...(base || {}) }
  delete env.XAI_API_KEY
  return env
}

function installSpec(platform) {
  if (platform === 'win32') {
    return {
      command: 'irm https://x.ai/cli/install.ps1 | iex',
      file: 'powershell.exe',
      args: ['-NoProfile', '-Command', 'irm https://x.ai/cli/install.ps1 | iex'],
    }
  }
  return {
    command: 'curl -fsSL https://x.ai/cli/install.sh | bash',
    file: 'bash',
    args: ['-lc', 'curl -fsSL https://x.ai/cli/install.sh | bash'],
  }
}

function prepareHeadless(prompt) {
  const cleaned = scrubChat(prompt)
  if (!cleaned) {
    return {
      ok: false,
      kind: 'empty',
      friendly: 'The question pack was empty after chat lines were removed. Copy context still works.',
      fallbackCopy: true,
    }
  }
  if (cleaned.length > PROMPT_ARGV_MAX) {
    return {
      ok: false,
      kind: 'too-long',
      friendly: `This pack is longer than ${PROMPT_ARGV_MAX} characters. The CLI\'s documented -p flag is how this app passes it, so the pack was not sent. Copy it and open Grok in the browser.`,
      fallbackCopy: true,
    }
  }
  return { ok: true, prompt: cleaned }
}

function headlessArgv({ cwd, prompt }) {
  return [
    '--no-auto-update',
    '--no-alt-screen',
    '-p', prompt,
    '--output-format', 'json',
    '--cwd', cwd,
    '--sandbox', 'read-only',
    '--permission-mode', 'dontAsk',
    '--max-turns', String(MAX_TURNS),
    '--no-memory',
    '--no-plan',
    '--no-subagents',
    '--disable-web-search',
    '--system-prompt-override', SYSTEM_PROMPT,
  ]
}

function parseHeadlessStdout(stdout) {
  const text = String(stdout || '').trim()
  if (!text) return { ok: false, reason: 'empty', answerField: 'unknown', raw: '' }
  const candidates = [text]
  const lines = text.split(/\r?\n/)
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    if (lines[i].trim().startsWith('{')) {
      candidates.push(lines.slice(i).join('\n').trim())
      break
    }
  }
  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate)
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) continue
      return {
        ok: true,
        sessionId: typeof parsed.sessionId === 'string' ? parsed.sessionId : null,
        answerField: 'unknown',
        raw: JSON.stringify(parsed, null, 2).slice(0, 12000),
      }
    } catch (_) {
      /* The docs say one JSON object at the end. Try the next slice. */
    }
  }
  return {
    ok: false,
    reason: 'not-json',
    answerField: 'unknown',
    raw: redactSecrets(text).slice(0, 4000),
  }
}

function classifyRunError({ code, stderr, stdout }) {
  const blob = redactSecrets(`${stderr || ''}\n${stdout || ''}`)
  if (/run `grok login` first|not signed in|not logged in|unauthorized|authentication/i.test(blob)) {
    return {
      ok: false,
      kind: 'auth',
      friendly: 'Grok is not signed in with your account. Sign in, or copy the context and open Grok in the browser.',
      fallbackCopy: true,
    }
  }
  if (/quota/i.test(blob)) {
    return {
      ok: false,
      kind: 'quota',
      friendly: 'Grok said this account is out of quota. Copy the context and open Grok in the browser. This app does not buy extra usage.',
      fallbackCopy: true,
    }
  }
  if (/eligib/i.test(blob)) {
    return {
      ok: false,
      kind: 'eligibility',
      friendly: 'Grok said this account cannot run that request. Copy the context and open Grok in the browser.',
      fallbackCopy: true,
    }
  }
  const detail = blob.trim().slice(0, 500)
  return {
    ok: false,
    kind: 'error',
    friendly: detail
      ? `Grok stopped (${code == null ? 'no exit code' : `exit ${code}`}). ${detail}`
      : `Grok stopped (${code == null ? 'no exit code' : `exit ${code}`}). Copy the context and open Grok in the browser.`,
    fallbackCopy: true,
  }
}

function stateFromAuthMethods(methods) {
  if (!Array.isArray(methods)) {
    return {
      state: 'unknown',
      detail: 'Sign-in check did not include authMethods. That is the field the CLI docs show on initialize.',
    }
  }
  const ids = methods.map((row) => row && row.id).filter((id) => typeof id === 'string')
  if (ids.includes('cached_token')) {
    return { state: 'ready', detail: 'Signed in with the Grok account saved by the CLI.' }
  }
  return {
    state: 'not_signed_in',
    detail: 'No saved Grok sign-in. An API key is not used.',
  }
}

function classifyDetection({ versionError, versionCode, authMethods, probeError }) {
  if (versionError === 'ENOENT') {
    return { state: 'not_installed', detail: NOT_INSTALLED }
  }
  if (versionCode !== 0) {
    return {
      state: 'unknown',
      detail: 'grok version did not succeed. Sign-in was not checked.',
    }
  }
  if (probeError) {
    return { state: 'unknown', detail: String(probeError) }
  }
  return stateFromAuthMethods(authMethods)
}

function track(child) {
  if (child) children.add(child)
}

function killChild(child, spawnFn) {
  if (!child) return
  if (process.platform === 'win32' && child.pid && spawnFn) {
    try {
      spawnFn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
    } catch (_) { /* the direct kill below still runs */ }
  }
  try { child.kill() } catch (_) { /* already gone */ }
}

function stopAll(spawnFn) {
  for (const child of children) killChild(child, spawnFn)
  children.clear()
}

function runCommand(spawn, args, env) {
  return new Promise((resolve, reject) => {
    let child
    try {
      child = spawn('grok', args, {
        env: childEnv(env || process.env),
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
      })
    } catch (err) {
      reject(err)
      return
    }
    if (!child) {
      reject(Object.assign(new Error('not found'), { code: 'ENOENT' }))
      return
    }
    let stdout = ''
    let stderr = ''
    if (child.stdout) child.stdout.on('data', (chunk) => { stdout += chunk })
    if (child.stderr) child.stderr.on('data', (chunk) => { stderr += chunk })
    child.on('error', reject)
    child.on('close', (code) => resolve({ code, stdout, stderr }))
  })
}

function probeAuthMethods(spawn, env, timeoutMs) {
  return new Promise((resolve, reject) => {
    let child
    try {
      child = spawn('grok', ['agent', 'stdio'], {
        env: childEnv(env || process.env),
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
      })
    } catch (err) {
      reject(err)
      return
    }
    if (!child || !child.stdin || !child.stdout) {
      reject(Object.assign(new Error('not found'), { code: 'ENOENT' }))
      return
    }
    track(child)
    let buf = ''
    let settled = false
    const finish = (err, methods) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      children.delete(child)
      killChild(child, spawn)
      if (err) reject(err)
      else resolve(methods)
    }
    const timer = setTimeout(() => {
      finish(new Error('Sign-in check timed out. The copy button still works.'))
    }, timeoutMs || DETECT_TIMEOUT_MS)
    child.on('error', (err) => finish(err))
    child.stdout.on('data', (chunk) => {
      buf += chunk
      let nl = buf.indexOf('\n')
      while (nl !== -1) {
        const line = buf.slice(0, nl).trim()
        buf = buf.slice(nl + 1)
        nl = buf.indexOf('\n')
        if (!line) continue
        try {
          const message = JSON.parse(line)
          if (message.id === 1 && message.result) {
            finish(null, message.result.authMethods)
            return
          }
          if (message.id === 1 && message.error) {
            finish(new Error('Sign-in check was rejected by the CLI.'))
            return
          }
        } catch (_) { /* wait for a full JSON line */ }
      }
    })
    child.stdin.write(`${JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: {
        protocolVersion: 1,
        clientCapabilities: {
          fs: { readTextFile: true, writeTextFile: true },
          terminal: true,
        },
      },
    })}\n`)
  })
}

async function detectGrok(deps) {
  const spawn = deps && deps.spawn
  if (typeof spawn !== 'function') {
    return { state: 'unknown', detail: 'Sign-in check could not be started.' }
  }
  let version
  try {
    version = await runCommand(spawn, ['version'], deps.env)
  } catch (err) {
    if (err && err.code === 'ENOENT') return classifyDetection({ versionError: 'ENOENT' })
    return { state: 'not_installed', detail: NOT_INSTALLED }
  }
  if (version.code !== 0) return classifyDetection({ versionCode: version.code })
  let authMethods
  let probeError = null
  try {
    authMethods = deps.probe
      ? await deps.probe()
      : await probeAuthMethods(spawn, deps.env, deps.timeoutMs)
  } catch (err) {
    if (err && err.code === 'ENOENT') return classifyDetection({ versionError: 'ENOENT' })
    probeError = (err && err.message) || 'Sign-in check failed.'
  }
  return classifyDetection({ versionCode: 0, authMethods, probeError })
}

function makeEmptyCwd() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'eq-ask-ai-'))
}

function removeCwd(dir) {
  try { fs.rmSync(dir, { recursive: true, force: true }) } catch (_) { /* best effort */ }
}

function startHeadless(deps) {
  const prepared = prepareHeadless(deps && deps.prompt)
  if (!prepared.ok) return { done: Promise.resolve(prepared), cancel() {} }
  const cwd = (deps && deps.cwd) || makeEmptyCwd()
  const owned = !(deps && deps.cwd)
  const argv = headlessArgv({ cwd, prompt: prepared.prompt })
  let child
  try {
    child = deps.spawn('grok', argv, {
      cwd,
      env: childEnv((deps && deps.env) || process.env),
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
  } catch (err) {
    if (owned) removeCwd(cwd)
    const notFound = err && err.code === 'ENOENT'
    return {
      done: Promise.resolve({
        ok: false,
        kind: notFound ? 'not_installed' : 'error',
        friendly: notFound ? NOT_INSTALLED : 'Grok could not be started.',
        fallbackCopy: true,
      }),
      cancel() {},
    }
  }
  if (!child) {
    if (owned) removeCwd(cwd)
    return {
      done: Promise.resolve({ ok: false, kind: 'not_installed', friendly: NOT_INSTALLED, fallbackCopy: true }),
      cancel() {},
    }
  }
  track(child)
  if (deps && typeof deps.track === 'function') deps.track(child)
  let stdout = ''
  let stderr = ''
  if (child.stdout) child.stdout.on('data', (chunk) => { stdout += chunk })
  if (child.stderr) child.stderr.on('data', (chunk) => { stderr += chunk })
  let settled = false
  let mode = ''
  const done = new Promise((resolve) => {
    const finish = (result) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      children.delete(child)
      if (owned) removeCwd(cwd)
      resolve(result)
    }
    child.on('error', (err) => {
      const notFound = err && err.code === 'ENOENT'
      finish({
        ok: false,
        kind: notFound ? 'not_installed' : 'error',
        friendly: notFound ? NOT_INSTALLED : 'Grok could not be started.',
        fallbackCopy: true,
      })
    })
    child.on('close', (code) => {
      if (mode === 'timeout') {
        finish({ ok: false, kind: 'timeout', friendly: TIMEOUT_TEXT, fallbackCopy: true })
        return
      }
      if (mode === 'cancel') {
        finish({ ok: false, kind: 'cancelled', friendly: CANCEL_TEXT, fallbackCopy: true })
        return
      }
      if (code !== 0) {
        finish(classifyRunError({ code, stderr, stdout }))
        return
      }
      const parsed = parseHeadlessStdout(stdout)
      if (!parsed.ok) {
        finish({
          ok: false,
          kind: 'output',
          friendly: 'Grok exited, and the output was not the documented JSON object. The text is shown as returned. The answer field name is not documented.',
          answerField: 'unknown',
          raw: parsed.raw,
          fallbackCopy: true,
        })
        return
      }
      finish({
        ok: true,
        kind: 'ok',
        sessionId: parsed.sessionId,
        answerField: 'unknown',
        raw: parsed.raw,
        fallbackCopy: false,
      })
    })
  })
  const timer = setTimeout(() => {
    mode = 'timeout'
    killChild(child, deps.spawn)
  }, (deps && deps.timeoutMs) || ASK_TIMEOUT_MS)
  return {
    done,
    argv,
    cancel() {
      mode = 'cancel'
      killChild(child, deps.spawn)
    },
  }
}

function startInstall(deps) {
  if (!deps || deps.confirmed !== true) {
    return { ok: false, started: false, detail: 'Installer was not run. Confirm it first.' }
  }
  const spec = installSpec(deps.platform || process.platform)
  let child
  try {
    child = deps.spawn(spec.file, spec.args, {
      env: childEnv(deps.env || process.env),
      windowsHide: false,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
  } catch (err) {
    return { ok: false, started: false, command: spec.command, detail: 'The installer could not be started.' }
  }
  track(child)
  if (typeof deps.track === 'function') deps.track(child)
  return { ok: true, started: true, command: spec.command, child }
}

function startLogin(deps) {
  const child = deps.spawn('grok', ['login'], {
    env: childEnv((deps && deps.env) || process.env),
    windowsHide: false,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  track(child)
  if (deps && typeof deps.track === 'function') deps.track(child)
  return { ok: true, detail: LOGIN_TEXT, child }
}

module.exports = {
  ASK_TIMEOUT_MS,
  CHAT_LINE_NEEDLES,
  DETECT_TIMEOUT_MS,
  FORBIDDEN_FLAGS,
  INSTALL_TIMEOUT_MS,
  LOGIN_TEXT,
  MAX_TURNS,
  NOT_INSTALLED,
  PROMPT_ARGV_MAX,
  SYSTEM_PROMPT,
  VERIFIED_HEADLESS_FLAGS,
  childEnv,
  classifyDetection,
  classifyRunError,
  detectGrok,
  headlessArgv,
  installSpec,
  isChatLine,
  parseHeadlessStdout,
  prepareHeadless,
  probeAuthMethods,
  redactSecrets,
  scrubChat,
  startHeadless,
  startInstall,
  startLogin,
  stateFromAuthMethods,
  stopAll,
}
