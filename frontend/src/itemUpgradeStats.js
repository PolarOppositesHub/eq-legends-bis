/** Upgrade scaling shared by Item Search chips and tooltip text.

Worn haste is tooltip base + integer level (eqlegendstools scaleTooltipLine).
AC/HP and the other scalable stats use scale_item_stat. Delay, elemental
bonus damage, effects, focus, slot, and class lines do not scale.
*/

export const SCALABLE_STAT_KEYS = new Set([
  'AC', 'HP', 'MANA', 'STR', 'STA', 'AGI', 'DEX', 'WIS', 'INT', 'CHA', 'END', 'ATK',
  'SVM', 'SVF', 'SVC', 'SVD', 'SVP', 'SVV',
  'HP_REGEN', 'MANA_REGEN', 'END_REGEN',
  'Haste',
])

const TIP_LABEL_TO_KEY = {
  'AC': 'AC',
  'HP': 'HP',
  'MANA': 'MANA',
  'END': 'END',
  'STR': 'STR',
  'STA': 'STA',
  'AGI': 'AGI',
  'DEX': 'DEX',
  'WIS': 'WIS',
  'INT': 'INT',
  'CHA': 'CHA',
  'ATK': 'ATK',
  'DMG': 'DMG',
  'HASTE': 'Haste',
  'SV FIRE': 'SVF',
  'SV COLD': 'SVC',
  'SV MAGIC': 'SVM',
  'SV POISON': 'SVP',
  'SV DISEASE': 'SVD',
  'SV VOID': 'SVV',
  'SVM': 'SVM',
  'SVF': 'SVF',
  'SVC': 'SVC',
  'SVP': 'SVP',
  'SVD': 'SVD',
  'SVV': 'SVV',
  'FIRE DMG': 'FIRE_DMG',
  'COLD DMG': 'COLD_DMG',
  'HP REGEN': 'HP_REGEN',
  'MANA REGEN': 'MANA_REGEN',
  'END REGEN': 'END_REGEN',
  'ATK DELAY': 'DLY',
}

// Longest labels first so "HP Regen" wins over "HP" and "Fire DMG" over "DMG".
const TIP_LABELS = Object.keys(TIP_LABEL_TO_KEY).sort((a, b) => b.length - a.length)
const TIP_LABEL_RE = new RegExp(
  `(?<![\\w])(?<!backstab\\s)(?<!base\\s)(${TIP_LABELS.join('|')})\\s*:\\s*([+-])?(\\d+)(\\s*%)?`,
  'gi',
)
const SKIP_TOOLTIP_LINE = /^(?:effect|clicky effect|click effect|focus effect|worn effect|proc effect|combat effect|clicky|focus|worn|proc)\s*:/i

export function clampUpgrade(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return 0
  return Math.max(0, Math.min(10, Math.trunc(v)))
}

export function isCatalogHasteKey(k) {
  return String(k || '').toLowerCase() === 'haste'
}

/** Match backend decode_local.scale_item_stat / engine.scale_stats_to_level. */
export function scaleItemStat(base, level) {
  const o = Number(base)
  if (!Number.isFinite(o)) return base
  if (!o || !level) return Number.isInteger(o) ? o : o
  const a = Math.floor(o * (1 + level / 10))
  if (o > 0) return Math.max(a, o + level)
  if (o < -10) return Math.ceil(o * Math.max(0, 10 - level) / 10)
  return Math.min(0, o + level)
}

/** eqlegendstools scaleTooltipLine: Haste% = tooltip base + integer upgrade. Not the AC curve. */
export function scaleWornHaste(base, level) {
  const o = Number(base)
  if (!Number.isFinite(o)) return base
  const n = o + clampUpgrade(level)
  return Number.isInteger(n) ? n : n
}

export function scaleStatsToLevel(stats0, level) {
  const lvl = clampUpgrade(level)
  const out = {}
  for (const [k, v] of Object.entries(stats0 || {})) {
    if (k === 'DMG') {
      const base = Number(v)
      if (!Number.isFinite(base)) continue
      out[k] = lvl === 0 ? base : Math.floor(base * (1 + lvl / 10))
    } else if (k === 'DLY' || k === 'FIRE_DMG' || k === 'COLD_DMG') {
      out[k] = Number(v) || 0
    } else if (isCatalogHasteKey(k)) {
      // Tooltip base + level. Stored stats_plus10.Haste copies +0, so it is not a measured +10.
      const base = Number(v)
      out[k] = Number.isFinite(base) ? scaleWornHaste(base, lvl) : v
    } else if (SCALABLE_STAT_KEYS.has(k)) {
      out[k] = scaleItemStat(v, lvl)
    } else {
      const n = Number(v)
      out[k] = Number.isFinite(n) ? n : v
    }
  }
  return out
}

/** Collapsed +10 line keeps stored AC/HP, but haste follows the same slider rule. */
export function previewStatsPlus10(item) {
  const s10 = { ...(item?.stats_plus10 || {}) }
  const s0 = item?.stats_plus0 || {}
  if (!Object.keys(s10).length) return scaleStatsToLevel(s0, 10)
  for (const [k, v] of Object.entries(s0)) {
    if (!isCatalogHasteKey(k)) continue
    const base = Number(v)
    const stored = Number(s10[k])
    if (!Number.isFinite(base)) continue
    if (Number.isFinite(stored) && stored !== base) continue
    s10[k] = scaleWornHaste(base, 10)
  }
  return s10
}

export function itemStatsAtLevel(item, level) {
  if (!item) return {}
  const s0 = item.stats_plus0
  if (s0 && typeof s0 === 'object' && Object.keys(s0).length) {
    return scaleStatsToLevel(s0, level)
  }
  const lvl = clampUpgrade(level)
  if (lvl >= 10) return item.stats_plus10 || item.stats_at_upgrade || {}
  if (lvl === 0) return item.stats_plus0 || item.stats_at_upgrade || {}
  return item.stats_at_upgrade || item.stats_plus10 || item.stats_plus0 || {}
}

function formatScaledNumber(n, sign) {
  const num = Number(n)
  const shown = Number.isInteger(num) ? String(num) : String(Math.round(num * 1000) / 1000)
  if (num < 0) return shown
  if (sign === '+') return `+${shown}`
  return shown
}

function scaledTooltipValue(key, base, level) {
  const lvl = clampUpgrade(level)
  if (key === 'DMG') return lvl === 0 ? base : Math.floor(base * (1 + lvl / 10))
  if (key === 'DLY' || key === 'FIRE_DMG' || key === 'COLD_DMG') return null
  if (isCatalogHasteKey(key)) return scaleWornHaste(base, lvl)
  if (SCALABLE_STAT_KEYS.has(key)) return scaleItemStat(base, lvl)
  return null
}

/** Rewrite scalable stat tokens in one tooltip line. Non-scaling lines stay as written. */
export function scaleTooltipLine(line, level) {
  const text = String(line ?? '')
  if (!text || SKIP_TOOLTIP_LINE.test(text)) return text
  return text.replace(TIP_LABEL_RE, (match, label, sign, digits, pct) => {
    const key = TIP_LABEL_TO_KEY[String(label).toUpperCase()]
    if (!key) return match
    const base = Number(`${sign === '-' ? '-' : ''}${digits}`)
    if (!Number.isFinite(base)) return match
    const scaled = scaledTooltipValue(key, base, level)
    if (scaled == null || !Number.isFinite(Number(scaled))) return match
    const body = formatScaledNumber(scaled, sign)
    const pctOut = pct ? (String(pct).startsWith(' ') ? ' %' : '%') : ''
    return `${label}: ${body}${pctOut}`
  })
}

export function scaleTooltipLines(lines, level) {
  return (lines || []).map((line) => scaleTooltipLine(line, level))
}
