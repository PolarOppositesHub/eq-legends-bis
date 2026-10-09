import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { CurrenciesPanel } from './currenciesView.jsx'
import { bagCountsFromImport, characterFromInventoryFile } from './currenciesView.js'

test('inventory filename yields the character and bag counts', () => {
  assert.equal(characterFromInventoryFile('C:\\EQ\\Zasariz_qeynos-Inventory.txt'), 'Zasariz')
  assert.equal(characterFromInventoryFile('notes.txt'), '')
  const counts = bagCountsFromImport({
    motes: [{ name: 'Mote of Minor Potential', count: 2 }],
    void_touched: { name: 'Void-Touched Potential', count: 1 },
    wind_runes: [{ name: 'Wind Rune Caza', count: 4 }],
  })
  assert.equal(counts['Mote of Minor Potential'], 2)
  assert.equal(counts['Void-Touched Potential'], 1)
  assert.equal(counts['Wind Rune Caza'], 4)
})

test('currencies panel shows storage, pending merges, and the void countdown', () => {
  const html = renderToStaticMarkup(React.createElement(CurrenciesPanel, {
    character: 'Zasariz',
    view: {
      pending_label: 'Pending: 1 merge since last check',
      warning: null,
      motes: [{
        name: 'Mote of Minor Potential',
        bags: 1,
        storage: 4,
        total: 5,
        item_xp: 1,
        condense: { warning: 'This loses 0 item XP', needs_confirmed: false },
      }],
      void_touched: {
        name: 'Void-Touched Potential',
        held_label: '1/3',
        earned_label: '1/3',
        countdown_label: '6d 2h 0m · resets Tuesday 10:00 AM CT',
      },
      wind_runes: [{ name: 'Wind Rune Caza', bags: 0, storage: 1, total: 1, need: null }],
      ledger: {},
    },
  }))
  assert.match(html, /data-testid="currencies-panel"/)
  assert.match(html, /Pending: 1 merge since last check/)
  assert.match(html, /Held 1\/3/)
  assert.match(html, /Earned this week 1\/3/)
  assert.match(html, /10:00 AM CT/)
  assert.match(html, /Plane of Sky need is on Requirements/)
  assert.match(html, /does not plan Void-Touched spending/)
})
