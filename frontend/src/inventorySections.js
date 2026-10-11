/**
 * Inventory imports merge by section.
 *
 * Each section update is an event: {id, ts, source, type, payload}.
 * Replay keeps the newest event per section. A later sync can union these
 * events by id. This module does not talk to a sync provider.
 *
 * Sections: worn, bags, bank, shared bank, Dragon's Hoard, depot, storage
 * (the KeyRing table), and unknown rows. A file replaces only the sections
 * it contains. Replace everything also clears sections the file does not have.
 * Equipped names come from the worn section only.
 */

export const SECTION_ORDER = ['worn', 'bags', 'bank', 'sharedbank', 'hoard', 'depot', 'storage', 'unknown']

export const SECTION_TITLES = {
  worn: 'Worn',
  bags: 'Bags',
  bank: 'Bank',
  sharedbank: 'Shared bank',
  hoard: "Dragon's Hoard",
  depot: 'Depot',
  storage: 'Storage',
  unknown: 'Other sections',
}

const KIND_TO_SECTION = {
  worn: 'worn',
  general: 'bags',
  bank: 'bank',
  sharedbank: 'sharedbank',
  dragonhorde: 'hoard',
  depot: 'depot',
  unknown: 'unknown',
}

export function sectionOfKind(kind) {
  return KIND_TO_SECTION[kind] || null
}

export function formatSectionStamp(ts) {
  if (typeof ts !== 'string' || ts.length < 19) return 'unknown'
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(ts)
  if (!match) return 'unknown'
  return `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}:${match[6]}`
}

export function sectionUpdatedLabel(status) {
  const when = formatSectionStamp(status?.updated_at)
  const stale = status?.stale ? ' · stale' : ''
  return `Last updated ${when}${stale}`
}

export function localSectionStamp(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

/** Dates only. Rows stay as the caller stored them. */
export function sectionStatusFromEvents(events) {
  return project(events).section_status
}

export function migrateSnapshot(meta) {
  if (!meta || typeof meta !== 'object') return null
  if (Array.isArray(meta.section_events) && meta.section_events.length) return meta
  const ts = typeof meta.imported_at === 'string' ? meta.imported_at : ''
  const chunks = splitParsed(meta)
  const events = []
  for (const id of SECTION_ORDER) {
    if (!chunks[id] || !chunkHasRows(chunks[id])) continue
    events.push(makeEvent({ ts, source: 'import', section: id, chunk: chunks[id], n: events.length }))
  }
  const view = project(events)
  return {
    ...meta,
    section_events: events,
    section_status: view.section_status,
    imported_at: ts,
  }
}

export function applySectionImport(previous, parsed, options = {}) {
  const ts = options.ts || ''
  const replaceAll = !!options.replaceAll
  const prior = previous ? migrateSnapshot(previous) : null
  const present = new Set(sectionsIn(parsed))
  const chunks = splitParsed(parsed)
  const events = [...(prior?.section_events || [])]
  const ids = replaceAll ? SECTION_ORDER : SECTION_ORDER.filter((id) => present.has(id))
  for (const id of ids) {
    const included = present.has(id)
    events.push(makeEvent({
      ts,
      source: 'import',
      section: id,
      chunk: included ? (chunks[id] || emptyChunk(id)) : emptyChunk(id),
      empty: !included,
      n: events.length,
    }))
  }
  return finish(prior, parsed, events, ts, options.source || '')
}

export function clearSection(previous, section, ts) {
  const prior = migrateSnapshot(previous)
  if (!prior) return null
  const events = [...prior.section_events, makeEvent({
    ts: ts || '',
    source: 'manual',
    section,
    chunk: emptyChunk(section),
    empty: true,
    n: prior.section_events.length,
  })]
  return finish(prior, null, events, ts || prior.imported_at || '', prior.source || '')
}

function finish(prior, parsed, events, ts, source) {
  const view = project(events)
  const first = !prior
  const equipment = view.equipment
  const base = first && parsed ? snapshotFromParsed(parsed) : snapshotFromView(view, prior)
  return {
    ...base,
    equipment,
    wornUpgrades: view.wornUpgrades,
    upgrade_hints: view.upgrade_hints,
    rows: first && parsed ? (parsed.rows || []) : view.rows,
    keyring: first && parsed ? (parsed.keyring || []) : view.keyring,
    unknown_rows: first && parsed ? (parsed.unknown_rows || []) : view.unknown_rows,
    all_items: first && parsed ? (parsed.all_items || []) : view.all_items,
    source: source || base.source || '',
    section_events: events,
    section_status: view.section_status,
    imported_at: ts,
  }
}

function snapshotFromParsed(parsed) {
  return {
    unmatched_count: parsed.unmatched_count || 0,
    unmatched: parsed.unmatched || [],
    worn: parsed.worn || [],
    skipped_count: parsed.skipped_count || 0,
    source: parsed.file_name || parsed.source || '',
  }
}

function snapshotFromView(view, prior) {
  return {
    unmatched_count: prior?.unmatched_count || 0,
    unmatched: prior?.unmatched || [],
    worn: view.worn || [],
    skipped_count: prior?.skipped_count || 0,
    source: prior?.source || '',
  }
}

function sectionsIn(parsed) {
  if (Array.isArray(parsed?.sections_present) && parsed.sections_present.length) {
    const ids = new Set(parsed.sections_present)
    if ((parsed.unknown_rows || []).length) ids.add('unknown')
    return [...ids]
  }
  const found = new Set()
  for (const row of parsed?.rows || []) {
    const id = sectionOfKind(row?.container_kind)
    if (id) found.add(id)
  }
  if ((parsed?.keyring || []).length) found.add('storage')
  if ((parsed?.unknown_rows || []).length) found.add('unknown')
  return [...found]
}

function splitParsed(parsed) {
  const groups = {}
  const indexOf = []
  ;(parsed?.rows || []).forEach((row, index) => {
    const id = sectionOfKind(row?.container_kind) || 'unknown'
    if (!groups[id]) groups[id] = []
    indexOf[index] = { id, at: groups[id].length }
    groups[id].push({ ...row })
  })
  for (const [id, list] of Object.entries(groups)) {
    for (const row of list) {
      if (row.parent_idx == null) continue
      const mapped = indexOf[row.parent_idx]
      row.parent_idx = mapped && mapped.id === id ? mapped.at : null
    }
  }
  const chunks = {}
  for (const id of Object.keys(groups)) {
    chunks[id] = {
      rows: groups[id],
      keyring: [],
      unknown_rows: id === 'unknown' ? (parsed?.unknown_rows || []) : [],
      equipment: id === 'worn' ? { ...(parsed?.equipment || {}) } : {},
      wornUpgrades: id === 'worn' ? { ...(parsed?.wornUpgrades || parsed?.upgrade_hints || {}) } : {},
      upgrade_hints: id === 'worn' ? { ...(parsed?.upgrade_hints || {}) } : {},
      worn: id === 'worn' ? (parsed?.worn || []) : [],
    }
  }
  if ((parsed?.keyring || []).length || (parsed?.sections_present || []).includes('storage')) {
    chunks.storage = {
      ...(chunks.storage || emptyChunk('storage')),
      keyring: parsed.keyring || [],
    }
  }
  if ((parsed?.unknown_rows || []).length && !chunks.unknown) {
    chunks.unknown = { ...emptyChunk('unknown'), unknown_rows: parsed.unknown_rows }
  }
  if (parsed?.equipment && Object.keys(parsed.equipment).length && !chunks.worn) {
    chunks.worn = {
      ...emptyChunk('worn'),
      equipment: { ...parsed.equipment },
      wornUpgrades: { ...(parsed.wornUpgrades || parsed.upgrade_hints || {}) },
      upgrade_hints: { ...(parsed.upgrade_hints || {}) },
      worn: parsed.worn || [],
    }
  }
  return chunks
}

function project(events) {
  const ordered = (events || [])
    .map((event, index) => ({ event, index }))
    .filter(({ event }) => event && event.type === 'inventory_section' && event.payload?.section)
    .sort((a, b) => String(a.event.ts).localeCompare(String(b.event.ts)) || a.index - b.index)
  const latest = new Map()
  for (const { event } of ordered) latest.set(event.payload.section, event)
  let newest = ''
  for (const event of latest.values()) {
    if (event.ts && event.ts > newest) newest = event.ts
  }
  const status = {}
  const pieces = []
  let equipment = {}
  let wornUpgrades = {}
  let upgradeHints = {}
  let worn = []
  let keyring = []
  let unknownRows = []
  for (const id of SECTION_ORDER) {
    const event = latest.get(id)
    if (!event) continue
    const payload = event.payload || {}
    status[id] = {
      title: SECTION_TITLES[id] || id,
      updated_at: event.ts || '',
      stale: !!(newest && event.ts && event.ts < newest),
    }
    if (id === 'storage') {
      keyring = payload.keyring || []
      continue
    }
    if (id === 'unknown') {
      unknownRows = payload.unknown_rows || []
    }
    if (id === 'worn') {
      equipment = { ...(payload.equipment || {}) }
      wornUpgrades = { ...(payload.wornUpgrades || {}) }
      upgradeHints = { ...(payload.upgrade_hints || {}) }
      worn = payload.worn || []
    }
    const rows = payload.rows || []
    if (rows.length) pieces.push(rows)
  }
  const rows = joinRows(pieces)
  return {
    rows,
    keyring,
    unknown_rows: unknownRows,
    equipment,
    wornUpgrades,
    upgrade_hints: upgradeHints,
    worn,
    all_items: itemsFrom(rows, keyring),
    section_status: status,
  }
}

function joinRows(pieces) {
  const out = []
  for (const list of pieces) {
    const base = out.length
    for (const row of list) {
      const copy = { ...row }
      if (copy.parent_idx != null) copy.parent_idx = base + Number(copy.parent_idx)
      out.push(copy)
    }
  }
  return out
}

function itemsFrom(rows, keyring) {
  const items = []
  for (const row of rows || []) {
    const name = row?.name || ''
    if (!name || name.toLowerCase() === 'empty') continue
    items.push({
      name: row.name_raw || name,
      base_name: name,
      id: row.id || '',
      count: row.count == null ? '' : String(row.count),
      upgrade_from_name: row.tier ?? null,
    })
  }
  for (const entry of keyring || []) {
    if (!entry?.name) continue
    items.push({
      name: entry.name,
      base_name: entry.name,
      id: entry.id || '',
      count: entry.count == null ? '1' : String(entry.count),
    })
  }
  return items
}

function makeEvent({ ts, source, section, chunk, empty = false, n = 0 }) {
  return {
    id: `inventory_section:${section}:${ts}:${n}`,
    ts,
    source,
    type: 'inventory_section',
    payload: {
      section,
      empty: !!empty,
      rows: chunk?.rows || [],
      keyring: chunk?.keyring || [],
      unknown_rows: chunk?.unknown_rows || [],
      equipment: chunk?.equipment || {},
      wornUpgrades: chunk?.wornUpgrades || {},
      upgrade_hints: chunk?.upgrade_hints || {},
      worn: chunk?.worn || [],
    },
  }
}

function emptyChunk(section) {
  return {
    rows: [],
    keyring: [],
    unknown_rows: [],
    equipment: {},
    wornUpgrades: {},
    upgrade_hints: {},
    worn: [],
    section,
  }
}

function chunkHasRows(chunk) {
  return !!(
    (chunk.rows && chunk.rows.length)
    || (chunk.keyring && chunk.keyring.length)
    || (chunk.unknown_rows && chunk.unknown_rows.length)
    || (chunk.equipment && Object.keys(chunk.equipment).length)
  )
}
