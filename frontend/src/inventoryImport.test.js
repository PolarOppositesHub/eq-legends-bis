import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { InventoryWatchStatus } from './inventoryImport.jsx'
import {
  acceptInventoryDrop,
  defaultInventorySelection,
  freshnessLine,
  shouldAutoImport,
  withChangedFile,
} from './inventoryImport.js'

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
  assert.match(html, /Newest file/)
  assert.match(html, /Imported Dranak_freeport-Inventory\.txt · 2 min ago/)
})
