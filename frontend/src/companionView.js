/**
 * Companion display helpers.
 * A missing duration, respawn, map, stat, or resist cap stays "unknown".
 * Level and class entries are keyed by loadout.
 */

export const COMPANION_BUFF_NOTE =
  'A cast line does not start a timer. Duration is a number you enter for this class loadout, or the time between a start and a worn-off line in your log. Otherwise it is unknown.'

export const COMPANION_RESPAWN_NOTE =
  'Respawn time is a number you enter. Time between two kills is not a respawn.'

export const COMPANION_MAP_NOTE =
  'A map link is shown only when a zone file already has one. Otherwise the map is unknown.'

export const COMPANION_EXALTATION_NOTE =
  'Stats appear only when the catalog already has them. No best exaltation is chosen. A target you type stays on this class loadout.'

export const COMPANION_RESIST_NOTE =
  'Resist cap is unknown. A missing item or race is not added as 0.'

export const COMPANION_SHARE_NOTE =
  'Export leaves out sign-in tokens. The feedback zip is logs and settings, with tokens removed.'

export function loadoutKey(classes, level) {
  const names = (Array.isArray(classes) ? classes : [])
    .map((name) => String(name || '').trim())
    .filter(Boolean)
  const levelText = level == null || level === '' ? 'unknown' : String(level)
  if (!names.length) return `unknown classes @ ${levelText}`
  return `${names.join(' / ')} @ ${levelText}`
}

export function wornResistRows(equipment, upgrades) {
  const eq = equipment && typeof equipment === 'object' ? equipment : {}
  const levels = upgrades && typeof upgrades === 'object' ? upgrades : {}
  const rows = []
  for (const [slot, value] of Object.entries(eq)) {
    const name = typeof value === 'string' ? value : (value && value.name) || ''
    const cleaned = String(name || '').trim()
    if (!cleaned) continue
    const upgrade = levels[slot]
    rows.push({
      slot,
      name: cleaned,
      upgrade: upgrade == null || upgrade === '' ? null : Number(upgrade),
    })
  }
  return rows
}

export function exaltationCandidates(items) {
  const rows = Array.isArray(items) ? items : []
  return rows.filter((row) => {
    const name = String(row?.name || row?.name_raw || '')
    const label = String(row?.socket_label || '')
    return /\(exaltation\)\s*$/i.test(name) || /^Slot(?:7|8|9|10) /.test(label)
  }).map((row) => ({
    name: row.name || row.name_raw || '',
    name_raw: row.name_raw || '',
    socket_label: row.socket_label || null,
    socket_index: row.socket_index ?? null,
    location_raw: row.location_raw || '',
    tier: row.tier ?? null,
    id: row.id || '',
  }))
}

export function buffOverlayText(payload) {
  const rows = Array.isArray(payload?.active) ? payload.active : []
  if (!rows.length) return 'No tracked buff or debuff. Duration stays unknown until you enter one for this loadout.'
  return rows.map((row) => {
    const who = row.target || 'unknown'
    const remaining = row.remaining_text || 'unknown'
    return `${row.name} on ${who} · ${remaining}`
  }).join('\n')
}

export function remainingLabel(text) {
  if (text == null || text === '') return 'unknown'
  return String(text)
}

/** Drop secret-shaped keys before a profile leaves the page. The server drops them again. */
export function redactProfile(value) {
  if (Array.isArray(value)) return value.map(redactProfile)
  if (!value || typeof value !== 'object') {
    if (typeof value === 'string' && /^bearer\s+\S+/i.test(value)) return ''
    return value
  }
  const out = {}
  for (const [key, item] of Object.entries(value)) {
    if (/token|secret|password|authorization|credential|cookie|api_key|refresh/i.test(key)) continue
    out[key] = redactProfile(item)
  }
  return out
}
