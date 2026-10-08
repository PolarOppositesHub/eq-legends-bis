import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { isOwnedName, ownedItemLevels, ownedNameSet } from './characterView.js'
import { canonicalItemName, itemIsLore, namesMatch } from './itemNames.js'
import { sanitizeWorkspace } from './workspaceSession.js'

const GAME = 'Slime Blood of Cazic-Thule'
const OLD = 'Slime Blood of Cazic Thule'

test('slime blood owned badge matches either spelling', () => {
  const owned = ownedNameSet({
    all_items: [{ base_name: `${GAME} +5`, name: `${GAME} +5`, id: '20655' }],
  })
  assert.equal(isOwnedName(GAME, owned), true)
  assert.equal(isOwnedName(OLD, owned), true)
  assert.equal(isOwnedName('slime  blood of cazic thule', owned), true)
  assert.equal(namesMatch("Crushbone Cadet`s Grimoire", "Crushbone Cadet's Grimoire"), true)
  assert.equal(namesMatch('Packmaster’s Lash', 'Packmasters Lash'), true)
  assert.equal(namesMatch('Synthetic Stone', 'Synthetic Stone (Exaltation)'), false)
  assert.equal(canonicalItemName(OLD), GAME)
})

test('an item id marks the catalog row owned when the name differs', () => {
  const owned = ownedNameSet({
    rows: [{ name: 'Diamondine Earring (Exaltation)', id: '10165' }],
  })
  assert.equal(isOwnedName('Diamondine Earring (Exaltation)', owned), true)
  assert.equal(isOwnedName('Diamondine Earring', owned), false)
  assert.equal(isOwnedName('Diamondine Earring', owned, '10165'), true)
  assert.equal(isOwnedName('Diamondine Earring', owned, '0'), false)
})

test('owned levels keep the highest upgrade and do not double-count rows', () => {
  const levels = ownedItemLevels({
    all_items: [
      { base_name: GAME, name: `${GAME} +5`, upgrade_from_name: 5, count: '1', id: '20655' },
    ],
    rows: [{ name_raw: `${OLD} +9`, name: OLD, tier: 9, id: '20655' }],
    equipment: { HANDS: GAME },
  })
  const row = levels.find((item) => item.name === GAME)
  assert.ok(row)
  assert.equal(row.upgrade, 9)
  assert.equal(row.count, 1)
  assert.equal(row.id, '20655')
})

test('a saved one-wrist build and the old slime blood spelling still load', () => {
  const slots = ['HEAD', 'WRIST1', 'WRIST2', 'HANDS']
  const known = new Set([GAME, 'Granite Bracer', 'Other'])
  const { state } = sanitizeWorkspace({
    equipment: { WRIST: OLD, HANDS: 'Other' },
    bisOverrides: { WRIST1: 'Granite Bracer', WRIST: 'Ignored Because Wrist1 Is Set' },
    wornUpgrades: { WRIST: 4 },
  }, {
    slots,
    itemExists: (name) => known.has(name),
  })
  assert.equal(state.equipment.WRIST1, GAME)
  assert.equal(state.equipment.WRIST, undefined)
  assert.equal(state.equipment.HANDS, 'Other')
  assert.equal(state.bisOverrides.WRIST1, 'Granite Bracer')
  assert.equal(state.bisOverrides.WRIST, undefined)
  assert.equal(state.wornUpgrades.WRIST1, 4)
  assert.equal(state.wornUpgrades.WRIST, undefined)
})

test('two wrist slots render as separate worn selects', () => {
  const slots = ['WRIST1', 'WRIST2']
  const html = renderToStaticMarkup(React.createElement(
    'div',
    { className: 'equip-list' },
    slots.map((slot) => React.createElement('select', {
      key: slot,
      'data-testid': `worn-slot-${slot}`,
      'aria-label': slot,
    })),
  ))
  assert.match(html, /data-testid="worn-slot-WRIST1"/)
  assert.match(html, /data-testid="worn-slot-WRIST2"/)
  assert.equal(itemIsLore('MAGIC ITEM · LORE Equipped'), true)
  assert.equal(itemIsLore('MAGIC ITEM'), false)
  assert.equal(itemIsLore(''), false)
})
