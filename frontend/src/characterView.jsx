import React, { useEffect, useMemo, useState } from 'react'
import { itemImageUrl } from './api.js'
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

function CharacterItemIcon({ name }) {
  if (!name) return null
  return (
    <img
      className="item-icon"
      src={itemImageUrl(name)}
      alt=""
      onError={(event) => {
        event.currentTarget.style.display = 'none'
      }}
    />
  )
}

function ItemLine({ node, renderItemName, onLocate }) {
  if (!node || node.empty) return <span className="muted">Empty</span>
  const count = node.count
  const name = node.displayName
  const iconName = node.catalogName || node.baseName || name
  return (
    <span className="character-item">
      <CharacterItemIcon name={iconName} />
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

function stopHeaderClick(event) {
  event.stopPropagation()
}

function CollapseButton({ id, title, collapsed, onToggle, className = '' }) {
  const open = !collapsed?.[id]
  return (
    <button
      type="button"
      className={`character-collapse-btn${className ? ` ${className}` : ''}`}
      aria-expanded={open}
      data-collapse-id={id}
      onClick={() => onToggle && onToggle(id)}
    >
      <span className="character-collapse-arrow" aria-hidden="true">{open ? '▼' : '▶'}</span>
      <span>{title}</span>
    </button>
  )
}

function TreeNode({ node, highlightKey, renderItemName, onLocate, collapsed, onToggle }) {
  const hit = highlightKey && highlightKey === node.key
  const childCount = node.children?.length || 0
  const collapseId = childCount ? `node:${node.key}` : ''
  const open = !collapseId || !collapsed?.[collapseId]
  const row = (
    <div>
      {node.location ? <span className="muted character-place">{node.location}</span> : null}
      <span onClick={stopHeaderClick} onKeyDown={stopHeaderClick}>
        <ItemLine node={node} renderItemName={renderItemName} onLocate={onLocate} />
      </span>
    </div>
  )
  return (
    <li
      data-character-slot={node.key}
      className={hit ? 'character-slot-hit' : undefined}
    >
      {childCount ? (
        <div
          className="character-collapse-row"
          role="button"
          tabIndex={0}
          aria-expanded={open}
          data-collapse-id={collapseId}
          onClick={() => onToggle && onToggle(collapseId)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              onToggle && onToggle(collapseId)
            }
          }}
        >
          <span className="character-collapse-arrow" aria-hidden="true">{open ? '▼' : '▶'}</span>
          {row}
        </div>
      ) : row}
      {childCount && open ? (
        <ul>
          {node.children.map((child) => (
            <TreeNode
              key={child.key}
              node={child}
              highlightKey={highlightKey}
              renderItemName={renderItemName}
              onLocate={onLocate}
              collapsed={collapsed}
              onToggle={onToggle}
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

function MergeList({ merge, renderItemName, onLocate, collapsed, onToggle }) {
  const groups = merge?.groups || []
  const omitted = merge?.omitted || []
  const stackedOmitted = omitted.filter((item) => item.reason === 'stacked-in-one-slot')
  const ambiguousOmitted = omitted.filter((item) => item.reason === 'ambiguous-id')
  const open = !collapsed?.merge
  return (
    <section className="character-section" data-testid="character-merge" data-collapse-id="merge">
      <h3 className="character-collapse">
        <CollapseButton id="merge" title="Items that can be merged" collapsed={collapsed} onToggle={onToggle} />
      </h3>
      {open ? (
        <>
          <p className="muted character-merge-note">{MERGE_LIST_NOTE}</p>
          {stackedOmitted.length ? (
            <p className="muted" data-testid="merge-omitted">
              {stackedOmitted.length} stacked item{stackedOmitted.length === 1 ? '' : 's'} left out because Count is greater than 1 in one slot.
            </p>
          ) : null}
          {ambiguousOmitted.length ? (
            <p className="muted" data-testid="merge-ambiguous-id">
              {ambiguousOmitted.length} item{ambiguousOmitted.length === 1 ? '' : 's'} left out because the copies do not share one id.
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
        </>
      ) : null}
    </section>
  )
}

function CarriedSection({ section, highlightKey, renderItemName, onLocate, collapsed, onToggle }) {
  const id = `section:${section.kind}`
  const open = !collapsed?.[id]
  return (
    <section className="character-section" data-collapse-id={id}>
      <h3 className="character-collapse">
        <CollapseButton id={id} title={section.title} collapsed={collapsed} onToggle={onToggle} />
      </h3>
      {open ? (
        section.nodes.length ? (
          <ul className="character-tree">
            {section.nodes.map((node) => (
              <TreeNode
                key={node.key}
                node={node}
                highlightKey={highlightKey}
                renderItemName={renderItemName}
                onLocate={onLocate}
                collapsed={collapsed}
                onToggle={onToggle}
              />
            ))}
          </ul>
        ) : (
          <p className="muted">No rows in this section.</p>
        )
      ) : null}
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
  collapsed,
  onToggle,
}) {
  const otherCount = (view?.otherSections || []).reduce((sum, group) => sum + group.rows.length, 0)
  const locate = typeof onLocate === 'function' ? onLocate : () => {}
  const toggle = typeof onToggle === 'function' ? onToggle : () => {}
  if (!view?.hasImport) {
    return (
      <p className="muted inventory-empty">
        No inventory imported yet — use Update from EQ folder or Import Inventory.txt.
      </p>
    )
  }
  const carriedOf = (kind) => (view.carried || []).find((section) => section.kind === kind)
  const beforeStorage = ['general', 'bank', 'sharedbank']
    .map(carriedOf)
    .filter(Boolean)
  const hoard = carriedOf('dragonhorde') || {
    kind: 'dragonhorde',
    title: "Dragon's Hoard",
    nodes: [],
  }
  const depot = carriedOf('depot')
  const wornOpen = !collapsed?.worn
  const storageOpen = !collapsed?.storage
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
      <section className="character-section" data-collapse-id="worn">
        <h3 className="character-collapse">
          <CollapseButton id="worn" title="Worn" collapsed={collapsed} onToggle={toggle} />
        </h3>
        {wornOpen ? (
          view.worn.length ? (
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
                          collapsed={collapsed}
                          onToggle={toggle}
                        />
                      ))}
                    </ul>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No worn rows in this import.</p>
          )
        ) : null}
      </section>
      <MergeList
        merge={view.merge}
        renderItemName={renderItemName}
        onLocate={locate}
        collapsed={collapsed}
        onToggle={toggle}
      />
      {beforeStorage.map((section) => (
        <CarriedSection
          key={section.kind}
          section={section}
          highlightKey={highlightKey}
          renderItemName={renderItemName}
          onLocate={locate}
          collapsed={collapsed}
          onToggle={toggle}
        />
      ))}
      <section className="character-section" data-testid="dragon-hoard" data-collapse-id="section:dragonhorde">
        <h3 className="character-collapse">
          <CollapseButton
            id="section:dragonhorde"
            title="Dragon's Hoard"
            collapsed={collapsed}
            onToggle={toggle}
          />
        </h3>
        {!collapsed?.['section:dragonhorde'] ? (
          <>
            {view.dragonHorde?.note ? (
              <p className="muted" data-testid="dragon-hoard-note">{view.dragonHorde.note}</p>
            ) : null}
            {hoard.nodes.length ? (
              <ul className="character-tree">
                {hoard.nodes.map((node) => (
                  <TreeNode
                    key={node.key}
                    node={node}
                    highlightKey={highlightKey}
                    renderItemName={renderItemName}
                    onLocate={locate}
                    collapsed={collapsed}
                    onToggle={toggle}
                  />
                ))}
              </ul>
            ) : null}
          </>
        ) : null}
      </section>
      {view.keyrings.length ? (
        <section className="character-section" data-testid="character-storage" data-collapse-id="storage">
          <h3 className="character-collapse">
            <CollapseButton id="storage" title="Storage" collapsed={collapsed} onToggle={toggle} />
          </h3>
          {storageOpen ? view.keyrings.map((group) => {
            const id = `storage:${group.ring}`
            const open = !collapsed?.[id]
            return (
              <div key={group.ring} data-collapse-id={id}>
                <h4 className="character-collapse">
                  <CollapseButton id={id} title={group.ring} collapsed={collapsed} onToggle={toggle} />
                </h4>
                {open ? (
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
                ) : null}
              </div>
            )
          }) : null}
        </section>
      ) : null}
      {depot ? (
        <CarriedSection
          section={depot}
          highlightKey={highlightKey}
          renderItemName={renderItemName}
          onLocate={locate}
          collapsed={collapsed}
          onToggle={toggle}
        />
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

export function CharacterPanel({
  importMeta,
  query = '',
  onQuery,
  renderItemName,
  collapsed,
  onCollapsedChange,
}) {
  const [hideEmpty, setHideEmpty] = useState(true)
  const [highlightKey, setHighlightKey] = useState('')
  const [localCollapsed, setLocalCollapsed] = useState({})
  const closed = collapsed && typeof collapsed === 'object' ? collapsed : localCollapsed
  const view = useMemo(
    () => buildCharacterView(importMeta, { hideEmpty }),
    [importMeta, hideEmpty],
  )
  const hits = useMemo(
    () => searchCharacterCopies(view.copies, query),
    [view.copies, query],
  )
  const locate = (key) => setHighlightKey(key || '')
  const toggle = (id) => {
    const next = { ...closed }
    if (next[id]) delete next[id]
    else next[id] = true
    if (typeof onCollapsedChange === 'function') onCollapsedChange(next)
    else setLocalCollapsed(next)
  }
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
      collapsed={closed}
      onToggle={toggle}
    />
  )
}
