/**
 * Optional local Grok CLI.
 *
 * The app never reads Grok's credential file, never stores a token, and never
 * sends one. A paid API key in the environment is removed before the
 * command runs, so only an account the user already signed in with can
 * answer. Anything else falls back to the browser.
 */

const { execFile } = require('child_process')
const os = require('os')

const SECRET_ENV = [
  'XAI_API_KEY',
  'GROK_CODE_XAI_API_KEY',
  'GROK_DEPLOYMENT_KEY',
  'GROK_AUTH_PROVIDER_ACCESS_TOKEN',
  'GROK_AUTH_PROVIDER_REFRESH_TOKEN',
]

const DISALLOWED_TOOLS = [
  'run_terminal_cmd',
  'grep',
  'read_file',
  'search_replace',
  'list_dir',
  'web_search',
  'web_fetch',
  'todo_write',
  'task',
  'Agent',
].join(',')

const SIGNED_OUT = /not signed in|sign in|grok login|no credentials|unauthorized|please log ?in|authentication required/i

function strippedEnv(base) {
  const env = { ...(base || {}) }
  for (const key of Object.keys(env)) {
    if (SECRET_ENV.includes(key) || /TOKEN|SECRET|API_KEY|PASSWORD|AUTHORIZATION/i.test(key)) {
      delete env[key]
    }
  }
  return env
}

function safeBin(bin) {
  const text = String(bin || '').trim()
  if (!text || text.length > 400 || /[\r\n\0]/.test(text)) return null
  if (!/(?:^|[\\/])grok(?:\.exe|\.cmd)?$/i.test(text)) return null
  return text
}

function looksSignedOut(text) {
  return SIGNED_OUT.test(String(text || ''))
}

function scrubSecrets(text) {
  return String(text || '')
    .replace(/Bearer\s+\S+/gi, 'Bearer [redacted]')
    .replace(/\bxai-[A-Za-z0-9_-]{8,}\b/g, '[redacted]')
    .replace(/"(?:access_token|refresh_token|id_token)"\s*:\s*"[^"]*"/gi, '"token":"[redacted]"')
}

function parseAnswer(stdout) {
  const raw = String(stdout || '').trim()
  if (!raw || looksSignedOut(raw)) return ''
  const candidates = [raw]
  const last = raw.lastIndexOf('\n{')
  if (last >= 0) candidates.push(raw.slice(last + 1))
  const brace = raw.indexOf('{')
  if (brace > 0) candidates.push(raw.slice(brace))
  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate)
      if (parsed && typeof parsed.text === 'string' && parsed.text.trim()) {
        return scrubSecrets(parsed.text).trim()
      }
    } catch (_) {
      /* plain text is the other documented format */
    }
  }
  if (/access_token|refresh_token|authorization:/i.test(raw)) return ''
  return scrubSecrets(raw).trim()
}

function askArgs() {
  return [
    '-p',
    'Answer the question on stdin. Use only the facts written there. If a stat, number, or rule is not written there, say it is unknown. Do not invent item stats.',
    '--output-format', 'json',
    '--permission-mode', 'dontAsk',
    '--max-turns', '1',
    '--disallowed-tools', DISALLOWED_TOOLS,
    '--disable-web-search',
    '--no-memory',
    '--no-plan',
    '--no-subagents',
    '--cwd', os.tmpdir(),
  ]
}

function defaultWhich(name) {
  return new Promise((resolve) => {
    const cmd = process.platform === 'win32' ? 'where' : 'which'
    execFile(cmd, [name], { timeout: 4000, windowsHide: true }, (err, stdout) => {
      if (err) return resolve(null)
      const lines = String(stdout || '').split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
      resolve(safeBin(lines[0]))
    })
  })
}

function defaultRun(bin, args, options) {
  return new Promise((resolve, reject) => {
    const child = execFile(bin, args, {
      env: options.env,
      timeout: options.timeout,
      windowsHide: true,
      maxBuffer: 1024 * 1024,
      cwd: os.tmpdir(),
    }, (err, stdout, stderr) => {
      if (err && (err.killed || err.signal)) {
        reject(err)
        return
      }
      const code = err && typeof err.code === 'number' ? err.code : (err ? 1 : 0)
      resolve({
        code,
        stdout: String(stdout || ''),
        stderr: String(stderr || ''),
      })
    })
    if (child && child.stdin) child.stdin.end(options.input || '')
  })
}

async function askWithLocalGrok(prompt, deps = {}) {
  const which = deps.which || defaultWhich
  const run = deps.run || defaultRun
  const env = strippedEnv(deps.env || process.env)
  const bin = safeBin(await which('grok'))
  if (!bin) return { mode: 'browser', reason: 'not-installed' }

  let version
  try {
    version = await run(bin, ['version'], { env, timeout: 8000, input: '' })
  } catch (_) {
    return { mode: 'browser', reason: 'not-installed' }
  }
  if (!version || version.code !== 0) return { mode: 'browser', reason: 'not-installed' }

  let probe
  try {
    probe = await run(bin, ['models'], { env, timeout: 15000, input: '' })
  } catch (_) {
    return { mode: 'browser', reason: 'not-signed-in' }
  }
  const probeText = `${probe && probe.stdout ? probe.stdout : ''}\n${probe && probe.stderr ? probe.stderr : ''}`
  if (!probe || probe.code !== 0 || looksSignedOut(probeText) || !String(probe.stdout || '').trim()) {
    return { mode: 'browser', reason: 'not-signed-in' }
  }

  let answer
  try {
    answer = await run(bin, askArgs(), {
      env,
      timeout: 60000,
      input: String(prompt || ''),
    })
  } catch (_) {
    return { mode: 'browser', reason: 'failed' }
  }
  if (!answer || answer.code !== 0) return { mode: 'browser', reason: 'failed' }
  const text = parseAnswer(answer.stdout)
  if (!text) return { mode: 'browser', reason: 'failed' }
  return { mode: 'answer', text }
}

module.exports = {
  askWithLocalGrok,
  strippedEnv,
  parseAnswer,
  askArgs,
  looksSignedOut,
  safeBin,
  SECRET_ENV,
}
