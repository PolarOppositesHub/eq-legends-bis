import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { CharacterPanel, CharacterView, OwnedBadge } from './characterView.jsx'
import {
  buildCharacterView,
  isOwnedName,
  ownedNameSet,
  visibleBisSlots,
  visibleSearchItems,
} from './characterView.js'

function row(partial) {
  return {
    location_raw: '',
    container_kind: 'worn',
    parent_idx: null,
    depth: 0,
    socket_index: null,
    socket_label: null,
    name_raw: '',
    name: '',
    tier: null,
    flag_star: false,
    id: '',
    count: 1,
    slots: 10,
    line: 1,
    ...partial,
  }
}

const importMeta = {
  source: 'Synth-Inventory.txt',
  rows: [
    row({ location_raw: 'Head', name_raw: 'Midnight Clad Headband', name: 'Midnight Clad Headband', id: '1001', line: 2 }),
    row({ location_raw: 'Ear', name_raw: 'Left Ear Stud +2', name: 'Left Ear Stud', tier: 2, id: '1002', line: 3 }),
    row({ location_raw: 'Ear', name_raw: 'Right Ear Stud', name: 'Right Ear Stud', id: '1003', line: 4 }),
    row({
      location_raw: 'Ear-Slot7',
      name_raw: 'Focus Stone',
      name: 'Focus Stone',
      id: '2001',
      parent_idx: 2,
      depth: 1,
      socket_index: 7,
      socket_label: 'Slot7 (Focus?)',
      line: 5,
    }),
    row({ location_raw: 'Chest', name_raw: 'Empty', name: 'Empty', id: '0', count: 0, slots: 0, line: 6 }),
    row({
      location_raw: 'General 1',
      container_kind: 'general',
      name_raw: 'Bag of Samples',
      name: 'Bag of Samples',
      id: '7001',
      line: 7,
    }),
    row({
      location_raw: 'General 1-Slot1',
      container_kind: 'general',
      name_raw: 'Mote of Infinitesimal Potential',
      name: 'Mote of Infinitesimal Potential',
      id: '148590',
      count: 5,
      parent_idx: 5,
      depth: 1,
      socket_index: 1,
      line: 8,
    }),
    row({
      location_raw: 'Bank1',
      container_kind: 'bank',
      name_raw: 'Banked Sample',
      name: 'Banked Sample',
      id: '8001',
      line: 9,
    }),
    row({
      location_raw: 'SharedBank1',
      container_kind: 'sharedbank',
      name_raw: 'Shared Sample',
      name: 'Shared Sample',
      id: '9001',
      line: 10,
    }),
    row({
      location_raw: 'Personal-Depot1',
      container_kind: 'depot',
      name_raw: 'Depot Sample',
      name: 'Depot Sample',
      id: '9002',
      line: 11,
    }),
    row({
      location_raw: 'Personal-Depot1-Slot3',
      container_kind: 'depot',
      name_raw: 'Depot Child',
      name: 'Depot Child',
      id: '9003',
      parent_idx: 9,
      depth: 1,
      socket_index: 3,
      line: 12,
    }),
  ],
  keyring: [
    { ring: 'Equipment', name: 'Synthetic Spare Cap', id: '1001', count: 1 },
    { ring: 'Augmentation', name: 'Synthetic Stone (Exaltation)', id: '90001', count: 1 },
    { ring: 'Activated', name: 'Synthetic Guise +4', id: '90002', count: 1 },
  ],
  unknown_rows: [
    { line: 30, header: 'Dragon Hoard\tName\tID', header_line: 28, raw: 'Hoard\tMystery\t1' },
    { line: 4, header: 'Location\tName\tID\tCount\tSlots', header_line: 1, raw: 'NotASlot\tMystery Item\t9\t1\t10' },
  ],
  all_items: [
    { location: 'Head', name: 'Midnight Clad Headband', base_name: 'Midnight Clad Headband', id: '1001', in_catalog: true, has_stats: true },
    { location: 'Ear', name: 'Left Ear Stud +2', base_name: 'Left Ear Stud', id: '1002', in_catalog: false, has_stats: false },
    { location: 'Ear', name: 'Right Ear Stud', base_name: 'Right Ear Stud', id: '1003', in_catalog: true, has_stats: false },
    { location: 'Ear-Slot7', name: 'Focus Stone', base_name: 'Focus Stone', id: '2001', in_catalog: true, has_stats: false },
    { location: 'General 1', name: 'Bag of Samples', base_name: 'Bag of Samples', id: '7001', in_catalog: false },
    { location: 'General 1-Slot1', name: 'Mote of Infinitesimal Potential', base_name: 'Mote of Infinitesimal Potential', id: '148590', in_catalog: true },
    { location: 'Bank1', name: 'Banked Sample', base_name: 'Banked Sample', id: '8001', in_catalog: false },
    { location: 'SharedBank1', name: 'Shared Sample', base_name: 'Shared Sample', id: '9001', in_catalog: true },
    { location: 'Personal-Depot1', name: 'Depot Sample', base_name: 'Depot Sample', id: '9002', in_catalog: false },
    { location: 'Personal-Depot1-Slot3', name: 'Depot Child', base_name: 'Depot Child', id: '9003', in_catalog: false },
    { location: 'Equipment', name: 'Synthetic Spare Cap', base_name: 'Synthetic Spare Cap', id: '1001', in_catalog: true },
    { location: 'Augmentation', name: 'Synthetic Stone (Exaltation)', base_name: 'Synthetic Stone (Exaltation)', id: '90001', in_catalog: false },
    { location: 'Activated', name: 'Synthetic Guise +4', base_name: 'Synthetic Guise', id: '90002', in_catalog: true },
  ],
  equipment: { HEAD: 'Midnight Clad Headband', EAR1: 'Left Ear Stud', EAR2: 'Right Ear Stud' },
}

test('worn grid keeps tiers, both ears, and the focus socket on the latest ear', () => {
  const view = buildCharacterView(importMeta, { hideEmpty: true })
  const ears = view.worn.filter((slot) => slot.location === 'Ear')
  assert.equal(ears.length, 2)
  assert.equal(ears[0].displayName, 'Left Ear Stud +2')
  assert.equal(ears[0].children.length, 0)
  assert.equal(ears[0].unknown, true)
  assert.equal(ears[1].displayName, 'Right Ear Stud')
  assert.equal(ears[1].unknown, false)
  assert.equal(ears[1].children.length, 1)
  assert.equal(ears[1].children[0].location, 'Slot7 (Focus?)')
  assert.equal(ears[1].children[0].displayName, 'Focus Stone')
  assert.equal(ears[1].children[0].unknown, false)
  assert.equal(view.worn.some((slot) => slot.location === 'Chest'), false)
  const shown = buildCharacterView(importMeta, { hideEmpty: false })
  assert.equal(shown.worn.some((slot) => slot.location === 'Chest' && slot.empty), true)
  for (const slot of view.worn) {
    assert.equal(slot.stats, undefined)
    assert.equal(slot.stats_plus0, undefined)
    assert.equal(slot.hasStats, undefined)
  }
})

test('bags, bank, shared bank, and depot stay in their own trees', () => {
  const view = buildCharacterView(importMeta)
  const bags = view.carried.find((section) => section.kind === 'general')
  const bank = view.carried.find((section) => section.kind === 'bank')
  const shared = view.carried.find((section) => section.kind === 'sharedbank')
  const depot = view.carried.find((section) => section.kind === 'depot')
  assert.equal(bags.title, 'Bags')
  assert.equal(bags.nodes[0].location, 'General 1')
  assert.equal(bags.nodes[0].displayName, 'Bag of Samples')
  assert.equal(bags.nodes[0].unknown, true)
  assert.equal(bags.nodes[0].children[0].location, 'Slot1')
  assert.equal(bags.nodes[0].children[0].displayName, 'Mote of Infinitesimal Potential')
  assert.equal(bags.nodes[0].children[0].count, 5)
  assert.equal(bank.nodes[0].displayName, 'Banked Sample')
  assert.equal(shared.nodes[0].location, 'SharedBank1')
  assert.equal(depot.nodes[0].location, 'Personal-Depot1')
  assert.equal(depot.nodes[0].children[0].location, 'Slot3')
  assert.equal(depot.nodes[0].children[0].displayName, 'Depot Child')
  assert.deepEqual(view.keyrings.map((group) => group.ring), ['Equipment', 'Augmentation', 'Activated'])
  assert.equal(view.keyrings[1].items[0].unknown, true)
  assert.equal(view.keyrings[0].items[0].unknown, false)
  assert.equal(view.keyrings[2].items[0].displayName, 'Synthetic Guise +4')
})

test('unknown rows stay in Other sections and are not given a new tree', () => {
  const view = buildCharacterView(importMeta)
  assert.equal(view.carried.some((section) => /dragon|hoard|nota/i.test(section.title)), false)
  assert.equal(view.otherSections.length, 2)
  assert.equal(view.otherSections[0].header, 'Dragon Hoard\tName\tID')
  assert.equal(view.otherSections[0].rows[0].raw, 'Hoard\tMystery\t1')
  assert.equal(view.otherSections[1].rows[0].raw, 'NotASlot\tMystery Item\t9\t1\t10')
  const html = renderToStaticMarkup(
    React.createElement(CharacterView, {
      view,
      hideEmpty: true,
      onHideEmpty: () => {},
    }),
  )
  assert.match(html, /Other sections \(2\)/)
  assert.match(html, /Hoard\tMystery\t1/)
  assert.match(html, /NotASlot\tMystery Item/)
  assert.match(html, /Slot7 \(Focus\?\)/)
  assert.match(html, /unknown/)
  assert.doesNotMatch(html, /AC:|HP:|stats_plus|Click\?|Worn\?|Proc\?/)
  assert.equal(html.includes('>Dragon'), false)
})

test('an import saved before the slot tree still shows worn and bank rows', () => {
  const view = buildCharacterView({
    source: 'Old-Inventory.txt',
    all_items: [
      { name: 'Jade Mace', base_name: 'Jade Mace', location: 'Primary', id: '1', in_catalog: true },
      { name: 'Banked Sample', base_name: 'Banked Sample', location: 'Bank1', id: '2', in_catalog: false },
      { name: 'Mystery Item', base_name: 'Mystery Item', location: 'NotASlot', id: '9', in_catalog: false },
    ],
  })
  assert.equal(view.fromTree, false)
  assert.equal(view.worn[0].displayName, 'Jade Mace')
  assert.equal(view.worn[0].unknown, false)
  assert.equal(view.carried.find((section) => section.kind === 'bank').nodes[0].unknown, true)
  assert.equal(view.otherSections[0].rows[0].raw, 'NotASlot\tMystery Item')
  assert.equal(view.worn[0].stats, undefined)
})

test('owned marks match base names and the owned-only filter does not rescore', () => {
  const owned = ownedNameSet(importMeta)
  assert.equal(isOwnedName('Midnight Clad Headband', owned), true)
  assert.equal(isOwnedName('left ear stud', owned), true)
  assert.equal(isOwnedName('Synthetic Guise', owned), true)
  assert.equal(isOwnedName('Synthetic Stone (Exaltation)', owned), true)
  assert.equal(isOwnedName('Cap', owned), false)
  assert.equal(isOwnedName('Mystery Item', owned), false)

  const slots = [
    {
      slot: 'HEAD',
      name: 'Midnight Clad Headband',
      score: 12,
      alts: [
        { name: 'Left Ear Stud', score: 4 },
        { name: 'Not Owned', score: 9 },
      ],
    },
    {
      slot: 'CHEST',
      name: 'Not Worn',
      score: 30,
      alts: [{ name: 'Midnight Clad Headband', score: 3 }],
    },
  ]
  assert.equal(visibleBisSlots(slots, owned, false), slots)
  assert.equal(visibleBisSlots(slots, ownedNameSet(null), false), slots)
  const filtered = visibleBisSlots(slots, owned, true)
  assert.deepEqual(filtered.map((slot) => slot.slot), ['HEAD'])
  assert.equal(filtered[0].score, 12)
  assert.deepEqual(filtered[0].alts.map((alt) => [alt.name, alt.score]), [['Left Ear Stud', 4]])
  assert.equal(slots[0].alts.length, 2)
  assert.equal(slots[1].score, 30)

  const search = [
    { name: 'Not Owned', score: 1 },
    { name: 'Synthetic Guise', score: 8 },
    { name: 'Midnight Clad Headband', score: 3 },
  ]
  assert.equal(visibleSearchItems(search, owned, false), search)
  assert.deepEqual(
    visibleSearchItems(search, owned, true).map((item) => [item.name, item.score]),
    [['Synthetic Guise', 8], ['Midnight Clad Headband', 3]],
  )
})

test('Character panel renders the import and the owned badge is separate from scores', () => {
  const html = renderToStaticMarkup(React.createElement(CharacterPanel, { importMeta }))
  assert.match(html, /Hide empty slots/)
  assert.match(html, /Worn/)
  assert.match(html, /Bags/)
  assert.match(html, /Shared bank/)
  assert.match(html, /Other sections/)
  assert.doesNotMatch(html, />Chest</)
  assert.equal(renderToStaticMarkup(React.createElement(OwnedBadge, { owned: true })), '<span class="badge owned-badge">Owned</span>')
  assert.equal(renderToStaticMarkup(React.createElement(OwnedBadge, { owned: false })), '')
  const empty = renderToStaticMarkup(React.createElement(CharacterPanel, { importMeta: null }))
  assert.match(empty, /No inventory imported yet/)
})
