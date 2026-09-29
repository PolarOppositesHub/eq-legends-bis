import React from 'react'
import { freshnessLine } from './inventoryImport.js'

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
  const pinned = selectedName && list.some((file) => file && file.name === selectedName)
    ? selectedName
    : ''
  const line = freshnessLine(importedName, importedAt, now)
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
      {folder && list.length > 1 ? (
        <label className="muted" style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', fontSize: '0.8rem', marginTop: '0.35rem' }}>
          Character
          <select value={pinned} onChange={(event) => onSelect(event.target.value)}>
            <option value="">Newest file</option>
            {list.map((file) => (
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
