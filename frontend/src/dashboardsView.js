/**
 * Display helpers for the tracking dashboards.
 * Numbers come from the sidecar. A missing rate or pace stays "unknown".
 */

export const MULTI_CLASS_CAVEAT =
  'Level follows each class loadout. Swapping classes can drop the level, for example 50 then 10. Both readings are kept. This is not one character level.'

export const XP_HONESTY =
  'The log records an experience percent, not raw experience points. Pace is levels of progress. A line with no percent is left out of the sum.'

export function dropRateLabel(loots, kills) {
  const lootN = Number(loots)
  const killN = Number(kills)
  if (!Number.isFinite(killN) || killN <= 0 || !Number.isFinite(lootN) || lootN < 0) {
    return { text: 'unknown', rate: null }
  }
  return { text: `${lootN} / ${killN}`, rate: lootN / killN }
}

export function formatLevelsPerHour(value) {
  if (value == null || value === '') return 'unknown'
  const n = Number(value)
  if (!Number.isFinite(n)) return 'unknown'
  return `${n.toFixed(2)} levels of progress / hour`
}

export function formatHours(hours) {
  if (hours == null || hours === '') return 'unknown'
  const n = Number(hours)
  if (!Number.isFinite(n) || n < 0) return 'unknown'
  if (n === 0) return '0m'
  const totalMin = Math.round(n * 60)
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  if (h <= 0) return `${m}m`
  return `${h}h ${m}m`
}

/** Live toasts only. A replay, or a payload that is not marked live, yields nothing. */
export function toastsFromStream(event, options = {}) {
  const live = options.live !== false && event && event.live === true
  if (!live) return []
  const toast = event.toast
  if (!toast || toast.live !== true) return []
  if (toast.kind === 'level' && toast.level != null) return [toast]
  if (toast.kind === 'loot' && toast.item) return [toast]
  return []
}

export function toastText(toast) {
  if (!toast) return ''
  if (toast.kind === 'level') return `Level ${toast.level}`
  const reasons = Array.isArray(toast.reasons) ? toast.reasons.join(', ') : ''
  return reasons ? `${toast.item} (${reasons})` : String(toast.item || '')
}

export function conLine(consider) {
  if (!consider) return 'No consider yet.'
  const mob = consider.mob || 'unknown mob'
  const con = consider.con || 'unknown'
  const level = consider.level == null ? 'level unknown' : `Lvl ${consider.level}`
  return `${mob} — ${con} (${level})`
}
