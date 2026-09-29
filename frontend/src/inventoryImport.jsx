import React from 'react'
import {
  defaultInventorySelection,
  freshnessLine,
  inventoryPanelState,
  NO_INVENTORY_YET,
} from './inventoryImport.js'

export function InventoryWatchStatus({
  folder,
  files,
  selectedName,
  onSelect,
  autoImport,
  onAutoImport,
  importedName,
  importedAt,
  now,
}) {
  const list = Array.isArray(files) ? files : []
  const imported = String(importedName || '').trim()
  const options = list.slice()
  if (imported && !options.some((file) => file && file.name === imported)) {
    options.unshift({ name: imported, path: '' })
  }
  const value = defaultInventorySelection(options, selectedName || imported)
  const line = freshnessLine(imported, importedAt, now)
  return (
    <div className="inventory-watch-status">
      <p className="muted" style={{ marginTop: 0, marginBottom: '0.35rem', fontSize: '0.8rem' }}>
        {folder
          ? <>EQ folder: <code>{folder}</code></>
          : 'Set EQ folder once, then Update pulls the newest *-Inventory.txt after /outputfile inventory.'}
      </p>
      {folder ? (
        <label className="muted" style={{ display: 'inline-flex', gap: '0.4rem', alignItems: 'center', fontSize: '0.8rem' }}>
          <input
            type="checkbox"
            checked={!!autoImport}
            onChange={(event) => onAutoImport(event.target.checked)}
          />
          Auto-import
        </label>
      ) : null}
      {folder && options.length > 1 ? (
        <label className="muted" style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', fontSize: '0.8rem', marginTop: '0.35rem' }}>
          Character
          <select value={value} onChange={(event) => onSelect(event.target.value)}>
            {options.map((file) => (
              <option key={file.path || file.name} value={file.name}>{file.name}</option>
            ))}
          </select>
        </label>
      ) : null}
      {line ? (
        <p className="muted inventory-freshness" style={{ margin: '0.35rem 0 0', fontSize: '0.8rem' }}>
          {line}
        </p>
      ) : null}
    </div>
  )
}

export function InventoryBagsSummary({
  folder,
  files,
  selectedName,
  onSelect,
  autoImport,
  onAutoImport,
  importedName,
  importedAt,
  now,
  items,
  children,
}) {
  const view = inventoryPanelState({
    files,
    selectedName,
    importedName,
    importedAt,
    items,
    now,
  })
  let body = null
  if (view.showEmpty) {
    body = <p className="muted inventory-empty">{NO_INVENTORY_YET}</p>
  } else if (children) {
    body = children
  } else {
    body = (
      <ul className="item-search-list">
        {view.occupied.map((row, index) => {
          const name = row?.base_name || row?.name || ''
          const loc = row?.location || '—'
          return (
            <li key={`${loc}-${name}-${index}`}>
              <div className="item-search-name">{name}</div>
              <div className="muted">{loc}</div>
            </li>
          )
        })}
      </ul>
    )
  }
  return (
    <div className="inventory-bags-summary">
      <InventoryWatchStatus
        folder={folder}
        files={files}
        selectedName={view.character}
        onSelect={onSelect}
        autoImport={autoImport}
        onAutoImport={onAutoImport}
        importedName={view.freshness ? importedName : ''}
        importedAt={view.freshness ? importedAt : null}
        now={now}
      />
      {body}
    </div>
  )
}
