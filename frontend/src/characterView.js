/**
 * Character tab and owned-item marks for an inventory import.
 *
 * The tree comes from the parser snapshot (rows, keyring, unknown_rows).
 * Names missing from the catalog are marked unknown. No stat block is
 * attached here — the catalog is only a yes/no match. Hover stats are
 * loaded by the same item popup the rest of the app uses.
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
  { kind: 'dragonhorde', title: 'Dragon hoard' },
]

const TRAILING_SLOTS = /(?:-Slot\d+)+$/i
const DRAGON_HOARD_RE = /dragon(?:['’]s)?\s*hoard/i
const SEARCH_STOP = new Set(['of', 'the', 'a', 'an', 'and'])

const CONTAINER_PLACE = {
  worn: 'Worn',
  general: 'Bag',
  bank: 'Bank',
  sharedbank: 'Shared bank',
  depot: 'Depot',
  dragonhorde: 'Dragon hoard',
  keyring: 'Key ring',
}

/**
 * The inventory file and the catalog do not say which items the game
 * allows you to merge. The only facts they do carry are identity (name,
 * tier, id) and Location Count. This id is the conservative rule below.
 */
export const MERGEABLE_DUPLICATE_RULE = 'same-item-separate-copies-exclude-location-stacks'

export const MERGE_LIST_NOTE = 'Same item means the same base name, the same tier (a missing tier is not +0), and the same id when both copies have one. A copy with no id still matches when every identified copy uses that one id. More than one separate copy is listed. A Location Count greater than 1 is a stack in one slot and is left out. Copies that share a name but use different ids stay apart, and a copy with no id is left out in that case. The inventory file and the catalog have no other merge rule, so anything else is left out.'

export function isDragonHoardName(value) {
  return DRAGON_HOARD_RE.test(String(value || ''))
}

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
  if (isDragonHoardName(token)) return 'dragonhorde'
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

function tierOfName(name) {
  const n = String(name || '').trim().replace(/\*$/, '').trim()
  const match = n.match(/(?:\s*\+\s*(\d+))\s*$/)
  return match ? Number(match[1]) : null
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
  const count = asInt(row.count)
  const baseName = empty ? '' : itemBaseName(nameForCatalog)
  return {
    key: `${keyPrefix}-${index}`,
    location: placeOf(row),
    displayName: empty ? '' : displayNameOf(row),
    baseName,
    catalogName: baseName,
    tier: row.tier == null || row.tier === '' ? tierOfName(row.name_raw || row.name) : row.tier,
    id: row.id == null ? '' : String(row.id),
    count,
    copyCount: 1,
    stackedInSlot: !empty && count != null && count > 1,
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

function effectiveKind(row) {
  const location = String(row?.location_raw || row?.location || '')
  const split = splitLocation(location)
  if (isDragonHoardName(split.base) || isDragonHoardName(location)) return 'dragonhorde'
  if (row?.container_kind) return row.container_kind
  return containerKindOf(split.base)
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
    const count = asInt(entry.count)
    const baseName = empty ? '' : itemBaseName(entry.name)
    const copies = count != null && count > 0 ? count : 1
    group.items.push({
      key: `${ring}-${group.items.length}`,
      location: ring,
      displayName: empty ? '' : String(entry.name || '').trim(),
      baseName,
      catalogName: baseName,
      tier: tierOfName(entry.name),
      id: entry.id == null ? '' : String(entry.id),
      count,
      copyCount: copies,
      stackedInSlot: false,
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
    .filter(({ row }) => row && effectiveKind(row) === kind)
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
      .filter((row) => row && effectiveKind(row) === 'unknown' && !isEmptyName(row.name_raw || row.name))
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

  const copies = []
  collectCopies(worn, 'worn', [CONTAINER_PLACE.worn], copies)
  for (const section of carried) {
    collectCopies(section.nodes, section.kind, [CONTAINER_PLACE[section.kind] || section.title], copies)
  }
  for (const group of keyrings) {
    collectCopies(group.items, 'keyring', [CONTAINER_PLACE.keyring], copies)
  }

  return {
    hasImport,
    fromTree,
    worn,
    carried,
    keyrings,
    otherSections: sections,
    copies,
    dragonHorde: dragonHordeStatus(meta, copies),
    merge: mergeableDuplicates(copies),
  }
}

function collectCopies(nodes, container, prefix, out) {
  for (const node of nodes || []) {
    const parts = node.location ? [...prefix, node.location] : [...prefix]
    if (!node.empty && node.displayName) {
      out.push({
        key: node.key,
        displayName: node.displayName,
        baseName: node.baseName || itemBaseName(node.displayName),
        catalogName: node.catalogName || node.baseName || itemBaseName(node.displayName),
        tier: node.tier ?? null,
        id: node.id || '',
        count: node.count,
        copyCount: node.copyCount || 1,
        stackedInSlot: !!node.stackedInSlot,
        unknown: !!node.unknown,
        container,
        place: parts.filter(Boolean).join(' · '),
      })
    }
    if (node.children?.length) collectCopies(node.children, container, parts, out)
  }
}

export function searchCharacterCopies(copies, query) {
  const tokens = String(query || '')
    .trim()
    .toLowerCase()
    .split(/[^a-z0-9']+/i)
    .filter((token) => token && !SEARCH_STOP.has(token))
  if (!tokens.length) return []
  return (copies || []).filter((copy) => {
    const hay = [copy.displayName, copy.baseName, copy.catalogName, copy.place, copy.container]
      .join(' ')
      .toLowerCase()
    return tokens.every((token) => hay.includes(token))
  })
}

function copyId(copy) {
  return String(copy?.id || '').trim()
}

function blankGroup(key, sample, id) {
  return {
    key,
    name: sample.baseName || sample.catalogName || sample.displayName,
    tier: sample.tier ?? null,
    id,
    unknown: false,
    catalogName: sample.catalogName || sample.baseName || sample.displayName,
    copies: [],
    stacked: false,
  }
}

function absorbCopy(group, copy) {
  if (copy.stackedInSlot) group.stacked = true
  if (copy.unknown) group.unknown = true
  group.copies.push(copy)
}

function finishMergeGroup(group, listed, omitted) {
  if (group.stacked) {
    omitted.push({ key: group.key, name: group.name, reason: 'stacked-in-one-slot' })
    return
  }
  const total = group.copies.reduce((sum, copy) => {
    const n = Number(copy.copyCount)
    return sum + (Number.isFinite(n) && n > 0 ? Math.trunc(n) : 1)
  }, 0)
  if (total < 2) return
  listed.push({ ...group, total })
}

export function mergeableDuplicates(copies) {
  const buckets = new Map()
  for (const copy of copies || []) {
    const name = itemBaseName(copy.baseName || copy.catalogName || copy.displayName).toLowerCase()
    if (!name || name === 'empty') continue
    const tier = copy.tier == null || copy.tier === '' ? '' : String(copy.tier)
    const key = `${name}\0${tier}`
    let bucket = buckets.get(key)
    if (!bucket) {
      bucket = { key, sample: copy, copies: [] }
      buckets.set(key, bucket)
    }
    bucket.copies.push(copy)
  }
  const listed = []
  const omitted = []
  for (const bucket of buckets.values()) {
    const ids = [...new Set(bucket.copies.map(copyId).filter(Boolean))]
    if (ids.length <= 1) {
      const id = ids[0] || ''
      const group = blankGroup(`${bucket.key}\0${id}`, bucket.sample, id)
      for (const copy of bucket.copies) absorbCopy(group, copy)
      finishMergeGroup(group, listed, omitted)
      continue
    }
    const unidentified = bucket.copies.filter((copy) => !copyId(copy))
    if (unidentified.length) {
      omitted.push({
        key: bucket.key,
        name: bucket.sample.baseName || bucket.sample.catalogName || bucket.sample.displayName,
        reason: 'ambiguous-id',
      })
    }
    for (const id of ids) {
      const group = blankGroup(`${bucket.key}\0${id}`, bucket.sample, id)
      for (const copy of bucket.copies) {
        if (copyId(copy) === id) absorbCopy(group, copy)
      }
      finishMergeGroup(group, listed, omitted)
    }
  }
  listed.sort((a, b) => String(a.name).localeCompare(String(b.name)) || String(a.id).localeCompare(String(b.id)))
  return { groups: listed, omitted, rule: MERGEABLE_DUPLICATE_RULE }
}

export function dragonHordeStatus(importMeta, copies) {
  const included = (copies || []).filter((copy) => copy.container === 'dragonhorde')
  if (included.length) {
    return {
      state: 'included',
      count: included.length,
      note: 'Dragon hoard rows in this import are included.',
    }
  }
  const raw = (importMeta?.unknown_rows || []).filter((row) => (
    isDragonHoardName(row?.header) || isDragonHoardName(row?.raw)
  ))
  if (raw.length) {
    return {
      state: 'unparsed',
      lines: raw.length,
      note: 'This import has a Dragon Hoard section that is not an item table the importer reads. Those lines stay under Other sections and are not listed as items.',
    }
  }
  return {
    state: 'absent',
    note: 'This inventory export has no dragon hoard item rows. A dump includes hoard items only while that window is open, and this file has none.',
  }
}

export function characterSlotSelector(key) {
  const safe = String(key ?? '').replace(/\\/g, '\\\\').replace(/"/g, '\\"')
  return `[data-character-slot="${safe}"]`
}

export function scrollCharacterSlotIntoView(key, doc) {
  const root = doc || (typeof document !== 'undefined' ? document : null)
  if (!root || key == null || key === '') return false
  const node = typeof root.querySelector === 'function'
    ? root.querySelector(characterSlotSelector(key))
    : null
  if (!node || typeof node.scrollIntoView !== 'function') return false
  node.scrollIntoView({ block: 'center', inline: 'nearest' })
  return true
}
