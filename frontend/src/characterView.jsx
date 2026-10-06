import React, { useEffect, useMemo, useState } from 'react'
import {
  MERGE_LIST_NOTE,
  buildCharacterView,
  scrollCharacterSlotIntoView,
  searchCharacterCopies,
} from './characterView.js'

export function OwnedBadge({ owned }) {
  if (!owned) return null
  return <span className="badge owned-badge">Owned</span>
}

function ItemLine({ node, renderItemName, onLocate }) {
  if (!node || node.empty) return <span className="muted">Empty</span>
  const count = node.count
  const name = node.displayName
  return (
    <span className="character-item">
      {name && typeof renderItemName === 'function' ? (
        renderItemName(node, { onLocate })
      ) : (
        <span className="character-item-name">{name}</span>
      )}
      {Number.isFinite(count) && count > 1 ? <span className="muted"> ×{count}</span> : null}
      {node.unknown ? <span className="badge unknown-badge">unknown</span> : null}
    </span>
  )
}

function TreeNode({ node, highlightKey, renderItemName, onLocate }) {
  const hit = highlightKey && highlightKey === node.key
  return (
    <li
      data-character-slot={node.key}
      className={hit ? 'character-slot-hit' : undefined}
    >
      <div>
        {node.location ? <span className="muted character-place">{node.location}</span> : null}
        <ItemLine node={node} renderItemName={renderItemName} onLocate={onLocate} />
      </div>
      {node.children?.length ? (
        <ul>
          {node.children.map((child) => (
            <TreeNode
              key={child.key}
              node={child}
              highlightKey={highlightKey}
              renderItemName={renderItemName}
              onLocate={onLocate}
            />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

function SearchHit({ hit, renderItemName, onLocate }) {
  return (
    <li>
      <div
        className="item-search-result character-search-hit"
        data-testid="character-search-hit"
        data-character-hit={hit.key}
        onClick={() => onLocate(hit.key)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            onLocate(hit.key)
          }
        }}
        role="button"
        tabIndex={0}
      >
        <div>
          <ItemLine node={hit} renderItemName={renderItemName} onLocate={onLocate} />
          <div className="muted" style={{ fontSize: '0.78rem' }}>{hit.place}</div>
        </div>
      </div>
    </li>
  )
}

function MergeList({ merge, dragonHorde, renderItemName, onLocate }) {
  const groups = merge?.groups || []
  const omitted = merge?.omitted || []
  return (
    <section className="character-section" data-testid="character-merge">
      <h3>Items that can be merged</h3>
      <p className="muted character-merge-note">{MERGE_LIST_NOTE}</p>
      {dragonHorde?.note ? (
        <p className="muted" data-testid="dragon-hoard-note">{dragonHorde.note}</p>
      ) : null}
      {omitted.length ? (
        <p className="muted" data-testid="merge-omitted">
          {omitted.length} stacked item{omitted.length === 1 ? '' : 's'} left out because Count is greater than 1 in one slot.
        </p>
      ) : null}
      {groups.length ? (
        <ul className="character-tree">
          {groups.map((group) => (
            <li key={group.key}>
              <ItemLine
                node={{
                  displayName: group.name,
                  catalogName: group.catalogName || group.name,
                  baseName: group.name,
                  unknown: group.unknown,
                  empty: false,
                  count: group.total,
                }}
                renderItemName={renderItemName}
                onLocate={onLocate}
              />
              <ul>
                {group.copies.map((copy) => (
                  <li key={copy.key}>
                    <button type="button" className="zone-link" onClick={() => onLocate(copy.key)}>
                      {copy.place}
                      {Number(copy.copyCount) > 1 ? ` ×${copy.copyCount}` : ''}
                    </button>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No duplicate items to merge in this import.</p>
      )}
    </section>
  )
}

export function CharacterView({
  view,
  hideEmpty,
  onHideEmpty,
  query,
  onQuery,
  hits,
  highlightKey,
  onLocate,
  renderItemName,
}) {
  const otherCount = (view?.otherSections || []).reduce((sum, group) => sum + group.rows.length, 0)
  const locate = typeof onLocate === 'function' ? onLocate : () => {}
  if (!view?.hasImport) {
    return (
      <p className="muted inventory-empty">
        No inventory imported yet — use Update from EQ folder or Import Inventory.txt.
      </p>
    )
  }
  return (
    <div className="character-view">
      <div className="item-search-bar">
        <input
          type="text"
          data-testid="character-search"
          placeholder="Find an item in your bags…"
          value={query || ''}
          onChange={(event) => onQuery && onQuery(event.target.value)}
          aria-label="Find an item on this character"
        />
      </div>
      {hits?.length ? (
        <ul className="item-search-list" data-testid="character-search-results">
          {hits.slice(0, 500).map((hit) => (
            <SearchHit key={hit.key} hit={hit} renderItemName={renderItemName} onLocate={locate} />
          ))}
        </ul>
      ) : (query || '').trim() ? (
        <p className="muted">No matching items in this import.</p>
      ) : null}
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
              <div
                className={`slot-card${highlightKey === slot.key ? ' character-slot-hit' : ''}`}
                data-character-slot={slot.key}
                key={slot.key}
              >
                <h3>{slot.location || 'Worn'}</h3>
                <ItemLine node={slot} renderItemName={renderItemName} onLocate={locate} />
                {slot.children?.length ? (
                  <ul className="character-sockets">
                    {slot.children.map((child) => (
                      <TreeNode
                        key={child.key}
                        node={child}
                        highlightKey={highlightKey}
                        renderItemName={renderItemName}
                        onLocate={locate}
                      />
                    ))}
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
            {section.nodes.map((node) => (
              <TreeNode
                key={node.key}
                node={node}
                highlightKey={highlightKey}
                renderItemName={renderItemName}
                onLocate={locate}
              />
            ))}
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
                {group.items.map((item) => {
                  const hit = highlightKey && highlightKey === item.key
                  return (
                    <li
                      key={item.key}
                      data-character-slot={item.key}
                      className={hit ? 'character-slot-hit' : undefined}
                    >
                      <ItemLine node={item} renderItemName={renderItemName} onLocate={locate} />
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </section>
      ) : null}
      <MergeList
        merge={view.merge}
        dragonHorde={view.dragonHorde}
        renderItemName={renderItemName}
        onLocate={locate}
      />
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

export function CharacterPanel({ importMeta, query = '', onQuery, renderItemName }) {
  const [hideEmpty, setHideEmpty] = useState(true)
  const [highlightKey, setHighlightKey] = useState('')
  const view = useMemo(
    () => buildCharacterView(importMeta, { hideEmpty }),
    [importMeta, hideEmpty],
  )
  const hits = useMemo(
    () => searchCharacterCopies(view.copies, query),
    [view.copies, query],
  )
  const locate = (key) => setHighlightKey(key || '')
  useEffect(() => {
    if (!highlightKey) return
    scrollCharacterSlotIntoView(highlightKey)
  }, [highlightKey, hideEmpty, view])
  return (
    <CharacterView
      view={view}
      hideEmpty={hideEmpty}
      onHideEmpty={setHideEmpty}
      query={query}
      onQuery={onQuery}
      hits={hits}
      highlightKey={highlightKey}
      onLocate={locate}
      renderItemName={renderItemName}
    />
  )
}
