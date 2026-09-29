/**
 * Character tab and owned-item marks for an inventory import.
 *
 * The tree comes from the parser snapshot (rows, keyring, unknown_rows).
 * Names missing from the catalog are marked unknown. No stat block is
 * attached here — the catalog is only a yes/no match.
 *
 * Owned badges and the owned-only filter never rescore BiS or Item Search.
 * With the filter off, the slot list is the same array the API returned.
 */

const OBSERVED_WORN = new Set([
  'ANY SLOT', 'AMMO', 'ARMS', 'BACK', 'CHEST', 'EAR', 'FACE', 'FEET',
  'FINGERS', 'HANDS', 'HEAD', 'HELD', 'LEGS', 'NECK', 'PRIMARY', 'RANGE',
  'SECONDARY', 'SHOULDERS', 'WAIST', 'WRIST',
  'FINGER', 'RANGED', 'ANY', 'CHARM',
])

const CARRIED_SECTIONS = [
  { kind: 'general', title: 'Bags' },
  { kind: 'bank', title: 'Bank' },
  { kind: 'sharedbank', title: 'Shared bank' },
  { kind: 'depot', title: 'Depot' },
]

const TRAILING_SLOTS = /(?:-Slot\d+)+$/i

export function itemBaseName(name) {
  let n = String(name || '').trim()
  if (n.endsWith('*')) n = n.slice(0, -1).trim()
  const match = n.match(/(?:\s*\+\s*\d+)\s*$/)
  if (match) n = n.slice(0, match.index).trim()
  return n
}

function isEmptyName(name) {
  const n = String(name || '').trim().toLowerCase()
  return !n || n === 'empty'
}

export function ownedNameSet(importMeta) {
  const set = new Set()
  if (!importMeta || typeof importMeta !== 'object') return set
  const add = (name) => {
    const base = itemBaseName(name)
    if (!base || base.toLowerCase() === 'empty') return
    set.add(base.toLowerCase())
  }
  for (const row of importMeta.all_items || []) add(row.base_name || row.name)
  for (const row of importMeta.rows || []) add(row.name || row.name_raw)
  for (const entry of importMeta.keyring || []) add(entry.name)
  const equipment = importMeta.equipment
  if (equipment && typeof equipment === 'object') {
    for (const name of Object.values(equipment)) add(name)
  }
  return set
}

export function isOwnedName(name, owned) {
  const base = itemBaseName(name).toLowerCase()
  if (!base || base === 'empty') return false
  return owned instanceof Set && owned.has(base)
}

/**
 * Filter off: return the API slots unchanged.
 * Filter on: drop picks that are not owned. Remaining slots and alternates
 * keep their original order and score fields.
 */
export function visibleBisSlots(slots, owned, ownedOnly) {
  const list = Array.isArray(slots) ? slots : []
  if (!ownedOnly) return list
  const out = []
  for (const slot of list) {
    if (!isOwnedName(slot && slot.name, owned)) continue
    const alts = Array.isArray(slot.alts)
      ? slot.alts.filter((alt) => isOwnedName(alt && alt.name, owned))
      : slot.alts
    if (alts === slot.alts) out.push(slot)
    else out.push({ ...slot, alts })
  }
  return out
}

export function visibleSearchItems(items, owned, ownedOnly) {
  const list = Array.isArray(items) ? items : []
  if (!ownedOnly) return list
  return list.filter((item) => isOwnedName(item && item.name, owned))
}

function splitLocation(location) {
  const raw = String(location || '')
  const match = raw.match(TRAILING_SLOTS)
  if (!match) return { base: raw, slots: [] }
  const slots = []
  const re = /-Slot(\d+)/gi
  let found = re.exec(match[0])
  while (found) {
    slots.push(Number(found[1]))
    found = re.exec(match[0])
  }
  return { base: raw.slice(0, match.index), slots }
}

function numberedToken(token, prefix, low, high) {
  if (token.length <= prefix.length) return false
  if (!token.toLowerCase().startsWith(prefix.toLowerCase())) return false
  const rest = token.slice(prefix.length)
  if (!/^\d+$/.test(rest)) return false
  const number = Number(rest)
  if (number < low) return false
  return high == null || number <= high
}

function containerKindOf(base) {
  const token = String(base || '').trim()
  if (/^general \d+$/i.test(token) && numberedToken(token, 'general ', 1, null)) return 'general'
  if (numberedToken(token, 'sharedbank', 1, 6)) return 'sharedbank'
  if (numberedToken(token, 'bank', 1, 24)) return 'bank'
  if (token.toLowerCase() === 'personal-depot1') return 'depot'
  if (OBSERVED_WORN.has(token.toUpperCase())) return 'worn'
  return 'unknown'
}

function asInt(value) {
  if (value == null || value === '') return null
  const n = Number(value)
  if (!Number.isFinite(n)) return null
  return Math.trunc(n)
}

function catalogIndex(importMeta) {
  const byExact = new Map()
  const byName = new Map()
  for (const row of importMeta?.all_items || []) {
    const name = itemBaseName(row?.base_name || row?.name)
    if (!name || name.toLowerCase() === 'empty') continue
    const status = {
      inCatalog: !!row.in_catalog,
      hasStats: !!row.has_stats,
    }
    const id = row.id == null ? '' : String(row.id)
    const loc = row.location == null ? '' : String(row.location)
    byExact.set(`${loc}\0${name.toLowerCase()}\0${id}`, status)
    const nameKey = name.toLowerCase()
    if (!byName.has(nameKey)) byName.set(nameKey, status)
  }
  return { byExact, byName }
}

function lookupCatalog(index, { location, name, id }) {
  const base = itemBaseName(name)
  if (!base || base.toLowerCase() === 'empty') {
    return { empty: true, inCatalog: false, hasStats: false }
  }
  const idText = id == null ? '' : String(id)
  const loc = location == null ? '' : String(location)
  const exact = index.byExact.get(`${loc}\0${base.toLowerCase()}\0${idText}`)
  if (exact) return { empty: false, ...exact }
  const byName = index.byName.get(base.toLowerCase())
  if (byName) return { empty: false, ...byName }
  return { empty: false, inCatalog: false, hasStats: false }
}

function displayNameOf(row) {
  const raw = String(row.name_raw || '').trim()
  if (raw && !isEmptyName(raw)) return raw
  const name = String(row.name || '').trim()
  if (!name || isEmptyName(name)) return ''
  return name
}

function placeOf(row) {
  if (row.socket_label) return String(row.socket_label)
  if (row.socket_index != null && row.socket_index !== '') return `Slot${row.socket_index}`
  return String(row.location_raw || row.location || '')
}

function decorate(row, index, catalog, keyPrefix) {
  const location = String(row.location_raw || row.location || '')
  const nameForCatalog = row.name || row.name_raw || ''
  const status = lookupCatalog(catalog, {
    location,
    name: nameForCatalog,
    id: row.id,
  })
  const empty = status.empty || isEmptyName(row.name_raw) || isEmptyName(row.name)
  return {
    key: `${keyPrefix}-${index}`,
    location: placeOf(row),
    displayName: empty ? '' : displayNameOf(row),
    count: asInt(row.count),
    slots: asInt(row.slots),
    empty,
    unknown: !empty && !status.inCatalog,
    children: [],
  }
}

function linkForest(rows, indexes, catalog, keyPrefix) {
  const nodes = new Map()
  for (const index of indexes) {
    nodes.set(index, decorate(rows[index], index, catalog, keyPrefix))
  }
  const roots = []
  for (const index of indexes) {
    const node = nodes.get(index)
    const parent = rows[index].parent_idx
    if (parent != null && nodes.has(parent)) nodes.get(parent).children.push(node)
    else roots.push(node)
  }
  return roots
}

function pruneEmpty(nodes, hideEmpty) {
  if (!hideEmpty) return nodes
  const out = []
  for (const node of nodes) {
    const children = pruneEmpty(node.children || [], true)
    if (node.empty && !children.length) continue
    out.push(children === node.children ? node : { ...node, children })
  }
  return out
}

function rowsFromStoredItems(importMeta) {
  const items = Array.isArray(importMeta?.all_items) ? importMeta.all_items : []
  const rows = items.map((item) => {
    const location = String(item?.location || '')
    const split = splitLocation(location)
    const socket = split.slots.length ? split.slots[split.slots.length - 1] : null
    return {
      location_raw: location,
      container_kind: containerKindOf(split.base),
      parent_idx: null,
      depth: split.slots.length,
      socket_index: socket,
      socket_label: null,
      name_raw: item?.name || '',
      name: item?.base_name || itemBaseName(item?.name),
      tier: item?.upgrade_from_name ?? null,
      flag_star: String(item?.name || '').trim().endsWith('*'),
      id: item?.id || '',
      count: item?.count,
      slots: item?.slots,
    }
  })
  const latest = new Map()
  rows.forEach((row, index) => {
    const split = splitLocation(row.location_raw)
    if (split.slots.length) {
      const parentLocation = row.location_raw.replace(/-Slot\d+$/i, '')
      const parent = latest.get(parentLocation)
      if (parent != null) row.parent_idx = parent
    }
    latest.set(row.location_raw, index)
  })
  return rows
}

function otherSections(unknownRows) {
  const groups = []
  const index = new Map()
  for (const row of unknownRows || []) {
    if (!row || typeof row !== 'object') continue
    const header = String(row.header || '')
    const headerLine = row.header_line == null ? '' : String(row.header_line)
    const key = `${headerLine}\0${header}`
    let group = index.get(key)
    if (!group) {
      group = { header, headerLine: row.header_line ?? null, rows: [] }
      index.set(key, group)
      groups.push(group)
    }
    group.rows.push({
      line: row.line ?? null,
      raw: String(row.raw || ''),
    })
  }
  return groups
}

function keyringGroups(importMeta, catalog) {
  const groups = []
  const index = new Map()
  for (const entry of importMeta?.keyring || []) {
    if (!entry || typeof entry !== 'object') continue
    const ring = String(entry.ring || '').trim()
    if (!ring) continue
    let group = index.get(ring)
    if (!group) {
      group = { ring, items: [] }
      index.set(ring, group)
      groups.push(group)
    }
    const status = lookupCatalog(catalog, {
      location: ring,
      name: entry.name,
      id: entry.id,
    })
    const empty = status.empty || isEmptyName(entry.name)
    group.items.push({
      key: `${ring}-${group.items.length}`,
      location: ring,
      displayName: empty ? '' : String(entry.name || '').trim(),
      count: asInt(entry.count),
      slots: null,
      empty,
      unknown: !empty && !status.inCatalog,
      children: [],
    })
  }
  return groups
}

export function buildCharacterView(importMeta, { hideEmpty = true } = {}) {
  const meta = importMeta && typeof importMeta === 'object' ? importMeta : null
  const storedRows = Array.isArray(meta?.rows) ? meta.rows : []
  const fromTree = storedRows.length > 0
  const rows = fromTree ? storedRows : rowsFromStoredItems(meta)
  const catalog = catalogIndex(meta)
  const indexesOf = (kind) => rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => row && row.container_kind === kind)
    .map(({ index }) => index)

  const worn = pruneEmpty(
    linkForest(rows, indexesOf('worn'), catalog, 'worn'),
    hideEmpty,
  )
  const carried = CARRIED_SECTIONS.map((section) => ({
    kind: section.kind,
    title: section.title,
    nodes: pruneEmpty(linkForest(rows, indexesOf(section.kind), catalog, section.kind), hideEmpty),
  })).filter((section) => section.nodes.length)

  const unknown = Array.isArray(meta?.unknown_rows) ? meta.unknown_rows : []
  let sections = otherSections(unknown)
  if (!sections.length) {
    const extras = rows
      .filter((row) => row && row.container_kind === 'unknown' && !isEmptyName(row.name_raw || row.name))
      .map((row) => ({
        line: row.line ?? null,
        raw: [row.location_raw, row.name_raw || row.name].filter(Boolean).join('\t'),
      }))
    if (extras.length) sections = [{ header: '', headerLine: null, rows: extras }]
  }
  const keyrings = keyringGroups(meta, catalog)
    .map((group) => ({
      ...group,
      items: hideEmpty ? group.items.filter((item) => !item.empty) : group.items,
    }))
    .filter((group) => group.items.length)

  const hasImport = Boolean(
    meta && (
      storedRows.length
      || (meta.all_items || []).length
      || (meta.keyring || []).length
      || unknown.length
      || (meta.equipment && Object.keys(meta.equipment).length)
      || meta.source
    ),
  )

  return {
    hasImport,
    fromTree,
    worn,
    carried,
    keyrings,
    otherSections: sections,
  }
}
