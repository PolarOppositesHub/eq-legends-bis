import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { InventoryBagsSummary, InventoryWatchStatus } from './inventoryImport.jsx'
import {
  acceptInventoryDrop,
  defaultInventorySelection,
  freshnessLine,
  inventoryPanelState,
  shouldAutoImport,
  withChangedFile,
} from './inventoryImport.js'

function selectedOptionValue(html) {
  const tags = html.match(/<option\b[^>]*>/g) || []
  const selected = tags.find((tag) => /\bselected\b/.test(tag))
  const value = selected && selected.match(/value="([^"]*)"/)
  return value ? value[1] : ''
}

const LOCATION = 'Location\tName\tID\tCount\tSlots\nHead\tSynthetic Cap\t1\t1\t10\n'
const KEYRING = 'KeyRing\tName\tID\t\nEquipment\tSynthetic Spare\t9\n'

test('drag-and-drop of an .exe is rejected', async () => {
  const result = await acceptInventoryDrop({
    name: 'inventory.exe',
    text: async () => 'MZ\u0000this is not an inventory dump',
  })
  assert.equal(result.ok, false)
  assert.match(result.message, /inventory\.exe|binar/i)

  const headerInsideExe = await acceptInventoryDrop({
    name: 'EQ/inventory.EXE',
    text: async () => LOCATION,
  })
  assert.equal(headerInsideExe.ok, false)
})

test('drag-and-drop rejects a file that is not an inventory dump', async () => {
  const notes = await acceptInventoryDrop({
    name: 'notes.txt',
    text: async () => 'hello\nthis is not a dump\n',
  })
  assert.equal(notes.ok, false)
  assert.match(notes.message, /not an inventory dump/i)

  const binaryTxt = await acceptInventoryDrop({
    name: 'Dranak_freeport-Inventory.txt',
    text: async () => 'MZ\u0000still a binary',
  })
  assert.equal(binaryTxt.ok, false)
})

test('drag-and-drop accepts an inventory dump by either header', async () => {
  const location = await acceptInventoryDrop({
    name: 'Dranak_freeport-Inventory.txt',
    text: async () => LOCATION,
  })
  assert.equal(location.ok, true)
  assert.equal(location.text, LOCATION)

  const keyring = await acceptInventoryDrop({
    name: 'Inventory.txt',
    text: async () => KEYRING,
  })
  assert.equal(keyring.ok, true)

  const reordered = await acceptInventoryDrop({
    name: 'Hero-Inventory.txt',
    text: async () => 'Name\tSlots\tID\tCount\tLocation\nCap\t10\t1\t1\tHead\n',
  })
  assert.equal(reordered.ok, true)
})

test('freshness line reads Imported <file> · N min ago', () => {
  const now = Date.parse('2026-09-29T18:00:00Z')
  assert.equal(
    freshnessLine('Dranak_freeport-Inventory.txt', now - 2 * 60 * 1000, now),
    'Imported Dranak_freeport-Inventory.txt · 2 min ago',
  )
  assert.equal(freshnessLine('Dranak_freeport-Inventory.txt', now - 10 * 1000, now), 'Imported Dranak_freeport-Inventory.txt · just now')
})

test('character selector defaults to the newest file and auto-import can be off', () => {
  const files = [
    { name: 'New_freeport-Inventory.txt', mtimeMs: 200 },
    { name: 'Old_freeport-Inventory.txt', mtimeMs: 100 },
  ]
  assert.equal(defaultInventorySelection(files, ''), 'New_freeport-Inventory.txt')
  assert.equal(defaultInventorySelection(files, 'Old_freeport-Inventory.txt'), 'Old_freeport-Inventory.txt')
  assert.equal(defaultInventorySelection(files, 'missing-Inventory.txt'), 'New_freeport-Inventory.txt')

  assert.equal(shouldAutoImport({
    enabled: false,
    selectedName: '',
    changedName: 'New_freeport-Inventory.txt',
    files,
  }), false)
  assert.equal(shouldAutoImport({
    enabled: true,
    selectedName: '',
    changedName: 'New_freeport-Inventory.txt',
    files,
  }), true)
  assert.equal(shouldAutoImport({
    enabled: true,
    selectedName: '',
    changedName: 'Old_freeport-Inventory.txt',
    files,
  }), false)
  assert.equal(shouldAutoImport({
    enabled: true,
    selectedName: 'Old_freeport-Inventory.txt',
    changedName: 'Old_freeport-Inventory.txt',
    files,
  }), true)
  assert.equal(shouldAutoImport({
    enabled: true,
    selectedName: 'Old_freeport-Inventory.txt',
    changedName: 'New_freeport-Inventory.txt',
    files,
  }), false)

  const rewritten = withChangedFile(files, {
    name: 'Old_freeport-Inventory.txt',
    path: 'C:\\EQ\\Old_freeport-Inventory.txt',
    mtimeMs: 300,
  })
  assert.equal(rewritten[0].name, 'Old_freeport-Inventory.txt')
  assert.equal(shouldAutoImport({
    enabled: true,
    selectedName: '',
    changedName: 'Old_freeport-Inventory.txt',
    files: rewritten,
  }), true)
})

test('watch status shows the freshness line, auto-import toggle, and character selector', () => {
  const html = renderToStaticMarkup(React.createElement(InventoryWatchStatus, {
    folder: 'C:\\EQ',
    files: [
      { name: 'Dranak_freeport-Inventory.txt', path: 'a', mtimeMs: 2 },
      { name: 'Other_freeport-Inventory.txt', path: 'b', mtimeMs: 1 },
    ],
    selectedName: '',
    onSelect: () => {},
    autoImport: true,
    onAutoImport: () => {},
    importedName: 'Dranak_freeport-Inventory.txt',
    importedAt: 0,
    now: 2 * 60 * 1000,
  }))
  assert.match(html, /Auto-import/)
  assert.doesNotMatch(html, /Newest file/)
  assert.equal(selectedOptionValue(html), 'Dranak_freeport-Inventory.txt')
  assert.match(html, /Imported Dranak_freeport-Inventory\.txt · 2 min ago/)
})

test('freshness, character, and bag list describe the same import', () => {
  const now = Date.parse('2026-09-29T18:00:00Z')
  const files = [
    { name: 'Dranak_freeport-Inventory.txt', path: 'a', mtimeMs: 300 },
    { name: 'Other_freeport-Inventory.txt', path: 'b', mtimeMs: 100 },
  ]
  const items = [
    { name: 'Empty', location: 'General 1' },
    { base_name: 'Synthetic Cap', location: 'Head' },
    { name: 'Mote of Minor Potential', location: 'General 2' },
  ]
  const props = {
    folder: 'C:\\EQ',
    files,
    selectedName: '',
    onSelect: () => {},
    autoImport: true,
    onAutoImport: () => {},
    importedName: 'Dranak_freeport-Inventory.txt',
    importedAt: now - 2 * 60 * 1000,
    now,
    items,
  }
  const view = inventoryPanelState(props)
  assert.equal(view.character, 'Dranak_freeport-Inventory.txt')
  assert.equal(view.freshness, 'Imported Dranak_freeport-Inventory.txt · 2 min ago')
  assert.equal(view.showEmpty, false)
  assert.deepEqual(view.occupied.map((row) => row.base_name || row.name), [
    'Synthetic Cap',
    'Mote of Minor Potential',
  ])

  const html = renderToStaticMarkup(React.createElement(InventoryBagsSummary, props))
  assert.match(html, /Imported Dranak_freeport-Inventory\.txt · 2 min ago/)
  assert.equal(selectedOptionValue(html), 'Dranak_freeport-Inventory.txt')
  assert.match(html, /Synthetic Cap/)
  assert.match(html, /Mote of Minor Potential/)
  assert.doesNotMatch(html, /No inventory imported yet/)
  assert.doesNotMatch(html, /Newest file/)
  assert.doesNotMatch(html, />Empty</)

  // A remembered filename with no rows is not an import: empty state, no freshness line.
  const stale = renderToStaticMarkup(React.createElement(InventoryBagsSummary, {
    ...props,
    items: [],
  }))
  assert.match(stale, /No inventory imported yet/)
  assert.doesNotMatch(stale, /Imported Dranak/)
  assert.doesNotMatch(stale, /Synthetic Cap/)
  assert.doesNotMatch(stale, /Newest file/)
  assert.equal(selectedOptionValue(stale), 'Dranak_freeport-Inventory.txt')

  // A pin for a file that is not the loaded dump does not blank that dump.
  const pinnedElsewhere = renderToStaticMarkup(React.createElement(InventoryBagsSummary, {
    ...props,
    selectedName: 'Other_freeport-Inventory.txt',
  }))
  assert.equal(selectedOptionValue(pinnedElsewhere), 'Dranak_freeport-Inventory.txt')
  assert.match(pinnedElsewhere, /Imported Dranak_freeport-Inventory\.txt · 2 min ago/)
  assert.match(pinnedElsewhere, /Synthetic Cap/)
  assert.doesNotMatch(pinnedElsewhere, /No inventory imported yet/)
})
