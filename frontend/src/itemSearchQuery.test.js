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
  assert.equal(params.usable_classes, 'Wizard')
  assert.equal(params.compare_level, '0')
  assert.equal(params.stat, 'INT')
  assert.equal(params.stat_min, '3')
  assert.equal(params.sort, 'DMG')
  assert.equal(params.sort_dir, 'desc')
  assert.equal(params.sort2, 'INT')
  assert.equal(params.sort2_dir, 'desc')
  assert.equal(params.sort3, undefined)
  assert.equal(params.ratio_min, undefined)
  assert.equal(searchStatLabel('INT'), 'INT')
  assert.equal(searchStatLabel('SVF'), 'SV Fire')
})

test('an empty sort leaves the server on its alphabetical order', () => {
  const params = buildItemSearchParams({ q: 'cap', sorts: [{ key: '', dir: 'desc' }] })
  assert.equal(params.sort, undefined)
  assert.equal(params.stat, undefined)
  assert.equal(params.stat_min, undefined)
})

test('usable-by sends up to three classes and the compare level', () => {
  const params = buildItemSearchParams({
    usableClasses: ['Wizard', 'Warrior', 'Cleric', 'Rogue'],
    usableMatch: 'all',
    compareLevel: 10,
  })
  assert.equal(params.usable_classes, 'Wizard,Warrior,Cleric')
  assert.equal(params.usable_match, 'all')
  assert.equal(params.compare_level, '10')
  assert.equal(params.usable_class, undefined)
})

test('damage/delay ratio is a sort key and a minimum', () => {
  const params = buildItemSearchParams({
    ratioMin: '1.25',
    compareLevel: 10,
    sorts: [
      { key: 'damage_delay_ratio', dir: 'desc' },
      { key: 'damage_delay_ratio', dir: 'asc' },
      { key: 'damage_delay_ratio', dir: 'desc' },
    ],
  })
  assert.equal(params.ratio_min, '1.25')
  assert.equal(params.compare_level, '10')
  assert.equal(params.sort, 'damage_delay_ratio')
  assert.equal(params.sort2, 'damage_delay_ratio')
  assert.equal(params.sort3, 'damage_delay_ratio')
  assert.equal(params.sort2_dir, 'asc')
})
