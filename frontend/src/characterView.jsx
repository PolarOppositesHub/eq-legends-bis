import React, { useMemo, useState } from 'react'
import { buildCharacterView } from './characterView.js'

export function OwnedBadge({ owned }) {
  if (!owned) return null
  return <span className="badge owned-badge">Owned</span>
}

function ItemLine({ node }) {
  if (!node || node.empty) return <span className="muted">Empty</span>
  const count = node.count
  return (
    <span className="character-item">
      <span className="character-item-name">{node.displayName}</span>
      {Number.isFinite(count) && count > 1 ? <span className="muted"> ×{count}</span> : null}
      {node.unknown ? <span className="badge unknown-badge">unknown</span> : null}
    </span>
  )
}

function TreeNode({ node }) {
  return (
    <li>
      <div>
        {node.location ? <span className="muted character-place">{node.location}</span> : null}
        <ItemLine node={node} />
      </div>
      {node.children?.length ? (
        <ul>
          {node.children.map((child) => <TreeNode key={child.key} node={child} />)}
        </ul>
      ) : null}
    </li>
  )
}

export function CharacterView({ view, hideEmpty, onHideEmpty }) {
  const otherCount = (view?.otherSections || []).reduce((sum, group) => sum + group.rows.length, 0)
  if (!view?.hasImport) {
    return (
      <p className="muted inventory-empty">
        No inventory imported yet — use Update from EQ folder or Import Inventory.txt.
      </p>
    )
  }
  return (
    <div className="character-view">
      <label className="muted character-hide-empty">
        <input
          type="checkbox"
          checked={!!hideEmpty}
          onChange={(event) => onHideEmpty(event.target.checked)}
        />
        Hide empty slots
      </label>
      <section className="character-section">
        <h3>Worn</h3>
        {view.worn.length ? (
          <div className="grid-slots">
            {view.worn.map((slot) => (
              <div className="slot-card" key={slot.key}>
                <h3>{slot.location || 'Worn'}</h3>
                <ItemLine node={slot} />
                {slot.children?.length ? (
                  <ul className="character-sockets">
                    {slot.children.map((child) => <TreeNode key={child.key} node={child} />)}
                  </ul>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">No worn rows in this import.</p>
        )}
      </section>
      {view.carried.map((section) => (
        <section className="character-section" key={section.kind}>
          <h3>{section.title}</h3>
          <ul className="character-tree">
            {section.nodes.map((node) => <TreeNode key={node.key} node={node} />)}
          </ul>
        </section>
      ))}
      {view.keyrings.length ? (
        <section className="character-section">
          <h3>Key rings</h3>
          {view.keyrings.map((group) => (
            <div key={group.ring}>
              <h4>{group.ring}</h4>
              <ul className="character-tree">
                {group.items.map((item) => (
                  <li key={item.key}><ItemLine node={item} /></li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      ) : null}
      {otherCount ? (
        <details className="character-other">
          <summary>Other sections ({otherCount})</summary>
          {view.otherSections.map((group) => (
            <div key={`${group.headerLine ?? ''}\0${group.header}`}>
              {(group.headerLine != null || group.header) ? (
                <div className="muted character-other-header">
                  {group.headerLine != null ? `Line ${group.headerLine}` : ''}
                  {group.header ? `${group.headerLine != null ? ': ' : ''}${group.header}` : ''}
                </div>
              ) : null}
              <pre>{group.rows.map((row) => row.raw).join('\n')}</pre>
            </div>
          ))}
        </details>
      ) : null}
    </div>
  )
}

export function CharacterPanel({ importMeta }) {
  const [hideEmpty, setHideEmpty] = useState(true)
  const view = useMemo(
    () => buildCharacterView(importMeta, { hideEmpty }),
    [importMeta, hideEmpty],
  )
  return (
    <CharacterView view={view} hideEmpty={hideEmpty} onHideEmpty={setHideEmpty} />
  )
}
