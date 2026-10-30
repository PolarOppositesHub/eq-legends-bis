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

/** Pages the home screen can open. Each id is already in the side menu. */
export const HOME_JUMPS = [
  { id: 'loot', label: 'Loot' },
  { id: 'leveling', label: 'Leveling' },
  { id: 'raids', label: 'Raid targets' },
  { id: 'parser', label: 'Parser' },
  { id: 'bis', label: 'Best in Slot' },
  { id: 'search', label: 'Item Search' },
]

/** Class loadout line from the overview payload. A missing class or level stays unknown. */
export function homeLoadout(leveling) {
  const classes = Array.isArray(leveling?.classes)
    ? leveling.classes.map((name) => String(name || '').trim()).filter(Boolean)
    : []
  const classText = classes.length ? classes.join(' / ') : 'classes unknown'
  const level = leveling?.level == null || leveling.level === '' ? 'level unknown' : String(leveling.level)
  return `${classText} · ${level}`
}

/** Short fight state for the home header. Uses the status the log already stored. */
export function homeFightStatus(mob) {
  const status = mob?.status
  if (status === 'fighting') return 'Fighting'
  if (status === 'between fights') return 'Between fights'
  if (status === 'no fight yet') return 'No fight yet'
  return 'No fight open'
}

/** Mob card line. Names come from the open fight. Anything else uses the status. */
export function homeMobLine(mob) {
  if (mob?.status === 'fighting') {
    const names = (Array.isArray(mob.names) ? mob.names : []).map((name) => String(name || '').trim()).filter(Boolean)
    return names.length ? names.join(', ') : 'unknown'
  }
  return homeFightStatus(mob)
}

/** One decimal, matching the rest of the app. A missing rate stays unknown. */
export function homeDpsText(value) {
  if (value == null || value === '') return 'unknown'
  const n = Number(value)
  if (!Number.isFinite(n)) return 'unknown'
  return `${n.toFixed(1)} DPS`
}

export function conLine(consider) {
  if (!consider) return 'No consider yet.'
  const mob = consider.mob || 'unknown mob'
  const con = consider.con || 'unknown'
  const level = consider.level == null ? 'level unknown' : `Lvl ${consider.level}`
  return `${mob} — ${con} (${level})`
}
