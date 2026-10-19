import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { CompanionPanel, MapsPanel } from './companionView.jsx'
import {
  COMPANION_BUFF_NOTE,
  buffOverlayText,
  exaltationCandidates,
  loadoutKey,
  redactProfile,
  remainingLabel,
  wornResistRows,
} from './companionView.js'

test('loadout key follows the selected classes and level', () => {
  assert.equal(loadoutKey(['Warrior', 'Shadow Knight', 'Paladin'], 50), 'Warrior / Shadow Knight / Paladin @ 50')
  assert.equal(loadoutKey(['Wizard'], 29), 'Wizard @ 29')
  assert.equal(loadoutKey([], null), 'unknown classes @ unknown')
  assert.notEqual(loadoutKey(['Wizard'], 50), loadoutKey(['Warrior'], 50))
})

test('missing timer and map text stays unknown', () => {
  assert.equal(remainingLabel(null), 'unknown')
  assert.equal(remainingLabel(''), 'unknown')
  assert.match(buffOverlayText({ active: [] }), /unknown/)
  assert.match(buffOverlayText({ active: [{ name: 'Slow', target: 'a rat', remaining_text: 'unknown' }] }), /Slow on a rat/)
  const html = renderToStaticMarkup(React.createElement(CompanionPanel, {
    character: '',
    loadout: 'Wizard @ 29',
  }))
  assert.match(html, /data-testid="companion-panel"/)
  assert.match(html, /Wizard @ 29/)
  assert.match(html, new RegExp(COMPANION_BUFF_NOTE.slice(0, 24)))
  const maps = renderToStaticMarkup(React.createElement(MapsPanel, { character: '' }))
  assert.match(maps, /data-testid="maps-panel"/)
  assert.match(maps, /unknown/)
})

test('exaltation rows and worn rows do not invent stats', () => {
  const rows = exaltationCandidates([
    { name: 'Cloak of Flames', socket_label: null },
    { name: 'Blade (Exaltation)', socket_label: 'Slot7 (Focus?)', location_raw: 'Primary-Slot7' },
  ])
  assert.equal(rows.length, 1)
  assert.equal(rows[0].name, 'Blade (Exaltation)')
  const worn = wornResistRows({ BACK: 'Cloak of Flames', HEAD: '' }, { BACK: 3 })
  assert.deepEqual(worn, [{ slot: 'BACK', name: 'Cloak of Flames', upgrade: 3 }])
})

test('profile redact drops tokens', () => {
  const clean = redactProfile({ theme: 'classic', refresh_token: 'secret-value', note: 'ok' })
  assert.equal(clean.theme, 'classic')
  assert.equal(clean.refresh_token, undefined)
  assert.equal(JSON.stringify(clean).includes('secret-value'), false)
})
