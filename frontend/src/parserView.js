/**
 * Display helpers for the Parser tab.
 *
 * Combat numbers are passed through from the sidecar. This module does not
 * invent zones, targets, or damage. A missing zone or target is "unknown".
 *
 * Level is per 3-class loadout. The same character can be 50 and later 29
 * after a class swap. A lower later number is never an error.
 */

export const WHATS_NEW_ID = '1.1.0'

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

export const WHATS_NEW_TITLE = "What's new in 1.1.0"

export const WHATS_NEW_POINTS = [
  'The Parser tab reads your EverQuest Legends combat log from disk. It does not read game memory or send keystrokes to the game.',
  'Pick a character log, such as eqlog_Zasariz_qeynos.txt. Live follows the file while you play. Load old log replays a file already on disk and shows a progress bar.',
  'Each fight lists the time, the zone when the log recorded one, the targets, the duration, and total damage from you, your pet, and your group.',
  'The selected fight shows DPS and SDPS for you, your pet, and group members. Merge pets rolls a pet into its owner and still lists the pet underneath.',
  LEVEL_LOADOUT_NOTE,
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
  return 'Unknown'
}

/**
 * Rows for the DPS table: you, your pet, and group members.
 * When the API merged pets, each pet is a nested row under its owner.
 */
export function displaySources(detail) {
  const sources = Array.isArray(detail?.sources) ? detail.sources : []
  const rows = []
  for (const src of sources) {
    if (!src || typeof src !== 'object') continue
    const pets = Array.isArray(src.pets) ? src.pets.filter((pet) => pet && typeof pet === 'object') : []
    const keep = FRIENDLY.has(src.kind) || pets.length > 0
    if (!keep) continue
    rows.push({ ...src, nested: false, pets })
    for (const pet of pets) {
      rows.push({ ...pet, nested: true, kind: pet.kind || 'pet', pets: [] })
    }
  }
  return rows
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
