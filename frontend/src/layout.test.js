import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'styles.css'), 'utf8')

function rule(selector) {
  const start = css.indexOf(selector)
  assert.notEqual(start, -1, selector)
  return css.slice(start, css.indexOf('}', start))
}

test('the window has no fixed 1600px content cap', () => {
  const app = rule('.app {')
  assert.match(app, /width:\s*100%/)
  assert.match(app, /max-width:\s*none/)
  assert.equal(css.includes('max-width: 1600px'), false)
  assert.match(rule('.grid-slots {'), /repeat\(auto-fill,\s*minmax\(260px,\s*1fr\)\)/)
})

test('long item names and badges wrap instead of clipping', () => {
  for (const selector of [
    '.item-name {',
    '.bis-item-name {',
    '.upgrade-priority-title {',
    '.item-search-name {',
    '.character-item {',
  ]) {
    assert.match(rule(selector), /overflow-wrap:\s*anywhere/)
  }
  const alt = rule('.alt-name-wrap {')
  assert.match(alt, /flex-wrap:\s*wrap/)
  assert.match(alt, /max-width:\s*100%/)
  assert.match(rule('.badge {'), /white-space:\s*normal/)
})
