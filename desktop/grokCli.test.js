const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { EventEmitter } = require('node:events')
const test = require('node:test')
const grok = require('./grokCli')

function fakeChild() {
  const child = new EventEmitter()
  child.stdout = new EventEmitter()
  child.stderr = new EventEmitter()
  child.stdin = { write() {}, end() {} }
  child.pid = 77
  child.kill = () => {
    child.killed = true
    process.nextTick(() => child.emit('close', null))
  }
  return child
}

test('detection states are not installed, not signed in, and ready', () => {
  assert.equal(grok.classifyDetection({ versionError: 'ENOENT' }).state, 'not_installed')
  assert.equal(grok.classifyDetection({ versionCode: 0, authMethods: [] }).state, 'not_signed_in')
  assert.equal(
    grok.classifyDetection({ versionCode: 0, authMethods: [{ id: 'xai.api_key' }] }).state,
    'not_signed_in',
  )
  assert.equal(
    grok.classifyDetection({ versionCode: 0, authMethods: [{ id: 'cached_token' }] }).state,
    'ready',
  )
  assert.equal(
    grok.classifyDetection({ versionCode: 0, probeError: 'Sign-in check timed out.' }).state,
    'unknown',
  )
  assert.equal(grok.classifyDetection({ versionCode: 0, authMethods: null }).state, 'unknown')
})

test('detect strips the API key and reads cached_token from initialize', async () => {
  let seenEnv = null
  const spawn = (cmd, args, opts) => {
    const child = fakeChild()
    seenEnv = opts.env
    if (args[0] === 'version') {
      process.nextTick(() => child.emit('close', 0))
      return child
    }
    assert.deepEqual(args, ['agent', 'stdio'])
    child.stdin.write = (data) => {
      const message = JSON.parse(String(data).trim())
      assert.equal(message.method, 'initialize')
      process.nextTick(() => {
        child.stdout.emit('data', `${JSON.stringify({
          jsonrpc: '2.0',
          id: 1,
          result: { authMethods: [{ id: 'cached_token' }] },
        })}\n`)
      })
    }
    return child
  }
  const result = await grok.detectGrok({ spawn, env: { PATH: '/usr/bin', XAI_API_KEY: 'secret-value' } })
  assert.equal(result.state, 'ready')
  assert.equal(seenEnv.XAI_API_KEY, undefined)
  assert.equal(JSON.stringify(seenEnv).includes('secret-value'), false)
})

test('a missing grok binary is not installed', async () => {
  const spawn = () => {
    const err = new Error('spawn grok ENOENT')
    err.code = 'ENOENT'
    throw err
  }
  const result = await grok.detectGrok({ spawn })
  assert.equal(result.state, 'not_installed')
})

test('headless argv uses verified flags and drops tool approval', () => {
  const argv = grok.headlessArgv({ cwd: '/tmp/empty', prompt: 'How is the cloak?' })
  for (const flag of grok.VERIFIED_HEADLESS_FLAGS) assert.ok(argv.includes(flag), flag)
  for (const flag of grok.FORBIDDEN_FLAGS) assert.equal(argv.includes(flag), false, flag)
  assert.equal(argv[argv.indexOf('--sandbox') + 1], 'read-only')
  assert.equal(argv[argv.indexOf('--permission-mode') + 1], 'dontAsk')
  assert.equal(argv[argv.indexOf('--output-format') + 1], 'json')
  assert.equal(argv[argv.indexOf('--max-turns') + 1], String(grok.MAX_TURNS))
  assert.equal(argv[argv.indexOf('--cwd') + 1], '/tmp/empty')
  assert.equal(argv.includes('--allow'), false)
})

test('headless prompt drops chat lines', () => {
  const prompt = [
    'View: Parser',
    "Jenann told you, 'Attacking a rat Master.'",
    "Jaber says, 'Following you, Master.'",
    'You told Mote, \'hello\'',
    'Someone tells the guild, \'raid\'',
    'Someone tells the group, \'pull\'',
    'Cloak of Flames',
  ].join('\n')
  const prepared = grok.prepareHeadless(prompt)
  assert.equal(prepared.ok, true)
  assert.equal(prepared.prompt.includes('told you'), false)
  assert.equal(prepared.prompt.includes('says,'), false)
  assert.equal(prepared.prompt.includes('tells the guild'), false)
  assert.equal(prepared.prompt.includes('tells the group'), false)
  assert.match(prepared.prompt, /Cloak of Flames/)
})

test('quota, eligibility, and auth errors fall back to copy', () => {
  const quota = grok.classifyRunError({ code: 1, stderr: 'quota exceeded for this account', stdout: '' })
  assert.equal(quota.kind, 'quota')
  assert.equal(quota.fallbackCopy, true)
  assert.match(quota.friendly, /quota/i)
  const eligibility = grok.classifyRunError({ code: 1, stderr: 'not eligible for grok', stdout: '' })
  assert.equal(eligibility.kind, 'eligibility')
  assert.equal(eligibility.fallbackCopy, true)
  const auth = grok.classifyRunError({ code: 1, stderr: 'Run `grok login` first', stdout: '' })
  assert.equal(auth.kind, 'auth')
  assert.equal(auth.fallbackCopy, true)
  assert.equal(grok.redactSecrets('Authorization: Bearer super-secret').includes('super-secret'), false)
})

test('json output keeps sessionId and does not invent an answer field', () => {
  const parsed = grok.parseHeadlessStdout('log line\n{"sessionId":"abc","mystery":"hello"}')
  assert.equal(parsed.ok, true)
  assert.equal(parsed.sessionId, 'abc')
  assert.equal(parsed.answerField, 'unknown')
  assert.equal(parsed.result, undefined)
  assert.match(parsed.raw, /mystery/)
})

test('installer runs only after confirm and uses the documented command', () => {
  let calls = 0
  const spawn = () => {
    calls += 1
    return fakeChild()
  }
  const refused = grok.startInstall({ spawn, confirmed: false, platform: 'win32' })
  assert.equal(refused.started, false)
  assert.equal(calls, 0)
  const win = grok.installSpec('win32')
  assert.equal(win.command, 'irm https://x.ai/cli/install.ps1 | iex')
  const started = grok.startInstall({ spawn, confirmed: true, platform: 'win32', env: { XAI_API_KEY: 'secret-value' } })
  assert.equal(started.started, true)
  assert.equal(started.command, win.command)
  assert.equal(calls, 1)
  const unix = grok.installSpec('linux')
  assert.equal(unix.command, 'curl -fsSL https://x.ai/cli/install.sh | bash')
})

test('sign-in launches grok login and does not pass an API key', () => {
  let args = null
  let env = null
  const spawn = (cmd, argv, opts) => {
    args = [cmd, ...argv]
    env = opts.env
    return fakeChild()
  }
  const started = grok.startLogin({ spawn, env: { PATH: '/bin', XAI_API_KEY: 'secret-value' } })
  assert.deepEqual(args, ['grok', 'login'])
  assert.equal(env.XAI_API_KEY, undefined)
  assert.match(started.detail, /own account/)
})

test('timeout and cancel stop the run and fall back to copy', async () => {
  const spawn = () => fakeChild()
  const timed = grok.startHeadless({ spawn, prompt: 'How is the cloak?', timeoutMs: 30, cwd: '/tmp' })
  const timeoutResult = await timed.done
  assert.equal(timeoutResult.kind, 'timeout')
  assert.equal(timeoutResult.fallbackCopy, true)

  const hanging = grok.startHeadless({ spawn, prompt: 'How is the cloak?', timeoutMs: 5000, cwd: '/tmp' })
  hanging.cancel()
  const cancelled = await hanging.done
  assert.equal(cancelled.kind, 'cancelled')
  assert.equal(cancelled.fallbackCopy, true)
})

test('desktop shell exposes Ask AI without touching the updater', () => {
  const main = fs.readFileSync(path.join(__dirname, 'main.js'), 'utf8')
  const preload = fs.readFileSync(path.join(__dirname, 'preload.js'), 'utf8')
  const pkg = require('./package.json')
  assert.match(main, /eq:grok-status/)
  assert.match(main, /eq:grok-install/)
  assert.match(main, /eq:grok-login/)
  assert.match(main, /eq:grok-ask/)
  assert.match(main, /eq:grok-cancel/)
  assert.match(main, /grokCli\.stopAll\(spawn\)/)
  assert.match(preload, /grokStatus/)
  assert.match(preload, /grokInstall/)
  assert.match(preload, /askGrok/)
  assert.match(preload, /cancelGrok/)
  assert.ok(pkg.build.files.includes('grokCli.js'))
  assert.match(main, /electron-updater/)
})

test('a pack that is too long for -p is not sent', async () => {
  let calls = 0
  const spawn = () => {
    calls += 1
    return fakeChild()
  }
  const handle = grok.startHeadless({ spawn, prompt: 'A'.repeat(grok.PROMPT_ARGV_MAX + 1) })
  const result = await handle.done
  assert.equal(result.kind, 'too-long')
  assert.equal(result.fallbackCopy, true)
  assert.equal(calls, 0)
})
