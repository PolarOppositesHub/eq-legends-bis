import assert from 'node:assert/strict'
import test from 'node:test'
import { ownedNameSet } from './characterView.js'
import {
  applySectionImport,
  applySyncedSections,
  clearSection,
  migrateSnapshot,
  sectionUpdatedLabel,
} from './inventorySections.js'

function row(location, name, kind, id = '1') {
  return {
    location_raw: location,
    container_kind: kind,
    parent_idx: null,
    depth: 0,
    name,
    name_raw: name,
    id,
    count: 1,
    tier: null,
  }
}

const T1 = '2026-10-01T12:00:00'
const T2 = '2026-10-06T15:30:00'

function parsed({ hoard, wornName = 'Worn Helm', hoardName = 'Old Hoard Leggings' }) {
  const rows = [
    row('Head', wornName, 'worn', '10'),
    row('General 1', 'Bag Item', 'general', '11'),
    row('Bank1', 'Bank Item', 'bank', '12'),
  ]
  if (hoard) rows.push(row('Hoard 1', hoardName, 'dragonhorde', '77'))
  return {
    rows,
    keyring: [{ ring: 'Equipment', name: 'Stored Blade', id: '20', count: 1 }],
    equipment: { HEAD: wornName },
    wornUpgrades: { HEAD: 0 },
    upgrade_hints: {},
    all_items: rows.map((item) => ({
      name: item.name,
      base_name: item.name,
      id: item.id,
      count: '1',
    })).concat([{ name: 'Stored Blade', base_name: 'Stored Blade', id: '20', count: '1' }]),
    sections_present: hoard
      ? ['worn', 'bags', 'bank', 'hoard', 'storage']
      : ['worn', 'bags', 'bank', 'storage'],
    unknown_rows: [],
    unmatched: [],
    worn: [],
  }
}

test('an import without hoard keeps the old hoard and dates each section', () => {
  const first = applySectionImport(null, parsed({ hoard: true }), { ts: T1, source: 'a.txt' })
  const next = applySectionImport(first, parsed({ hoard: false, wornName: 'New Helm' }), { ts: T2, source: 'b.txt' })
  const hoard = next.rows.find((item) => item.container_kind === 'dragonhorde')
  const worn = next.rows.find((item) => item.container_kind === 'worn')
  assert.equal(hoard.name, 'Old Hoard Leggings')
  assert.equal(worn.name, 'New Helm')
  assert.equal(next.equipment.HEAD, 'New Helm')
  assert.equal(next.section_status.hoard.updated_at, T1)
  assert.equal(next.section_status.worn.updated_at, T2)
  assert.equal(next.section_status.hoard.stale, true)
  assert.equal(next.section_status.worn.stale, false)
  assert.equal(sectionUpdatedLabel(next.section_status.hoard), 'Last updated 2026-10-01 12:00:00 · stale')
  assert.equal(ownedNameSet(next).has('old hoard leggings') || [...ownedNameSet(next)].some((name) => name.includes('hoard')), true)
})

test('an import with hoard replaces the old hoard', () => {
  const first = applySectionImport(null, parsed({ hoard: true }), { ts: T1 })
  const next = applySectionImport(first, parsed({ hoard: true, hoardName: 'New Hoard Boots' }), { ts: T2 })
  const hoard = next.rows.filter((item) => item.container_kind === 'dragonhorde')
  assert.deepEqual(hoard.map((item) => item.name), ['New Hoard Boots'])
  assert.equal(next.section_status.hoard.updated_at, T2)
  assert.equal(next.section_status.hoard.stale, false)
})

test('a full import keeps the same owned names', () => {
  const raw = parsed({ hoard: true })
  const imported = applySectionImport(null, raw, { ts: T1 })
  assert.deepEqual([...ownedNameSet(imported)].sort(), [...ownedNameSet(raw)].sort())
})

test('replace everything drops a section the file does not contain', () => {
  const first = applySectionImport(null, parsed({ hoard: true }), { ts: T1 })
  const next = applySectionImport(first, parsed({ hoard: false }), { ts: T2, replaceAll: true })
  assert.equal(next.rows.some((item) => item.container_kind === 'dragonhorde'), false)
})

test('clear section removes only that section', () => {
  const first = applySectionImport(null, parsed({ hoard: true }), { ts: T1 })
  const cleared = clearSection(first, 'hoard', T2)
  assert.equal(cleared.rows.some((item) => item.container_kind === 'dragonhorde'), false)
  assert.equal(cleared.rows.some((item) => item.container_kind === 'worn'), true)
})

test('an old single snapshot is dated at its original import time', () => {
  const old = parsed({ hoard: true })
  old.imported_at = T1
  delete old.sections_present
  const migrated = migrateSnapshot(old)
  assert.equal(migrated.section_events[0].ts, T1)
  assert.equal(migrated.section_events.every((event) => event.type === 'inventory_section'), true)
  assert.ok(migrated.section_events.some((event) => event.payload.section === 'hoard'))
})

test('a synced section event unions by id and the newest section wins', () => {
  const local = applySectionImport(null, parsed({}), { ts: T1 })
  const remote = [{
    id: 'remote-worn',
    ts: T2,
    device_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    source: 'import',
    type: 'inventory_section',
    payload: {
      section: 'worn',
      rows: [{ name: 'New Cloak', container_kind: 'worn', parent_idx: null }],
      equipment: { BACK: 'New Cloak' },
      worn: ['New Cloak'],
    },
  }]
  const merged = applySyncedSections(local, remote)
  assert.equal(merged.section_events.some((event) => event.id === 'remote-worn'), true)
  assert.ok(merged.section_events.length > 1)
  assert.equal(merged.equipment.BACK, 'New Cloak')
  const again = applySyncedSections(merged, remote)
  assert.equal(again.section_events.filter((event) => event.id === 'remote-worn').length, 1)
})
