import assert from 'node:assert/strict'
import test from 'node:test'
import { buildItemSearchParams, searchStatLabel } from './itemSearchQuery.js'

test('search params keep token query, slot, class, stat min, and three sort keys', () => {
  const params = buildItemSearchParams({
    q: 'sword of the night',
    slot: 'PRIMARY',
    typeName: 'sword',
    usableClass: 'Wizard',
    stat: 'INT',
    statMin: '3',
    sorts: [
      { key: 'DMG', dir: 'desc' },
      { key: 'INT', dir: 'desc' },
      { key: '', dir: 'asc' },
    ],
    limit: 80,
  })
  assert.equal(params.q, 'sword of the night')
  assert.equal(params.slot, 'PRIMARY')
  assert.equal(params.type, 'sword')
  assert.equal(params.usable_class, 'Wizard')
  assert.equal(params.stat, 'INT')
  assert.equal(params.stat_min, '3')
  assert.equal(params.sort, 'DMG')
  assert.equal(params.sort_dir, 'desc')
  assert.equal(params.sort2, 'INT')
  assert.equal(params.sort2_dir, 'desc')
  assert.equal(params.sort3, undefined)
  assert.equal(searchStatLabel('INT'), 'INT')
  assert.equal(searchStatLabel('SVF'), 'SV Fire')
})

test('an empty sort leaves the server on its alphabetical order', () => {
  const params = buildItemSearchParams({ q: 'cap', sorts: [{ key: '', dir: 'desc' }] })
  assert.equal(params.sort, undefined)
  assert.equal(params.stat, undefined)
  assert.equal(params.stat_min, undefined)
})
