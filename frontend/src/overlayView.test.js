import assert from 'node:assert/strict'
import test from 'node:test'
import { meterRows, overlayIdFromSearch } from './overlayView.js'

test('zone meter rows sum damage and heals and leave DPS off', () => {
  const rows = meterRows({
    scope: 'zone',
    rows: [{ source: 'Zasariz', damage: 10, heals: 4, dps: 99 }],
  })
  assert.equal(rows[0].damage, 10)
  assert.equal(rows[0].heals, 4)
  assert.equal('dps' in rows[0], false)
})

test('fight meter rows keep the stored DPS', () => {
  const rows = meterRows({
    scope: 'fight',
    rows: [{ source: 'Zasariz', damage: 80, heals: 0, dps: 8, sdps: 2.7 }],
  })
  assert.equal(rows[0].dps, 8)
  assert.equal(rows[0].sdps, 2.7)
})

test('overlay route ids are the three windows', () => {
  assert.equal(overlayIdFromSearch('?overlay=dps'), 'dps')
  assert.equal(overlayIdFromSearch('?overlay=heal'), 'heal')
  assert.equal(overlayIdFromSearch('?overlay=alert'), 'alert')
  assert.equal(overlayIdFromSearch('?overlay=xp'), '')
})
