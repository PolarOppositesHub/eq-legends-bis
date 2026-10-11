const assert = require('node:assert/strict')
const fs = require('fs')
const os = require('os')
const path = require('path')
const test = require('node:test')
const {
  EXCLUSIVE_FULLSCREEN_WARNING,
  eqclientIniPath,
  parseVideoMode,
  readEqClientVideoMode,
} = require('./eqclientIni')

const fullscreenFixture = path.join(__dirname, 'fixtures', 'eqclient-fullscreen.ini')
const windowedFixture = path.join(__dirname, 'fixtures', 'eqclient-windowed.ini')

test('Fullscreen=1 in VideoMode warns and a later section does not', () => {
  const text = fs.readFileSync(fullscreenFixture, 'utf8')
  const parsed = parseVideoMode(text)
  assert.equal(parsed.fullscreen, true)
  assert.equal(parsed.value, '1')
  const windowed = parseVideoMode(fs.readFileSync(windowedFixture, 'utf8'))
  assert.equal(windowed.fullscreen, false)
  assert.equal(windowed.value, '0')
})

test('reading a fixture ini does not write the file', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'eqclient-'))
  const dest = path.join(dir, 'eqclient.ini')
  fs.copyFileSync(fullscreenFixture, dest)
  const before = fs.readFileSync(dest)
  const writes = []
  const fsImpl = {
    readFileSync(file, encoding) {
      assert.equal(file, dest)
      return fs.readFileSync(file, encoding)
    },
    writeFileSync() {
      writes.push('write')
    },
  }
  const result = readEqClientVideoMode(dir, fsImpl)
  assert.equal(writes.length, 0)
  assert.deepEqual(fs.readFileSync(dest), before)
  assert.equal(result.fullscreen, true)
  assert.equal(result.warning, EXCLUSIVE_FULLSCREEN_WARNING)
  assert.match(result.warning, /Alt\+Enter/)
  const quiet = readEqClientVideoMode(path.join(dir, 'missing'))
  assert.equal(quiet.missing, true)
  assert.equal(quiet.warning, '')
  assert.match(eqclientIniPath(''), /EverQuest Legends[\\/]eqclient\.ini$/)
})
