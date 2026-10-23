/**
 * Ask AI prompt text for 1.1.17.
 *
 * Numbers and stats are copied from objects the screen already has.
 * A missing value is written as unknown. It is not turned into 0.
 */

import { itemStatsAtLevel } from './itemUpgradeStats.js'
import { namesMatch } from './itemNames.js'
import { formatDuration, formatFightTime, formatTargets, formatZone } from './parserView.js'

export const GROK_HOME = 'https://grok.com/'
export const MAX_GROK_URL = 1900

const STAT_KEYS = [
  'AC', 'HP', 'MANA', 'END', 'STR', 'STA', 'AGI', 'DEX', 'WIS', 'INT', 'CHA', 'ATK',
  'Haste', 'DMG', 'DLY', 'HP_REGEN', 'MANA_REGEN', 'END_REGEN',
  'SVM', 'SVF', 'SVC', 'SVD', 'SVP', 'SVV',
]

const SECRET_KEY = /token|secret|authorization|api[_-]?key|password|bearer/i

export function askPlace(tab) {
  if (tab === 'parser') return 'parser'
  if (tab === 'bis') return 'bis'
  if (tab === 'sim') return 'sim'
  return 'gear'
}

export function askPlaceLabel(tab) {
  const place = askPlace(tab)
  if (place === 'parser') return 'Includes the selected Parser fight. Missing numbers stay unknown.'
  if (place === 'bis') return 'Includes the Best in Slot picks on this page. Missing stats stay unknown.'
  if (place === 'sim') return 'Includes the Simulator picks on this page. Missing stats stay unknown.'
  return 'Includes the current character and worn gear. Missing stats stay unknown.'
}

export function askPlaceholder(tab) {
  const place = askPlace(tab)
  if (place === 'parser') return 'Ask about the selected fight'
  if (place === 'bis') return 'Ask about these Best in Slot picks'
  if (place === 'sim') return 'Ask about these Simulator picks'
  return "Ask about this character's gear"
}

export function isGrokUrl(url) {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' && parsed.hostname === 'grok.com' && parsed.pathname === '/'
  } catch (_) {
    return false
  }
}

/** Prefill ?q= when the link stays short. Otherwise the caller copies the prompt. */
export function grokLink(prompt) {
  const text = String(prompt || '')
  const url = `https://grok.com/?q=${encodeURIComponent(text)}`
  if (url.length <= MAX_GROK_URL && isGrokUrl(url)) {
    return { url, prefilled: true, copy: false }
  }
  return { url: GROK_HOME, prefilled: false, copy: true }
}

export function scrubSecrets(text) {
  return String(text || '')
    .replace(/Bearer\s+\S+/gi, 'Bearer [redacted]')
    .replace(/\bxai-[A-Za-z0-9_-]{8,}\b/g, '[redacted]')
    .replace(/"(?:access_token|refresh_token|id_token)"\s*:\s*"[^"]*"/gi, '"token":"[redacted]"')
}

export async function deliverAsk({ prompt, askLocal, openUrl, copyText }) {
  let local = { mode: 'browser', reason: 'not-installed' }
  try {
    if (typeof askLocal === 'function') local = await askLocal(prompt)
  } catch (_) {
    local = { mode: 'browser', reason: 'failed' }
  }
  if (local && local.mode === 'answer' && typeof local.text === 'string' && local.text.trim()) {
    return { mode: 'answer', text: scrubSecrets(local.text).trim() }
  }
  const link = grokLink(prompt)
  const url = isGrokUrl(link.url) ? link.url : GROK_HOME
  let copied = false
  if (link.copy && typeof copyText === 'function') {
    try {
      copied = Boolean(await copyText(prompt))
    } catch (_) {
      copied = false
    }
  }
  if (typeof openUrl === 'function') {
    try {
      await openUrl(url)
    } catch (_) {
      /* the toast still tells the user what to paste */
    }
  }
  if (link.copy && copied) {
    return { mode: 'browser', url, copied: true, toast: 'Prompt copied. Paste it into Grok.' }
  }
  if (link.copy) {
    return {
      mode: 'browser',
      url,
      copied: false,
      toast: 'Could not copy the prompt. Select it below and paste it into Grok.',
      prompt,
    }
  }
  return { mode: 'browser', url, copied: false, toast: '' }
}

export function buildAskPrompt(tab, question, snapshot) {
  const asked = cleanLine(question, 2000)
  if (!asked) return { ok: false, reason: 'empty' }
  const place = askPlace(tab)
  const lines = [
    `Question: ${asked}`,
    '',
    'Use only the facts below. A stat or number that is not listed is unknown. Do not treat unknown as 0.',
    '',
  ]
  if (place === 'parser') lines.push(...parserLines(snapshot || {}))
  else if (place === 'bis') lines.push(...bisLines(snapshot || {}))
  else if (place === 'sim') lines.push(...simLines(snapshot || {}))
  else lines.push(...gearLines(snapshot || {}))
  let prompt = lines.join('\n').trim()
  if (prompt.length > 12000) {
    prompt = `${prompt.slice(0, 11800)}\nContext truncated. The rest is unknown.`
  }
  return { ok: true, place, prompt }
}

function gearLines(snapshot) {
  const lines = ['Context: current character and worn gear']
  lines.push(`Character: ${textOrUnknown(snapshot.character)}`)
  lines.push(`Classes: ${classText(snapshot.classes)}`)
  lines.push(`Level: ${levelText(snapshot.level)}`)
  lines.push(`Race: ${textOrUnknown(snapshot.race)}`)
  const slots = slotOrder(snapshot)
  const worn = []
  for (const slot of slots) {
    const name = cleanLine(snapshot.equipment?.[slot], 120)
    if (!name) continue
    worn.push(gearSlotLine(slot, name, snapshot))
  }
  if (!worn.length) {
    lines.push('Worn gear: unknown')
    return lines
  }
  lines.push(`Worn slots filled: ${worn.length}`)
  lines.push(...worn)
  return lines
}

function gearSlotLine(slot, name, snapshot) {
  const recorded = recordedUpgrade(snapshot.wornUpgrades?.[slot])
  const item = findNamed(snapshot.slotItems?.[slot], name)
  let stats = 'stats unknown'
  let upgrade = 'upgrade unknown'
  const scaled = statsForShown(item, recorded)
  if (recorded != null && scaled) {
    upgrade = `recorded +${recorded}`
    stats = catalogStats(scaled)
  } else if (item?.stats_plus0) {
    stats = `+0 catalog ${catalogStats(item.stats_plus0)}`
  }
  return `${slotLabel(slot)}: ${name}. ${upgrade}. ${stats}.`
}

function bisLines(snapshot) {
  const bis = snapshot.bis
  const lines = ['Context: Best in Slot picks']
  lines.push(`Character: ${textOrUnknown(snapshot.character)}`)
  lines.push(`Classes: ${classText(snapshot.classes)}`)
  if (!bis || !Array.isArray(bis.slots)) {
    lines.push('Best in Slot picks: unknown')
    return lines
  }
  lines.push(`Level: ${levelText(bis.character_level ?? snapshot.level)}`)
  lines.push(`Mode: ${textOrUnknown(bis.mode)}`)
  const upgrade = recordedUpgrade(bis.upgrade)
  lines.push(upgrade == null ? 'Upgrade: unknown' : `Upgrade: +${upgrade}`)
  const primary = listText(bis.primary_stats)
  if (primary) lines.push(`Primary: ${primary}`)
  const secondary = listText(bis.secondary_stats)
  if (secondary) lines.push(`Secondary: ${secondary}`)
  const tertiary = listText(bis.tertiary_stats)
  if (tertiary) lines.push(`Tertiary: ${tertiary}`)
  if (bis.maximize_hp_regen === true) lines.push('HP regen maximized: yes')
  for (const slot of bis.slots) {
    if (!slot || SECRET_KEY.test(String(slot.slot || ''))) continue
    lines.push(bisSlotLine(slot, upgrade))
  }
  if (!bis.slots.length) lines.push('Slots: unknown')
  return lines
}

function bisSlotLine(slot, upgrade) {
  const name = cleanLine(slot.name, 120)
  if (!name) return `${slotLabel(slot.slot)}: empty.`
  const zone = cleanLine(slot.zone, 80)
  const parts = [`${slotLabel(slot.slot)}: ${name}`]
  parts.push(zone ? `zone ${zone}` : 'zone unknown')
  if (Number.isFinite(Number(slot.haste))) parts.push(`haste ${Number(slot.haste)}%`)
  parts.push(bisStats(slot, upgrade))
  const alts = Array.isArray(slot.alts) ? slot.alts.map((alt) => cleanLine(alt?.name, 80)).filter(Boolean) : []
  if (alts.length) {
    const shown = alts.slice(0, 2).join(', ')
    const more = alts.length > 2 ? ` and ${alts.length - 2} more` : ''
    parts.push(`alternates ${shown}${more}`)
  }
  return `${parts.join('. ')}.`
}

function bisStats(slot, upgrade) {
  const at = slot.stats_at_upgrade
  if (at && typeof at === 'object' && Object.keys(at).length && upgrade != null) {
    return `+${upgrade} ${catalogStats(at)}`
  }
  if (upgrade === 0 && slot.stats_plus0) return `+0 ${catalogStats(slot.stats_plus0)}`
  if (upgrade === 10 && slot.stats_plus10) return `+10 ${catalogStats(slot.stats_plus10)}`
  const base = slot.stats_plus0 && typeof slot.stats_plus0 === 'object' ? catalogStats(slot.stats_plus0) : ''
  if (upgrade == null) {
    return base && !/^no listed|^stats unknown/.test(base)
      ? `upgrade unknown. +0 catalog ${base}`
      : 'upgrade unknown. stats unknown'
  }
  if (base && !/^no listed|^stats unknown/.test(base)) {
    return `stats at +${upgrade} unknown. +0 catalog ${base}`
  }
  return `stats at +${upgrade} unknown`
}

function simLines(snapshot) {
  const lines = ['Context: Simulator picks']
  lines.push(`Character: ${textOrUnknown(snapshot.character)}`)
  lines.push(`Classes: ${classText(snapshot.classes)}`)
  lines.push(`Level: ${levelText(snapshot.level)}`)
  lines.push(`Race: ${textOrUnknown(snapshot.race)}`)
  const build = cleanLine(snapshot.buildName, 80)
  if (build) lines.push(`Build name: ${build}`)
  const slots = slotOrder(snapshot)
  if (!slots.length) {
    lines.push('Simulator picks: unknown')
    return lines
  }
  let any = false
  for (const slot of slots) {
    const line = simSlotLine(slot, snapshot)
    if (!line) continue
    any = true
    lines.push(line)
  }
  if (!any) lines.push('Simulator picks: unknown')
  return lines
}

function simSlotLine(slot, snapshot) {
  const wornName = cleanLine(snapshot.equipment?.[slot], 120)
  const picked = selectedBisName(slot, snapshot)
  if (!wornName && !picked) return ''
  const worn = sideStats(slot, wornName, snapshot.wornUpgrades?.[slot], snapshot)
  const bis = sideStats(slot, picked, snapshot.bisUpgrades?.[slot], snapshot)
  const deltas = knownDeltas(worn.stats, bis.stats)
  const deltaText = deltas == null ? 'deltas unknown' : (deltas.length ? `deltas ${deltas.join(', ')}` : 'deltas none')
  return [
    `${slotLabel(slot)}:`,
    `worn ${worn.name}. ${worn.upgrade}. ${worn.statText}.`,
    `BiS pick ${bis.name}. ${bis.upgrade}. ${bis.statText}.`,
    `${deltaText}.`,
  ].join(' ')
}

function statsForShown(item, shown) {
  if (!item || shown == null) return null
  const plus0 = item.stats_plus0
  if (plus0 && typeof plus0 === 'object' && Object.keys(plus0).length) {
    const scaled = itemStatsAtLevel(item, shown)
    return scaled && Object.keys(scaled).length ? scaled : null
  }
  if (shown === 10 && item.stats_plus10 && typeof item.stats_plus10 === 'object' && Object.keys(item.stats_plus10).length) {
    return item.stats_plus10
  }
  return null
}

function sideStats(slot, name, rawUpgrade, snapshot) {
  if (!name) {
    return { name: 'empty', upgrade: 'upgrade unknown', stats: null, statText: 'stats unknown' }
  }
  const recorded = recordedUpgrade(rawUpgrade)
  const shown = recorded != null ? recorded : recordedUpgrade(snapshot.upgrade)
  const item = findNamed(snapshot.slotItems?.[slot], name)
  const stats = statsForShown(item, shown)
  let statText = 'stats unknown'
  if (stats) statText = catalogStats(stats)
  else if (item?.stats_plus0 && shown !== 0) {
    statText = `+0 catalog ${catalogStats(item.stats_plus0)}`
  }
  const upgrade = recorded != null
    ? `recorded +${recorded}`
    : (shown != null ? `shown at +${shown}` : 'upgrade unknown')
  return { name, upgrade, stats: stats && Object.keys(stats).length ? stats : null, statText }
}

function selectedBisName(slot, snapshot) {
  const override = cleanLine(snapshot.bisOverrides?.[slot], 120)
  if (override) return override
  const row = Array.isArray(snapshot.bis?.slots)
    ? snapshot.bis.slots.find((entry) => entry && entry.slot === slot)
    : null
  return cleanLine(row?.name, 120)
}

export function knownDeltas(wornStats, bisStats) {
  if (!wornStats || !bisStats || typeof wornStats !== 'object' || typeof bisStats !== 'object') return null
  const out = []
  for (const key of STAT_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(wornStats, key)) continue
    if (!Object.prototype.hasOwnProperty.call(bisStats, key)) continue
    const left = wornStats[key]
    const right = bisStats[key]
    if (typeof left !== 'number' || typeof right !== 'number') continue
    if (!Number.isFinite(left) || !Number.isFinite(right)) continue
    const delta = right - left
    if (!Number.isFinite(delta) || Math.abs(delta) < 1e-9) continue
    out.push(`${key} ${signed(delta)}`)
  }
  return out
}

function parserLines(snapshot) {
  const parser = snapshot.parser || {}
  const lines = ['Context: selected Parser fight']
  lines.push(`Character: ${textOrUnknown(parser.character || snapshot.character)}`)
  const fight = parser.fight
  if (!fight) {
    lines.push('No fight is selected. Fight summary: unknown.')
    return lines
  }
  if (parser.status === 'loading') {
    lines.push('Fight summary is still loading. Numbers: unknown.')
    return lines
  }
  if (parser.status === 'missing' || parser.status === 'error') {
    lines.push('The selected fight has no loaded summary. Fight summary: unknown.')
    return lines
  }
  lines.push(`Time: ${formatFightTime(fight.start_ts)}`)
  lines.push(`Zone: ${formatZone(fight)}`)
  lines.push(`Targets: ${formatTargets(fight.targets)}`)
  lines.push(`Duration: ${formatDuration(fight.duration_seconds)}`)
  lines.push(`Total damage: ${numberOrUnknown(fight.damage)}`)
  lines.push(`Your DPS: ${numberOrUnknown(fight.your_dps)}`)
  if (fight.player_died === true) lines.push('You died: yes')
  if (fight.open === true) lines.push('Fight is still open.')
  const detail = parser.detail
  const sources = Array.isArray(detail?.sources) ? detail.sources.filter((row) => row && !row.nested) : null
  if (!sources) {
    lines.push('Source breakdown: unknown')
    return lines
  }
  const shown = sources.slice(0, 6)
  if (!shown.length) {
    lines.push('Source breakdown: unknown')
    return lines
  }
  for (const row of shown) {
    const name = cleanLine(row.source, 80) || 'unknown'
    lines.push(`Source ${name}: damage ${numberOrUnknown(row.damage)}, DPS ${numberOrUnknown(row.dps)}`)
  }
  if (sources.length > shown.length) lines.push(`${sources.length - shown.length} more sources not listed.`)
  return lines
}

function catalogStats(stats) {
  if (!stats || typeof stats !== 'object') return 'stats unknown'
  const parts = []
  for (const key of STAT_KEYS) {
    if (SECRET_KEY.test(key)) continue
    if (!Object.prototype.hasOwnProperty.call(stats, key)) continue
    const value = stats[key]
    if (typeof value !== 'number' || !Number.isFinite(value) || value === 0) continue
    parts.push(`${key} ${formatNum(value)}`)
  }
  return parts.length ? parts.join(', ') : 'no listed catalog stats'
}

function findNamed(list, name) {
  if (!name) return null
  for (const item of list || []) {
    if (item && namesMatch(item.name, name)) return item
  }
  return null
}

function slotOrder(snapshot) {
  if (Array.isArray(snapshot.slots) && snapshot.slots.length) return snapshot.slots.filter(Boolean)
  return Object.keys(snapshot.equipment || {})
}

function slotLabel(slot) {
  if (slot === 'ANY1') return 'ANY1 (Any Slot)'
  if (slot === 'ANY2') return 'ANY2 (Any Slot)'
  return String(slot || 'unknown')
}

function classText(classes) {
  const names = Array.isArray(classes) ? classes.map((name) => cleanLine(name, 40)).filter(Boolean) : []
  return names.length ? names.join(', ') : 'unknown'
}

function levelText(level) {
  const value = Number(level)
  if (!Number.isFinite(value)) return 'unknown'
  return String(Math.trunc(value))
}

function recordedUpgrade(value) {
  if (value == null || value === '') return null
  const number = Number(value)
  if (!Number.isFinite(number)) return null
  return Math.max(0, Math.min(10, Math.trunc(number)))
}

function listText(values) {
  if (!Array.isArray(values)) return ''
  return values.map((value) => cleanLine(value, 24)).filter(Boolean).join(', ')
}

function textOrUnknown(value) {
  return cleanLine(value, 80) || 'unknown'
}

function numberOrUnknown(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'unknown'
  return formatNum(value)
}

function formatNum(value) {
  if (Number.isInteger(value)) return String(value)
  return String(Math.round(value * 10) / 10)
}

function signed(value) {
  const shown = formatNum(value)
  return value > 0 ? `+${shown}` : shown
}

function cleanLine(value, max) {
  if (value == null) return ''
  const text = String(value).replace(/[\r\n\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  if (!text || SECRET_KEY.test(text) && text.length > 40 && /token|bearer|xai-/i.test(text)) return ''
  return text.length > max ? `${text.slice(0, max)}…` : text
}
