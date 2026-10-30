import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { ShortcutsDialog } from './shortcuts.jsx'
import { HOME_JUMPS } from './dashboardsView.js'
import {
  CHORD_MS,
  SHORTCUTS,
  isTypingTarget,
  nextShortcut,
  shortcutHelpLines,
} from './shortcuts.js'

test('g then a letter opens each side menu page', () => {
  const app = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
  const start = app.indexOf('const navItems = [')
  const end = app.indexOf(']', start)
  const ids = [...app.slice(start, end).matchAll(/id: '([^']+)'/g)].map((match) => match[1])
  assert.deepEqual(SHORTCUTS.map((row) => row.tab).sort(), [...ids].sort())
  assert.equal(nextShortcut({ key: 'g' }, false).type, 'arm')
  assert.equal(nextShortcut({ key: 'G' }, false).type, 'arm')
  assert.equal(nextShortcut({ key: 'o' }, true).tab, 'overview')
  assert.equal(nextShortcut({ key: 'p' }, true).tab, 'parser')
  assert.equal(nextShortcut({ key: 'i' }, true).tab, 'search')
  assert.equal(nextShortcut({ key: 'x' }, true).type, 'clear')
  assert.equal(nextShortcut({ key: 'o' }, false), null)
  assert.equal(nextShortcut({ key: '?' }, false).type, 'help')
  assert.equal(nextShortcut({ key: '?', ctrlKey: true }, false), null)
  assert.equal(nextShortcut({ key: 'g', repeat: true }, false), null)
  assert.equal(nextShortcut({ key: 'Escape' }, true).type, 'clear')
  assert.equal(CHORD_MS, 1200)
})

test('shortcuts stay quiet while typing', () => {
  assert.equal(isTypingTarget({ tagName: 'INPUT' }), true)
  assert.equal(isTypingTarget({ tagName: 'TEXTAREA' }), true)
  assert.equal(isTypingTarget({ tagName: 'SELECT' }), true)
  assert.equal(isTypingTarget({ tagName: 'DIV', isContentEditable: true }), true)
  assert.equal(isTypingTarget({ tagName: 'BUTTON' }), false)
  assert.equal(nextShortcut({ key: '?', target: { tagName: 'INPUT' } }, false), null)
  assert.equal(nextShortcut({ key: 'g', target: { tagName: 'TEXTAREA' } }, false), null)
  assert.equal(nextShortcut({ key: 'o', target: { tagName: 'INPUT' } }, true).type, 'clear')
})

test('the shortcut dialog lists every page and the home jumps are real pages', () => {
  const html = renderToStaticMarkup(React.createElement(ShortcutsDialog, { onClose: () => {} }))
  assert.match(html, /data-testid="shortcuts-dialog"/)
  assert.match(html, /data-testid="shortcut-list"/)
  for (const row of SHORTCUTS) {
    assert.match(html, new RegExp(`<kbd>${row.key}</kbd>`))
    assert.match(html, new RegExp(row.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  }
  const lines = shortcutHelpLines()
  assert.match(lines[0], /Press \?/)
  for (const jump of HOME_JUMPS) {
    assert.equal(SHORTCUTS.some((row) => row.tab === jump.id && row.label === jump.label), true)
  }
})
