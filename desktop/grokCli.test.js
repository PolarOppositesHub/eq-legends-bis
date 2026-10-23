const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const { askWithLocalGrok, parseAnswer, safeBin, strippedEnv } = require('./grokCli')

test('a missing or unsigned grok command falls back without reading a token', async () => {
  const src = fs.readFileSync(path.join(__dirname, 'grokCli.js'), 'utf8')
  assert.equal(src.includes('auth.json'), false)
  assert.equal(src.includes('readFile'), false)
  const pkg = require('./package.json')
  assert.ok(pkg.build.files.includes('grokCli.js'))

  const calls = []
  const missing = await askWithLocalGrok('What about this cloak?', {
    env: { XAI_API_KEY: 'xai-secretvalue', PATH: '/usr/bin' },
    which: async () => null,
    run: async (...args) => calls.push(args),
  })
  assert.deepEqual(missing, { mode: 'browser', reason: 'not-installed' })
  assert.equal(calls.length, 0)

  const signedOut = await askWithLocalGrok('Question', {
    env: { XAI_API_KEY: 'xai-secretvalue', HOME: '/tmp' },
    which: async () => '/usr/local/bin/grok',
    run: async (bin, args, options) => {
      calls.push({ bin, args, env: options.env, input: options.input })
      if (args[0] === 'version') return { code: 0, stdout: 'grok 0.1.0', stderr: '' }
      return { code: 1, stdout: '', stderr: 'Not signed in. Run grok login.' }
    },
  })
  assert.equal(signedOut.mode, 'browser')
  assert.equal(signedOut.reason, 'not-signed-in')
  assert.equal(calls.some((call) => call.env && call.env.XAI_API_KEY), false)
  assert.equal(JSON.stringify(signedOut).includes('xai-secretvalue'), false)
})

test('a signed-in local grok answers from stdin and the prompt is not a token', async () => {
  const calls = []
  const result = await askWithLocalGrok('Question: is the cloak +10?', {
    env: { XAI_API_KEY: 'xai-secretvalue', SAFE: 'ok' },
    which: async () => '/home/josh/.local/bin/grok',
    run: async (bin, args, options) => {
      calls.push({ bin, args, env: options.env, input: options.input })
      if (args[0] === 'version') return { code: 0, stdout: 'grok 1.0.0', stderr: '' }
      if (args[0] === 'models') return { code: 0, stdout: 'grok-build', stderr: '' }
      return {
        code: 0,
        stdout: JSON.stringify({ text: 'The cloak is listed at Haste 46. Bearer abcdefghijk' }),
        stderr: '',
      }
    },
  })
  assert.equal(result.mode, 'answer')
  assert.match(result.text, /Haste 46/)
  assert.equal(result.text.includes('abcdefghijk'), false)
  const ask = calls.find((call) => call.args[0] === '-p')
  assert.ok(ask)
  assert.equal(ask.input, 'Question: is the cloak +10?')
  assert.equal(ask.args.join(' ').includes('is the cloak'), false)
  assert.equal(ask.env.XAI_API_KEY, undefined)
  assert.equal(ask.env.SAFE, 'ok')
  assert.equal(ask.args.includes('--permission-mode'), true)
  assert.equal(ask.args.includes('dontAsk'), true)
  assert.equal(safeBin('grok'), 'grok')
  assert.equal(safeBin('/usr/bin/not-grok'), null)
  assert.equal(strippedEnv({ XAI_API_KEY: 'x', HOME: '/tmp' }).HOME, '/tmp')
  assert.equal(parseAnswer('{"text":"ok"}'), 'ok')
  assert.equal(parseAnswer('{"access_token":"nope"}'), '')
})
