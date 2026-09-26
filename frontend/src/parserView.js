/**
 * Display helpers for the Parser tab.
 *
 * Combat numbers are passed through from the sidecar. This module does not
 * invent zones, targets, or damage. A missing zone or target is "unknown".
 *
 * Level is per 3-class loadout. The same character can be 50 and later 29
 * after a class swap. A lower later number is never an error.
 */

export const WHATS_NEW_ID = '1.1.1'

export const PARSER_EMPTY = {
  title: 'No combat logs found',
  logOn:
    'In game, type /log on. EverQuest Legends writes Logs\\eqlog_name_server.txt (for example eqlog_Zasariz_qeynos.txt). Logging stays on across logins.',
  folder:
    'Check the EQ install folder setting. It must be the game folder that contains a Logs folder, not a character folder inside it.',
  filters:
    'Check chat filters. Channels filtered out of chat are not written to the log, so the file can exist and still have no combat lines.',
}

export const LEVEL_LOADOUT_NOTE =
  'Level follows each 3-class loadout. The same character can be 50 and later 29 after a class swap. Both readings are kept.'

export const WHATS_NEW_TITLE = "What's new in 1.1.1"

export const WHATS_NEW_POINTS = [
  'After updating, the app automatically rebuilds the existing 1.1.0 parse from the log, so there is nothing to redo.',
  'Each fight keeps damage by attack and spell, healing, tanking, deaths, resists, and loot. Open a row for the breakdown, and use the timeline.',
  'Item Search quest names that said "not in Quest Hub" now open the quest. Woven Skull Cap shows Wizard Test of Focus.',
  'Fight history keeps everything by default. A full, long log is about 64 MB. The Parser tab can clear history for one character.',
  'The Parser tab tracks pets and your group. Limit a fight to Self, Group, Pets, or All.',
  'The desktop and Start Menu icons refresh to the dragon-eye seal on install and update.',
  'Merge selected fights. Copy the parse as text or TSV, or save CSV and HTML. Browse older fights in the history list.',
]

export const CREDITS = [
  {
    id: 'eqlwiki',
    title: 'eqlwiki',
    href: 'https://eqlwiki.com/',
    body:
      'Item, mob, quest, and command text from the EverQuest Legends Wiki (eqlwiki.com), and images fetched from that wiki, are used under the Creative Commons Attribution-ShareAlike 4.0 International license (CC BY-SA 4.0).',
    licenseHref: 'https://creativecommons.org/licenses/by-sa/4.0/',
    licenseLabel: 'CC BY-SA 4.0',
  },
  {
    id: 'eqlegendstools',
    title: 'eqlegendstools.com',
    href: 'https://eqlegendstools.com/',
    body:
      'Catalog item stats and planner data are decoded from eqlegendstools.com. A name with no decoded stat is shown without one. Stats are never invented.',
  },
]

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const FRIENDLY = new Set(['self', 'group', 'pet'])

export function logOptionLabel(log) {
  const character = text(log?.character) || 'Unknown character'
  const server = text(log?.server)
  const name = text(log?.name) || 'eqlog'
  const who = server ? `${character} · ${server}` : character
  return `${who} — ${name}`
}

/** Wall-clock digits from the log prefix. No timezone conversion. */
export function formatFightTime(iso) {
  if (typeof iso !== 'string') return 'unknown'
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(iso.trim())
  if (!match) return 'unknown'
  const month = MONTHS[Number(match[2]) - 1]
  if (!month) return 'unknown'
  return `${month} ${Number(match[3])}, ${match[1]} ${match[4]}:${match[5]}:${match[6]}`
}

export function formatDuration(seconds) {
  const n = Number(seconds)
  if (!Number.isFinite(n) || n < 0) return 'unknown'
  const total = Math.round(n)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }
  return `${minutes}:${String(secs).padStart(2, '0')}`
}

export function formatZone(fight) {
  const zone = text(fight?.zone)
  if (!zone) return 'unknown'
  const inst = fight?.instance
  if (!inst || typeof inst !== 'object' || Array.isArray(inst)) return zone
  const extra = []
  if (text(inst.scope)) extra.push(text(inst.scope))
  if (inst.number != null && inst.number !== '' && Number.isFinite(Number(inst.number))) {
    extra.push(String(inst.number))
  }
  if (text(inst.tier)) extra.push(text(inst.tier))
  return extra.length ? `${zone} · ${extra.join(' · ')}` : zone
}

export function formatTargets(targets) {
  const names = []
  if (Array.isArray(targets)) {
    for (const entry of targets) {
      const name = typeof entry === 'string' ? text(entry) : text(entry?.name)
      if (name) names.push(name)
    }
  }
  if (!names.length) return 'unknown'
  if (names.length <= 4) return names.join(', ')
  return `${names.slice(0, 3).join(', ')} +${names.length - 3} more`
}

export function formatDamage(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '0'
  const rounded = Math.round(v)
  const sign = rounded < 0 ? '-' : ''
  return sign + String(Math.abs(rounded)).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

export function formatRate(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '0.0'
  return (Math.round(v * 10) / 10).toFixed(1)
}

export function sourceKindLabel(kind) {
  if (kind === 'self') return 'You'
  if (kind === 'pet') return 'Pet'
  if (kind === 'group') return 'Group'
  if (kind === 'candidate') return 'Candidate'
  if (kind === 'other') return 'Player'
  if (kind === 'npc') return 'NPC'
  return 'Unknown'
}

export const SOURCE_SCOPES = [
  { id: 'self', label: 'Self' },
  { id: 'group', label: 'Group' },
  { id: 'pets', label: 'Pets' },
  { id: 'raid', label: 'Raid' },
  { id: 'all', label: 'All' },
]

export const PET_LEADER_HINT = 'Ask group members to type /pet leader.'

export const RAID_SCOPE_NOTE =
  'Raid is your allowlist plus players who damaged the same NPC. Automatic raid rosters wait until a real raid log is sampled.'

const PET_EVIDENCE = {
  tell: 'Binding tell',
  leader: '/pet leader',
  charm: 'Your Charm',
  warder_name: 'Warder name',
  manual: 'Set by you',
  nominate: 'Nominated in chat',
}

export function petEvidenceLabel(evidence) {
  if (!evidence) return ''
  return PET_EVIDENCE[evidence] || evidence
}

/**
 * Rows for the DPS table: you, your pet, and group members.
 * When the API merged pets, each pet is a nested row under its owner.
 */
export function displaySources(detail, options = {}) {
  const includeOthers = !!options.includeOthers
  const sources = Array.isArray(detail?.sources) ? detail.sources : []
  const rows = []
  for (const src of sources) {
    if (!src || typeof src !== 'object') continue
    const pets = Array.isArray(src.pets) ? src.pets.filter((pet) => pet && typeof pet === 'object') : []
    const keep = FRIENDLY.has(src.kind) || pets.length > 0 || (includeOthers && src.kind && src.kind !== 'unknown')
    if (!keep) continue
    rows.push({ ...src, nested: false, pets })
    for (const pet of pets) {
      rows.push({ ...pet, nested: true, kind: pet.kind || 'pet', pets: [] })
    }
  }
  return rows
}

/**
 * SELF / GROUP / PETS / RAID / ALL.
 * GROUP is you, log group, allowlist, and pets already rolled onto those rows.
 * RAID adds the allowlist and players who damaged this fight. It does not
 * invent a raid roster. A candidate pet is not merged into an owner.
 */
export function sourcesForScope(detail, scope, allowlist = []) {
  const id = SOURCE_SCOPES.some((item) => item.id === scope) ? scope : 'group'
  const includeOthers = id === 'all' || id === 'raid'
  const rows = displaySources(detail, { includeOthers })
  const allow = new Set(
    (Array.isArray(allowlist) ? allowlist : [])
      .map((name) => (typeof name === 'string' ? name.trim().toLowerCase() : ''))
      .filter(Boolean),
  )
  if (id === 'all') return rows
  if (id === 'self') return rows.filter((row) => row.kind === 'self' && !row.nested)
  if (id === 'pets') return rows.filter((row) => row.kind === 'pet' || row.nested)
  if (id === 'raid') {
    return rows.filter((row) => {
      if (row.kind === 'self' || row.kind === 'group' || row.kind === 'pet' || row.nested) return true
      if (allow.has(String(row.source || '').toLowerCase())) return true
      if (row.kind === 'other' && Number(row.damage) > 0) return true
      return false
    })
  }
  return rows.filter((row) => row.kind === 'self' || row.kind === 'group' || row.kind === 'pet' || row.nested)
}

/**
 * Sum damage for the rows on screen.
 * Merge pets folds a pet into its owner and still lists the pet underneath.
 * Skip that nested row when the owner is also shown, so it is not counted twice.
 * Pets scope shows only those nested rows, so their damage is the total.
 */
export function visibleDamage(rows) {
  if (!Array.isArray(rows)) return 0
  const coveredByOwner = new Set()
  for (const row of rows) {
    if (!row || row.nested) continue
    const pets = Array.isArray(row.pets) ? row.pets : []
    for (const pet of pets) {
      const name = typeof pet?.source === 'string' ? pet.source.trim().toLowerCase() : ''
      if (name) coveredByOwner.add(name)
    }
  }
  return rows.reduce((sum, row) => {
    if (!row) return sum
    const name = typeof row.source === 'string' ? row.source.trim().toLowerCase() : ''
    if (row.nested && name && coveredByOwner.has(name)) return sum
    const damage = Number(row.damage)
    return sum + (Number.isFinite(damage) ? damage : 0)
  }, 0)
}

/** Fight-length rate for the rows the scope is showing. */
export function visibleRate(rows, seconds) {
  const duration = Number(seconds)
  if (!Number.isFinite(duration) || duration <= 0) return 0
  return visibleDamage(rows) / duration
}

export function loadoutsFor(name, loadouts) {
  if (!name || !Array.isArray(loadouts)) return []
  const key = String(name).toLowerCase()
  return loadouts.filter((row) => row && String(row.name || '').toLowerCase() === key)
}

export function loadoutText(rows) {
  if (!Array.isArray(rows) || !rows.length) return ''
  return rows
    .map((row) => {
      const classes = text(row.classes)
      const level = row.level == null || row.level === '' ? '' : String(row.level)
      return [classes, level].filter(Boolean).join(' ')
    })
    .filter(Boolean)
    .join(' · ')
}

/**
 * Two level readings for one character. A drop is a loadout change.
 * `error` is always false.
 */
export function describeLevelChange(earlier, later) {
  const from = Number(earlier)
  const to = Number(later)
  if (!Number.isFinite(from) || !Number.isFinite(to)) {
    return { error: false, text: '' }
  }
  if (to < from) {
    return {
      error: false,
      text: `Level ${from} then ${to}. Level follows the 3-class loadout, so a lower number after a class swap is kept.`,
    }
  }
  if (to > from) return { error: false, text: `Level ${from} then ${to}.` }
  return { error: false, text: `Level ${from}.` }
}

function text(value) {
  if (typeof value !== 'string') return ''
  return value.trim()
}
