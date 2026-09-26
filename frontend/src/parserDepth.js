/**
 * Parser tab depth: drill-down math, merged fights, history paging,
 * and clipboard / file text. Numbers are summed from the sidecar payload.
 * Nothing here invents a damage figure.
 *
 * Copy text is plain ASCII for EQ chat. The app only writes the clipboard.
 * It never sends keystrokes or text to the game.
 */

import {
  formatDamage,
  formatDuration,
  formatRate,
  formatTargets,
  formatZone,
  visibleDamage,
  visibleRate,
} from './parserView.js'

export const PARSER_DETAIL_TABS = [
  { id: 'damage', label: 'Damage' },
  { id: 'healing', label: 'Healing' },
  { id: 'tanking', label: 'Tanking' },
  { id: 'deaths', label: 'Deaths' },
  { id: 'resists', label: 'Resists' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'loot', label: 'Loot' },
]

export const FIGHT_PAGE_SIZE = 40
export const LOOT_PAGE_SIZE = 40
export const MERGE_LIMIT = 40
export const COPY_LINE_MAX = 220

export const LOOT_MODE_LABELS = {
  bag: 'Bag',
  autosold: 'Auto-sold',
  merged: 'Merged',
  stored_currency: 'Stored in currency',
  stored_depot: 'Stored in depot',
  stored_hoard: 'Stored in Dragon Hoard',
  given: 'Given',
  coin: 'Coin',
  payment: 'Payment',
  stored: 'Stored',
}

export const ABILITY_CATEGORY_LABELS = {
  melee: 'Melee',
  spell: 'Spell',
  dot: 'DoT',
  ds: 'Damage shield',
  miss: 'Miss',
  avoid: 'Avoid',
  heal: 'Heal',
}

const MARK_PREFIX = 'eql-parser-session-mark'

export function markStorageKey(character) {
  return `${MARK_PREFIX}:${typeof character === 'string' ? character : ''}`
}

export function categoryLabel(category) {
  if (!category) return 'Unknown'
  return ABILITY_CATEGORY_LABELS[category] || category
}

export function lootModeLabel(mode) {
  if (!mode) return 'Unknown'
  return LOOT_MODE_LABELS[mode] || mode
}

export function pct(part, whole) {
  const n = Number(part)
  const d = Number(whole)
  if (!Number.isFinite(n) || !Number.isFinite(d) || d <= 0) return null
  return (100 * n) / d
}

export function average(total, hits) {
  const n = Number(total)
  const d = Number(hits)
  if (!Number.isFinite(n) || !Number.isFinite(d) || d <= 0) return null
  return n / d
}

/** Hits, crits, average, and max for one attack or spell row. */
export function spellStats(row) {
  if (!row || typeof row !== 'object') return null
  const heal = row.spell != null && row.ability == null
  const hits = Number(row.hits) || 0
  const misses = Number(row.misses) || 0
  const crits = Number(row.crits) || 0
  const swings = hits + misses
  const total = heal ? Number(row.actual) || 0 : Number(row.damage) || 0
  return {
    name: heal ? String(row.spell) : String(row.ability || ''),
    category: heal ? (row.over_time ? 'heal' : 'heal') : (row.category || ''),
    overTime: !!row.over_time,
    heal,
    source: row.source || '',
    target: row.target || '',
    hits,
    misses,
    crits,
    hitPct: pct(hits, swings),
    critPct: pct(crits, hits),
    total,
    full: heal ? Number(row.full) || 0 : null,
    overheal: heal ? Number(row.overheal) || 0 : null,
    max: heal ? null : Number(row.max_hit) || 0,
    avg: average(total, hits),
  }
}

function num(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function earlier(a, b) {
  if (!a) return b || null
  if (!b) return a
  return a <= b ? a : b
}

function later(a, b) {
  if (!a) return b || null
  if (!b) return a
  return a >= b ? a : b
}

function abilityKey(row) {
  return [row.source || '', row.category || '', row.ability || ''].join('\0')
}

function addAbility(map, row) {
  if (!row || typeof row !== 'object') return
  const key = abilityKey(row)
  const prev = map.get(key)
  if (!prev) {
    map.set(key, {
      source: row.source,
      category: row.category,
      ability: row.ability,
      damage: num(row.damage),
      hits: num(row.hits),
      crits: num(row.crits),
      misses: num(row.misses),
      max_hit: num(row.max_hit),
    })
    return
  }
  prev.damage += num(row.damage)
  prev.hits += num(row.hits)
  prev.crits += num(row.crits)
  prev.misses += num(row.misses)
  prev.max_hit = Math.max(prev.max_hit, num(row.max_hit))
}

function sortedAbilities(map) {
  return [...map.values()].sort((a, b) => (
    b.damage - a.damage || b.hits - a.hits || String(a.source).localeCompare(String(b.source))
    || String(a.category).localeCompare(String(b.category)) || String(a.ability).localeCompare(String(b.ability))
  ))
}

function blankSource(name, kind) {
  return {
    source: name,
    kind: kind || 'unknown',
    owner: null,
    damage: 0,
    damage_taken: 0,
    hits: 0,
    misses: 0,
    crits: 0,
    max_hit: 0,
    heals: 0,
    heals_full: 0,
    overheal: 0,
    melee: 0,
    spell: 0,
    dot: 0,
    ds: 0,
    active_seconds: 0,
    first_ts: null,
    last_ts: null,
    pets: [],
    abilities: [],
  }
}

const SOURCE_SUM_KEYS = [
  'damage', 'damage_taken', 'hits', 'misses', 'crits', 'heals', 'heals_full',
  'overheal', 'melee', 'spell', 'dot', 'ds', 'active_seconds',
]

function absorbSource(host, row) {
  for (const key of SOURCE_SUM_KEYS) host[key] += num(row[key])
  host.max_hit = Math.max(host.max_hit, num(row.max_hit))
  host.first_ts = earlier(host.first_ts, row.first_ts)
  host.last_ts = later(host.last_ts, row.last_ts)
  if (row.owner) host.owner = row.owner
  if (row.kind && row.kind !== 'unknown') host.kind = row.kind
}

function finishSource(row, fightSeconds) {
  const swings = row.hits + row.misses
  const active = row.hits ? Math.max(1, row.active_seconds) : 0
  row.dps = active ? row.damage / active : 0
  row.sdps = fightSeconds > 0 ? row.damage / fightSeconds : 0
  row.hit_pct = swings ? (100 * row.hits) / swings : 0
  row.crit_pct = row.hits ? (100 * row.crits) / row.hits : 0
  row.active_seconds = active
  return row
}

function sumKeyed(rows, keyFn, add) {
  const map = new Map()
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue
    const key = keyFn(row)
    const prev = map.get(key)
    if (!prev) map.set(key, { ...row })
    else add(prev, row)
  }
  return [...map.values()]
}

/**
 * Combine fight-detail payloads. Duration is the sum of each fight.
 * Gaps between fights are not counted as active time.
 * Pet rows stay nested. Their damage is already on the owner when merge pets is on,
 * so pets are not added into the owner a second time.
 */
export function mergeFightDetails(details) {
  const list = (Array.isArray(details) ? details : []).filter((row) => row && typeof row === 'object')
  if (!list.length) return null
  if (list.length === 1) {
    const only = list[0]
    return { ...only, merged_ids: [only.id], merged_count: 1 }
  }

  const abilityMap = new Map()
  const top = new Map()
  const nested = new Map()
  let duration = 0
  const zones = []
  const targets = []
  const ids = []
  let startTs = null
  let endTs = null
  let playerDied = false
  let open = false
  let instance = null
  const healRows = []
  const incoming = []
  const avoidance = []
  const runes = []
  const selfDamage = []
  const resists = []
  const deaths = []
  const procItems = []
  const multi = []
  let multiNote = ''

  for (const detail of list) {
    ids.push(detail.id)
    duration += num(detail.duration_seconds)
    startTs = earlier(startTs, detail.start_ts)
    endTs = later(endTs, detail.end_ts)
    playerDied = playerDied || !!detail.player_died
    open = open || !!detail.open
    if (detail.zone && !zones.includes(detail.zone)) zones.push(detail.zone)
    if (list.indexOf(detail) === 0) instance = detail.instance || null
    if (Array.isArray(detail.targets)) {
      for (const entry of detail.targets) {
        const name = typeof entry === 'string' ? entry : entry?.name
        if (name && !targets.includes(name)) targets.push(name)
      }
    }
    const listed = Array.isArray(detail.abilities) ? detail.abilities : []
    if (listed.length) {
      for (const ability of listed) addAbility(abilityMap, ability)
    }
    for (const row of detail.sources || []) {
      if (!row?.source) continue
      const host = top.get(row.source) || blankSource(row.source, row.kind)
      absorbSource(host, row)
      top.set(row.source, host)
      if (!listed.length) {
        for (const ability of row.abilities || []) addAbility(abilityMap, ability)
      }
      for (const pet of row.pets || []) {
        if (!pet?.source) continue
        const byOwner = nested.get(row.source) || new Map()
        const petHost = byOwner.get(pet.source) || blankSource(pet.source, pet.kind || 'pet')
        absorbSource(petHost, pet)
        petHost.kind = 'pet'
        petHost.owner = pet.owner || row.source
        byOwner.set(pet.source, petHost)
        nested.set(row.source, byOwner)
        if (!listed.length) {
          for (const ability of pet.abilities || []) addAbility(abilityMap, ability)
        }
      }
    }
    healRows.push(...(detail.healing?.rows || []))
    incoming.push(...(detail.tanking?.incoming || []))
    avoidance.push(...(detail.tanking?.avoidance || []))
    runes.push(...(detail.tanking?.runes || []))
    selfDamage.push(...(detail.tanking?.self_damage || []))
    resists.push(...(detail.resists || []))
    deaths.push(...(detail.deaths || []))
    procItems.push(...(detail.procs?.items || []))
    multi.push(...(detail.multi_attack?.sources || []))
    if (!multiNote && detail.multi_attack?.note) multiNote = detail.multi_attack.note
  }

  const abilities = sortedAbilities(abilityMap)
  const bySource = new Map()
  for (const ability of abilities) {
    const bucket = bySource.get(ability.source) || []
    bucket.push(ability)
    bySource.set(ability.source, bucket)
  }
  const fightSeconds = Math.max(1, duration)
  const sources = []
  for (const host of top.values()) {
    host.abilities = bySource.get(host.source) || []
    const pets = [...(nested.get(host.source)?.values() || [])].map((pet) => {
      pet.abilities = bySource.get(pet.source) || pet.abilities || []
      return finishSource(pet, fightSeconds)
    })
    pets.sort((a, b) => b.damage - a.damage || String(a.source).localeCompare(String(b.source)))
    host.pets = pets
    sources.push(finishSource(host, fightSeconds))
  }
  sources.sort((a, b) => b.damage - a.damage || String(a.source).localeCompare(String(b.source)))

  const heals = sumKeyed(
    healRows,
    (row) => [row.source, row.target, row.spell, row.over_time ? '1' : '0'].join('\0'),
    (prev, row) => {
      prev.actual = num(prev.actual) + num(row.actual)
      prev.full = num(prev.full) + num(row.full)
      prev.hits = num(prev.hits) + num(row.hits)
      prev.crits = num(prev.crits) + num(row.crits)
      prev.overheal = Math.max(0, num(prev.full) - num(prev.actual))
    },
  )
  for (const row of heals) row.overheal = Math.max(0, num(row.full) - num(row.actual))
  heals.sort((a, b) => num(b.actual) - num(a.actual) || String(a.source).localeCompare(String(b.source)))

  const sumPair = (rows, key) => rows.reduce((total, row) => total + num(row[key]), 0)
  const direct = heals.filter((row) => !row.over_time)
  const hot = heals.filter((row) => row.over_time)

  const incomingRows = sumKeyed(
    incoming,
    (row) => [row.target, row.source, row.category, row.ability].join('\0'),
    (prev, row) => {
      prev.damage = num(prev.damage) + num(row.damage)
      prev.hits = num(prev.hits) + num(row.hits)
      prev.max_hit = Math.max(num(prev.max_hit), num(row.max_hit))
    },
  )
  incomingRows.sort((a, b) => num(b.damage) - num(a.damage))

  const avoidanceRows = sumKeyed(
    avoidance,
    (row) => [row.target, row.kind].join('\0'),
    (prev, row) => { prev.count = num(prev.count) + num(row.count) },
  )
  const runeRows = sumKeyed(
    runes,
    (row) => row.source || '',
    (prev, row) => {
      prev.absorption = num(prev.absorption) + num(row.absorption)
      prev.count = num(prev.count) + num(row.count)
    },
  )
  const selfRows = sumKeyed(
    selfDamage,
    (row) => row.target || '',
    (prev, row) => {
      prev.damage = num(prev.damage) + num(row.damage)
      prev.hits = num(prev.hits) + num(row.hits)
    },
  )
  const resistRows = sumKeyed(
    resists,
    (row) => [row.source, row.target, row.spell].join('\0'),
    (prev, row) => { prev.count = num(prev.count) + num(row.count) },
  )
  resistRows.sort((a, b) => num(b.count) - num(a.count))

  const procRows = sumKeyed(
    procItems,
    (row) => [row.source, row.item].join('\0'),
    (prev, row) => { prev.count = num(prev.count) + num(row.count) },
  )
  procRows.sort((a, b) => num(b.count) - num(a.count))
  const procCount = procRows.reduce((total, row) => total + num(row.count), 0)

  const multiRows = sumKeyed(
    multi,
    (row) => row.source || '',
    (prev, row) => {
      prev.singles = num(prev.singles) + num(row.singles)
      prev.doubles = num(prev.doubles) + num(row.doubles)
      prev.triples = num(prev.triples) + num(row.triples)
      prev.flurries = num(prev.flurries) + num(row.flurries)
      prev.rounds = num(prev.rounds) + num(row.rounds)
    },
  )
  for (const row of multiRows) {
    const rounds = num(row.rounds)
    row.double_rate = rounds ? num(row.doubles) / rounds : 0
    row.triple_rate = rounds ? num(row.triples) / rounds : 0
    row.flurry_rate = rounds ? num(row.flurries) / rounds : 0
  }

  const friendly = new Set(['self', 'group', 'pet'])
  const outgoing = sources.reduce((total, row) => (
    friendly.has(row.kind) ? total + num(row.damage) : total
  ), 0)
  const taken = sources.reduce((total, row) => (
    friendly.has(row.kind) ? total + num(row.damage_taken) : total
  ), 0)

  return {
    id: ids[0],
    merged_ids: ids,
    merged_count: ids.length,
    character: list[0].character,
    zone: zones.length === 1 ? zones[0] : null,
    zones,
    instance: zones.length === 1 ? instance : null,
    start_ts: startTs,
    end_ts: endTs,
    duration_seconds: duration,
    targets,
    open,
    player_died: playerDied,
    merge_pets: list[0].merge_pets !== false,
    totals: {
      damage: outgoing,
      damage_taken: taken,
      dps: outgoing / fightSeconds,
      sdps: outgoing / fightSeconds,
    },
    sources,
    abilities,
    healing: {
      rows: heals,
      totals: {
        actual: sumPair(heals, 'actual'),
        full: sumPair(heals, 'full'),
        overheal: sumPair(heals, 'overheal'),
        direct_actual: sumPair(direct, 'actual'),
        direct_full: sumPair(direct, 'full'),
        direct_overheal: sumPair(direct, 'overheal'),
        hot_actual: sumPair(hot, 'actual'),
        hot_full: sumPair(hot, 'full'),
        hot_overheal: sumPair(hot, 'overheal'),
      },
    },
    tanking: {
      incoming: incomingRows,
      avoidance: avoidanceRows,
      runes: runeRows,
      self_damage: selfRows,
    },
    deaths,
    resists: resistRows,
    procs: {
      count: procCount,
      per_minute: procCount ? (procCount * 60) / fightSeconds : 0,
      items: procRows,
    },
    multi_attack: {
      estimate: true,
      note: multiNote,
      sources: multiRows,
    },
  }
}

export function filterFights(fights, query) {
  const q = String(query || '').trim().toLowerCase()
  const rows = Array.isArray(fights) ? fights : []
  if (!q) return rows
  return rows.filter((fight) => {
    const zone = String(fight?.zone || '').toLowerCase()
    const targets = formatTargets(fight?.targets).toLowerCase()
    return zone.includes(q) || targets.includes(q)
  })
}

export function pageSlice(items, page, size = FIGHT_PAGE_SIZE) {
  const rows = Array.isArray(items) ? items : []
  const pageSize = size > 0 ? size : FIGHT_PAGE_SIZE
  const pages = Math.max(1, Math.ceil(rows.length / pageSize))
  const current = Math.min(Math.max(1, Number(page) || 1), pages)
  const start = (current - 1) * pageSize
  return {
    page: current,
    pages,
    total: rows.length,
    start: rows.length ? start + 1 : 0,
    end: Math.min(rows.length, start + pageSize),
    rows: rows.slice(start, start + pageSize),
  }
}

export function zoneSession(fights, fightId) {
  const chrono = (Array.isArray(fights) ? fights : [])
    .filter((fight) => fight && fight.start_ts)
    .slice()
    .sort((a, b) => String(a.start_ts).localeCompare(String(b.start_ts)) || num(a.id) - num(b.id))
  const idx = chrono.findIndex((fight) => fight.id === fightId)
  if (idx < 0) return []
  const zone = chrono[idx].zone || ''
  let start = idx
  let end = idx
  while (start > 0 && (chrono[start - 1].zone || '') === zone) start -= 1
  while (end < chrono.length - 1 && (chrono[end + 1].zone || '') === zone) end += 1
  return chrono.slice(start, end + 1)
}

export function sliceFromMark(fights, markTs) {
  if (!markTs) return []
  return (Array.isArray(fights) ? fights : []).filter((fight) => fight?.start_ts && fight.start_ts >= markTs)
}

export function capIds(ids, limit = MERGE_LIMIT) {
  const seen = []
  const have = new Set()
  for (const id of ids || []) {
    if (id == null || have.has(id)) continue
    have.add(id)
    seen.push(id)
    if (seen.length >= limit) break
  }
  return seen
}

export function scopeNames(sources) {
  const names = new Set()
  for (const row of sources || []) {
    if (row?.source) names.add(String(row.source).toLowerCase())
  }
  return names
}

export function inScope(name, names) {
  if (!name) return false
  return names.has(String(name).toLowerCase())
}

function asciiClip(value) {
  const clean = String(value ?? '').replace(/[^\x20-\x7e]/g, '')
  if (clean.length <= COPY_LINE_MAX) return clean
  return `${clean.slice(0, COPY_LINE_MAX - 3)}...`
}

/**
 * Compact parse for EQ chat. ASCII only, short lines, no tells or says.
 */
export function formatParseText(detail, sources, meta = {}) {
  if (!detail) return ''
  const lines = []
  const bits = []
  const targets = formatTargets(detail.targets)
  const zone = detail.zones && detail.zones.length > 1
    ? detail.zones.join(', ')
    : formatZone(detail)
  const dur = formatDuration(detail.duration_seconds)
  if (targets && targets !== 'unknown') bits.push(targets)
  if (zone && zone !== 'unknown') bits.push(zone)
  if (dur && dur !== 'unknown') bits.push(dur)
  let head = 'Parse'
  const merged = Number(meta.mergedCount || detail.merged_count) || 0
  if (merged > 1) head += ` (merged ${merged})`
  lines.push(asciiClip(bits.length ? `${head}: ${bits.join(' | ')}` : head))
  const rows = (Array.isArray(sources) ? sources : []).filter((row) => row && !row.nested)
  for (const row of rows.slice(0, 8)) {
    lines.push(asciiClip(`${row.source}  ${formatDamage(row.damage)} dmg  ${formatRate(row.dps)} DPS`))
    const abilities = Array.isArray(row.abilities) ? row.abilities : []
    for (const ability of abilities.filter((item) => num(item.damage) > 0).slice(0, 6)) {
      lines.push(asciiClip(
        `  ${ability.ability}  ${formatDamage(ability.damage)}  ${num(ability.hits)} hits  max ${formatDamage(ability.max_hit)}`,
      ))
    }
  }
  lines.push(asciiClip(
    `Total  ${formatDamage(visibleDamage(rows))} dmg  ${formatRate(visibleRate(rows, detail.duration_seconds))} DPS`,
  ))
  return lines.join('\n')
}

function tsvCell(value) {
  return String(value ?? '').replace(/[\t\r\n]/g, ' ')
}

export function formatParseTsv(detail, sources) {
  const header = ['Source', 'Kind', 'Ability', 'Category', 'Damage', 'Hits', 'Misses', 'Crits', 'Max', 'DPS', 'SDPS']
  const lines = [header.join('\t')]
  for (const row of sources || []) {
    if (!row) continue
    lines.push([
      row.nested ? row.source : row.source,
      row.kind || '',
      '',
      '',
      num(row.damage),
      num(row.hits),
      num(row.misses),
      num(row.crits),
      num(row.max_hit),
      formatRate(row.dps),
      formatRate(row.sdps),
    ].map(tsvCell).join('\t'))
    for (const ability of row.abilities || []) {
      lines.push([
        row.source,
        row.kind || '',
        ability.ability || '',
        ability.category || '',
        num(ability.damage),
        num(ability.hits),
        num(ability.misses),
        num(ability.crits),
        num(ability.max_hit),
        '',
        '',
      ].map(tsvCell).join('\t'))
    }
  }
  if (detail?.healing?.rows) {
    lines.push(['Source', 'Target', 'Spell', 'Over time', 'Actual', 'Full', 'Overheal', 'Hits', 'Crits', '', ''].join('\t'))
    for (const row of detail.healing.rows) {
      lines.push([
        row.source, row.target, row.spell, row.over_time ? 'yes' : 'no',
        num(row.actual), num(row.full), num(row.overheal), num(row.hits), num(row.crits), '', '',
      ].map(tsvCell).join('\t'))
    }
  }
  return lines.join('\n')
}

function csvCell(value) {
  const text = String(value ?? '')
  if (/[",\r\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`
  return text
}

export function formatParseCsv(detail, sources) {
  return formatParseTsv(detail, sources)
    .split('\n')
    .map((line) => line.split('\t').map(csvCell).join(','))
    .join('\n')
}

function htmlEscape(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function formatParseHtml(detail, sources) {
  const title = htmlEscape(formatParseText(detail, sources).split('\n')[0] || 'Parse')
  const body = []
  body.push('<table><thead><tr><th>Source</th><th>Damage</th><th>DPS</th><th>SDPS</th><th>Hits</th><th>Max</th></tr></thead><tbody>')
  for (const row of sources || []) {
    if (!row || row.nested) continue
    body.push(
      `<tr><td>${htmlEscape(row.source)}</td><td>${formatDamage(row.damage)}</td><td>${formatRate(row.dps)}</td>`
      + `<td>${formatRate(row.sdps)}</td><td>${num(row.hits)}</td><td>${formatDamage(row.max_hit)}</td></tr>`,
    )
    for (const ability of row.abilities || []) {
      body.push(
        `<tr><td>${htmlEscape(row.source)} / ${htmlEscape(ability.ability)}</td><td>${formatDamage(ability.damage)}</td>`
        + `<td></td><td></td><td>${num(ability.hits)}</td><td>${formatDamage(ability.max_hit)}</td></tr>`,
      )
    }
  }
  body.push('</tbody></table>')
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${title}</title>`
    + '<style>body{background:#111;color:#f2f2f2;font-family:Segoe UI,sans-serif}'
    + 'h1{color:#d4af37;font-size:1.1rem}table{border-collapse:collapse;width:100%}'
    + 'th,td{border-bottom:1px solid #3a3a3a;padding:0.35rem;text-align:left}'
    + 'th{color:#a8a8a8;font-size:0.75rem}</style></head><body>'
    + `<h1>${title}</h1>${body.join('')}`
    + '<p>Copied from EQ Legends BiS. Paste into the game yourself. This file does not send anything to EverQuest.</p>'
    + '</body></html>'
}

export function stitchTimelines(parts) {
  const list = (Array.isArray(parts) ? parts : []).filter((part) => part && Array.isArray(part.buckets))
  if (!list.length) return { buckets: [], bin_seconds: 1, stitched: false }
  if (list.length === 1) return { buckets: list[0].buckets, bin_seconds: list[0].bin_seconds || 1, stitched: false }
  let offset = 0
  const buckets = []
  for (const part of list) {
    const bin = part.bin_seconds || 1
    for (const row of part.buckets) {
      buckets.push({ ...row, t: offset + num(row.t) })
    }
    const last = part.buckets.length ? num(part.buckets[part.buckets.length - 1].t) + bin : 0
    offset += last + bin
  }
  return { buckets, bin_seconds: list[0].bin_seconds || 1, stitched: true }
}

export function chartValue(bucket, scope, binSeconds) {
  const bin = binSeconds > 0 ? binSeconds : 1
  const you = num(bucket?.you)
  const pets = num(bucket?.pets)
  const group = num(bucket?.group)
  const other = num(bucket?.other)
  const incomingYou = num(bucket?.incoming)
  const incomingGroup = num(bucket?.incoming_group)
  let outgoing = you + pets
  let incoming = incomingYou
  if (scope === 'self') outgoing = you
  else if (scope === 'pets') outgoing = pets
  else if (scope === 'all' || scope === 'raid') {
    outgoing = you + pets + group + other
    incoming = incomingYou + incomingGroup
  } else if (scope === 'group') {
    outgoing = you + pets + group
    incoming = incomingYou + incomingGroup
  }
  return { outgoing: outgoing / bin, incoming: incoming / bin }
}

export function spellBucketAmount(bucket) {
  if (!bucket) return 0
  return num(bucket.you) + num(bucket.pets) + num(bucket.group) + num(bucket.other)
    + num(bucket.incoming) + num(bucket.incoming_group) + num(bucket.heals)
}

export function timelinePeak(buckets, scope, binSeconds) {
  let bestOut = 0
  let bestOutT = 0
  let bestIn = 0
  let bestInT = 0
  for (const row of buckets || []) {
    const point = chartValue(row, scope, binSeconds)
    if (point.outgoing >= bestOut) {
      bestOut = point.outgoing
      bestOutT = num(row.t)
    }
    if (point.incoming >= bestIn) {
      bestIn = point.incoming
      bestInT = num(row.t)
    }
  }
  return { outgoing: bestOut, outgoingT: bestOutT, incoming: bestIn, incomingT: bestInT }
}

export function upsertFights(prev, fresh) {
  const map = new Map()
  for (const row of prev || []) {
    if (row && row.id != null) map.set(row.id, row)
  }
  for (const row of fresh || []) {
    if (row && row.id != null) map.set(row.id, row)
  }
  return [...map.values()].sort((a, b) => (
    String(b.start_ts || '').localeCompare(String(a.start_ts || '')) || num(b.id) - num(a.id)
  ))
}

export function lootInWindow(events, startTs, endTs) {
  const rows = Array.isArray(events) ? events : []
  if (!startTs) return rows
  const end = endTs || startTs
  return rows.filter((row) => row?.ts && row.ts >= startTs && row.ts <= end)
}

export async function copyText(text) {
  if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    await navigator.clipboard.writeText(text)
    return true
  }
  return false
}

export function downloadText(filename, text, mime) {
  if (typeof document === 'undefined' || typeof URL === 'undefined' || typeof Blob === 'undefined') return false
  const blob = new Blob([text], { type: mime || 'text/plain' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
  return true
}
