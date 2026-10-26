/**
 * Ask AI prompt text for 1.1.18.
 *
 * Numbers and stats are copied from objects the screen already has.
 * A missing value is written as unknown. It is not turned into 0.
 */

import { loadoutKey } from './companionView.js'
import { itemStatsAtLevel } from './itemUpgradeStats.js'
import { namesMatch } from './itemNames.js'
import { formatDuration, formatFightTime, formatPerSecond, formatTargets, formatZone } from './parserView.js'

export const GROK_HOME = 'https://grok.com/'
export const MAX_GROK_URL = 1900
export const URL_MAX_LENGTH = 1800
export const SHORT_PROMPT_MAX = 160
export const PASTE_HINT = 'Copied. Paste it into the Grok tab that just opened. The full context is on the clipboard, not in the web address.'
export const ASK_TIMEOUT_MS = 90000

/** Same chat needles as backend/tests/test_parser.py _CHAT. */
export const CHAT_LINE_NEEDLES = [
  " says, '",
  " say, '",
  " shouts, '",
  " shout, '",
  " auctions, '",
  " auction, '",
  'out of character',
  "told you, '",
  "tells you, '",
  'you told ',
  'tells the guild',
  'tells the group',
  'tells the raid',
]

const SHORT_BASE = 'EQ Legends question. The full context is on the clipboard. Paste it into this chat.'

const VIEW_LABELS = {
  overview: 'Overview',
  loot: 'Loot',
  leveling: 'Leveling',
  raids: 'Raid targets',
  companion: 'Companion',
  maps: 'Maps',
  bis: 'Best in Slot',
  sim: 'Simulator',
  upgrades: 'Upgrade Priority',
  requirements: 'Requirements',
  wishlist: 'Wish list',
  character: 'Character',
  currencies: 'Currencies',
  quests: 'Quest Hub',
  mobs: 'Mobs',
  search: 'Item Search',
  parser: 'Parser',
  alerts: 'Alerts',
}

export const CLI_STATE_TEXT = {
  not_installed: 'Grok Build CLI is not installed.',
  not_signed_in: 'Grok Build CLI is installed and not signed in.',
  ready: 'Grok Build CLI is installed and signed in.',
  unknown: 'Grok Build CLI sign-in status is unknown.',
}

export function isChatLine(line) {
  const lowered = String(line || '').toLowerCase()
  return CHAT_LINE_NEEDLES.some((needle) => lowered.includes(needle))
}

export function scrubChat(text) {
  return String(text ?? '')
    .split(/\r?\n/)
    .filter((line) => !isChatLine(line))
    .join('\n')
}

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

/** The clipboard gets the full pack. The URL only gets a short prompt. */
export function grokLink(prompt) {
  const url = grokUrl(prompt)
  return {
    url,
    prefilled: url.startsWith('https://grok.com/?q='),
    copy: true,
  }
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
  if (typeof copyText === 'function') {
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
  if (copied) {
    return { mode: 'browser', url, copied: true, toast: PASTE_HINT }
  }
  return {
    mode: 'browser',
    url,
    copied: false,
    toast: 'Could not copy the prompt. Select it below and paste it into Grok.',
    prompt,
  }
}

function questionForPrompt(question) {
  const lines = String(question ?? '').split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  if (!lines.length) return { ok: false, text: '' }
  const kept = lines.filter((line) => !isChatLine(line))
  if (!kept.length) return { ok: true, text: '(left out because it was a chat line)' }
  const asked = cleanLine(kept.join(' '), 2000)
  if (!asked) return { ok: false, text: '' }
  return { ok: true, text: asked }
}

export function buildAskPrompt(tab, question, snapshot) {
  const asked = questionForPrompt(question)
  if (!asked.ok) return { ok: false, reason: 'empty' }
  const place = askPlace(tab)
  const lines = [
    `Question: ${asked.text}`,
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
  const shown = sources.slice(0, 8)
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

function packText(value) {
  if (value == null) return ''
  return String(value).trim()
}

function numberText(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'unknown'
  return String(n)
}

export function viewLabel(id) {
  return VIEW_LABELS[id] || (packText(id) ? packText(id) : 'unknown')
}

function wornPackLines(equipment, upgrades) {
  const eq = equipment && typeof equipment === 'object' ? equipment : null
  if (!eq) return ['unknown']
  const levels = upgrades && typeof upgrades === 'object' ? upgrades : {}
  const lines = []
  for (const [slot, value] of Object.entries(eq)) {
    const name = typeof value === 'string' ? value : (value && value.name) || ''
    const cleaned = packText(name)
    if (!cleaned) continue
    const tier = levels[slot]
    const tierText = tier == null || tier === '' || !Number.isFinite(Number(tier)) ? 'tier unknown' : `+${Number(tier)}`
    lines.push(`${slot}: ${cleaned} (${tierText})`)
    if (lines.length >= 40) break
  }
  return lines.length ? lines : ['none in the last import']
}

function bisNameLines(slots, upgrade) {
  if (!Array.isArray(slots) || !slots.length) return ['unknown']
  const level = upgrade == null || upgrade === '' ? 'unknown' : String(upgrade)
  return slots.slice(0, 40).map((slot) => {
    const name = packText(slot?.name) || 'unknown'
    const id = packText(slot?.slot) || 'slot'
    return `${id}: ${name} (list at +${level})`
  })
}

function currencyLines(view) {
  if (!view || typeof view !== 'object') return ['unknown']
  const rows = []
  const push = (row) => {
    if (!row || !row.name) return
    const bags = Number.isFinite(Number(row.bags)) ? String(row.bags) : 'unknown'
    const storage = Number.isFinite(Number(row.storage)) ? String(row.storage) : 'unknown'
    const total = Number.isFinite(Number(row.total)) ? String(row.total) : 'unknown'
    if (bags === '0' && storage === '0' && total === '0') return
    rows.push(`${row.name}: bags ${bags}, storage ${storage}, total ${total}`)
  }
  for (const row of view.motes || []) push(row)
  push(view.void_touched)
  for (const row of view.wind_runes || []) push(row)
  if (!rows.length) return ['Currencies tab loaded. Every shown count is 0.']
  return rows.slice(0, 40)
}

function targetText(targets) {
  if (!Array.isArray(targets) || !targets.length) return 'unknown'
  const names = targets.map((entry) => (typeof entry === 'string' ? entry : entry?.name)).map(packText).filter(Boolean)
  return names.length ? names.join(', ') : 'unknown'
}

function parseLines(parse) {
  if (!parse || typeof parse !== 'object') return ['unknown']
  const totals = parse.totals && typeof parse.totals === 'object' ? parse.totals : {}
  const lines = [
    `Fight id: ${parse.id == null || parse.id === '' ? 'unknown' : String(parse.id)}`,
    `Zone: ${packText(parse.zone) || 'unknown'}`,
    `Targets: ${targetText(parse.targets)}`,
    `Duration seconds: ${numberText(parse.duration_seconds)}`,
    `Friendly damage: ${numberText(totals.damage)}`,
    `DPS: ${Number.isFinite(Number(totals.dps)) ? formatPerSecond(totals.dps) : 'unknown'}`,
  ]
  const sources = Array.isArray(parse.sources) ? parse.sources.filter((row) => row && !row.nested).slice(0, 8) : []
  if (!sources.length) {
    lines.push('Sources: unknown')
  } else {
    lines.push('Sources:')
    for (const row of sources) {
      const name = packText(row?.name || row?.source) || 'unknown'
      const kind = packText(row?.kind) || 'unknown'
      const damage = numberText(row?.damage)
      const dps = Number.isFinite(Number(row?.dps)) ? formatPerSecond(row.dps) : 'unknown'
      lines.push(`- ${name} (${kind}): damage ${damage}, DPS ${dps}`)
    }
  }
  return lines
}

export function compactFightSummary(detail) {
  if (!detail || typeof detail !== 'object') return null
  const sources = Array.isArray(detail.sources)
    ? detail.sources.filter((row) => row && !row.nested).slice(0, 8).map((row) => ({
      name: row?.name || row?.source || '',
      kind: row?.kind || '',
      damage: row?.damage,
      dps: row?.dps,
    }))
    : []
  const zone = packText(detail.zone) || (Array.isArray(detail.zones) ? detail.zones.map(packText).filter(Boolean).join(', ') : '')
  return {
    id: detail.id ?? null,
    zone,
    targets: detail.targets || [],
    duration_seconds: detail.duration_seconds,
    totals: detail.totals || null,
    sources,
  }
}

function parseFromSnapshot(snap) {
  if (snap.parse && typeof snap.parse === 'object') return snap.parse
  const summary = compactFightSummary(snap.parser?.detail)
  const fight = snap.parser?.fight || null
  if (!summary && !fight) return null
  return {
    ...(summary || {}),
    id: summary?.id ?? fight?.id ?? null,
    zone: summary?.zone || fight?.zone || '',
    targets: (summary?.targets && summary.targets.length) ? summary.targets : (fight?.targets || []),
    duration_seconds: summary?.duration_seconds ?? fight?.duration_seconds,
    totals: summary?.totals || (fight && fight.damage != null ? { damage: fight.damage, dps: fight.your_dps } : null),
    sources: summary?.sources || [],
  }
}

function richContextLines(snap) {
  if (!snap.slotItems && !snap.bis && !snap.parser) return []
  const place = askPlace(snap.view || snap.tab)
  if (place === 'parser') return parserLines(snap)
  if (place === 'bis') return bisLines(snap)
  if (place === 'sim') return simLines(snap)
  return gearLines(snap)
}

export function buildContextPack(snapshot, question) {
  const snap = snapshot && typeof snapshot === 'object' ? snapshot : {}
  const classes = Array.isArray(snap.classes) ? snap.classes : []
  const lines = [
    'EQ Legends BiS context',
    `View: ${viewLabel(snap.view || snap.tab)}`,
    `Character: ${packText(snap.character) || 'unknown'}`,
    `Loadout: ${loadoutKey(classes, snap.level)}`,
    'Level and classes are for this loadout only.',
    '',
    'Worn gear from the last inventory import:',
    ...wornPackLines(snap.equipment, snap.wornUpgrades).map((line) => `- ${line}`),
    '',
    'Best in Slot names already chosen in the app:',
    ...bisNameLines(snap.bisSlots, snap.bisUpgrade).map((line) => `- ${line}`),
    '',
    'Currency counts (bags from import + currency storage = total):',
    ...currencyLines(snap.currencies).map((line) => `- ${line}`),
    '',
    'Parse:',
    ...parseLines(parseFromSnapshot(snap)).map((line) => (line.startsWith('- ') || line === 'Sources:' ? line : `- ${line}`)),
  ]
  const rich = richContextLines(snap)
  if (rich.length) {
    lines.push('')
    lines.push(...rich)
  }
  lines.push('')
  lines.push('Question:')
  const questionLines = String(question ?? '').split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  const kept = questionLines.filter((line) => !isChatLine(line))
  if (!questionLines.length) lines.push('(none yet)')
  else if (!kept.length) lines.push('(left out because it was a chat line)')
  else lines.push(...kept)
  lines.push('')
  lines.push('A missing number is unknown. Do not treat a missing number as 0.')
  return scrubChat(lines.join('\n')).replace(/\n{3,}/g, '\n\n').trim()
}

export function shortPrompt(question) {
  const q = scrubChat(question).replace(/\s+/g, ' ').trim()
  let text = SHORT_BASE
  if (q && !isChatLine(q)) text = `${SHORT_BASE} Question: ${q}`
  if (text.length > SHORT_PROMPT_MAX) text = text.slice(0, SHORT_PROMPT_MAX)
  return text
}

export function grokUrl(question) {
  let prompt = shortPrompt(question)
  let url = `https://grok.com/?q=${encodeURIComponent(prompt)}`
  while (url.length > URL_MAX_LENGTH && prompt.length > 0) {
    prompt = prompt.slice(0, -1)
    url = `https://grok.com/?q=${encodeURIComponent(prompt)}`
  }
  if (url.length > URL_MAX_LENGTH || !url.startsWith('https://grok.com/')) return GROK_HOME
  return url
}

export function prepareAsk(snapshot, question) {
  return {
    pack: buildContextPack(snapshot, question),
    url: grokUrl(question),
    hint: PASTE_HINT,
  }
}

export function formatCliAnswer(result) {
  if (!result) return { label: '', body: '' }
  const session = result.sessionId ? ` Session id: ${result.sessionId}.` : ''
  return {
    label: `Grok returned JSON.${session} The docs name sessionId. The answer text field is not documented, so the whole object is shown.`,
    body: result.raw || '',
  }
}
