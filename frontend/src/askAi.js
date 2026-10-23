/**
 * Ask AI context pack and grok.com link.
 * Chat needles match backend/tests/test_parser.py _CHAT.
 * Full context stays on the clipboard. The URL only gets a short prompt.
 * ?q on grok.com is undocumented.
 */

import { loadoutKey } from './companionView.js'
import { formatPerSecond } from './parserView.js'

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

export const URL_MAX_LENGTH = 1800
export const SHORT_PROMPT_MAX = 160
export const PASTE_HINT = 'Copied. Paste it into the Grok tab that just opened. The full context is on the clipboard, not in the web address.'
export const ASK_TIMEOUT_MS = 90000

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

function text(value) {
  if (value == null) return ''
  return String(value).trim()
}

function numberText(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'unknown'
  return String(n)
}

export function viewLabel(id) {
  return VIEW_LABELS[id] || (text(id) ? text(id) : 'unknown')
}

function wornLines(equipment, upgrades) {
  const eq = equipment && typeof equipment === 'object' ? equipment : null
  if (!eq) return ['unknown']
  const levels = upgrades && typeof upgrades === 'object' ? upgrades : {}
  const lines = []
  for (const [slot, value] of Object.entries(eq)) {
    const name = typeof value === 'string' ? value : (value && value.name) || ''
    const cleaned = text(name)
    if (!cleaned) continue
    const tier = levels[slot]
    const tierText = tier == null || tier === '' || !Number.isFinite(Number(tier)) ? 'tier unknown' : `+${Number(tier)}`
    lines.push(`${slot}: ${cleaned} (${tierText})`)
    if (lines.length >= 40) break
  }
  return lines.length ? lines : ['none in the last import']
}

function bisLines(slots, upgrade) {
  if (!Array.isArray(slots) || !slots.length) return ['unknown']
  const level = upgrade == null || upgrade === '' ? 'unknown' : String(upgrade)
  return slots.slice(0, 40).map((slot) => {
    const name = text(slot?.name) || 'unknown'
    const id = text(slot?.slot) || 'slot'
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
  const names = targets.map((entry) => (typeof entry === 'string' ? entry : entry?.name)).map(text).filter(Boolean)
  return names.length ? names.join(', ') : 'unknown'
}

function parseLines(parse) {
  if (!parse || typeof parse !== 'object') return ['unknown']
  const totals = parse.totals && typeof parse.totals === 'object' ? parse.totals : {}
  const lines = [
    `Fight id: ${parse.id == null || parse.id === '' ? 'unknown' : String(parse.id)}`,
    `Zone: ${text(parse.zone) || 'unknown'}`,
    `Targets: ${targetText(parse.targets)}`,
    `Duration seconds: ${numberText(parse.duration_seconds)}`,
    `Friendly damage: ${numberText(totals.damage)}`,
    `DPS: ${Number.isFinite(Number(totals.dps)) ? formatPerSecond(totals.dps) : 'unknown'}`,
  ]
  const sources = Array.isArray(parse.sources) ? parse.sources.slice(0, 8) : []
  if (!sources.length) {
    lines.push('Sources: unknown')
  } else {
    lines.push('Sources:')
    for (const row of sources) {
      const name = text(row?.name) || 'unknown'
      const kind = text(row?.kind) || 'unknown'
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
    ? detail.sources.slice(0, 8).map((row) => ({
      name: row?.name || row?.source || '',
      kind: row?.kind || '',
      damage: row?.damage,
      dps: row?.dps,
    }))
    : []
  const zone = text(detail.zone) || (Array.isArray(detail.zones) ? detail.zones.map(text).filter(Boolean).join(', ') : '')
  return {
    id: detail.id ?? null,
    zone,
    targets: detail.targets || [],
    duration_seconds: detail.duration_seconds,
    totals: detail.totals || null,
    sources,
  }
}

export function buildContextPack(snapshot, question) {
  const snap = snapshot && typeof snapshot === 'object' ? snapshot : {}
  const classes = Array.isArray(snap.classes) ? snap.classes : []
  const lines = [
    'EQ Legends BiS context',
    `View: ${viewLabel(snap.view)}`,
    `Character: ${text(snap.character) || 'unknown'}`,
    `Loadout: ${loadoutKey(classes, snap.level)}`,
    'Level and classes are for this loadout only.',
    '',
    'Worn gear from the last inventory import:',
    ...wornLines(snap.equipment, snap.wornUpgrades).map((line) => `- ${line}`),
    '',
    'Best in Slot names already chosen in the app:',
    ...bisLines(snap.bisSlots, snap.bisUpgrade).map((line) => `- ${line}`),
    '',
    'Currency counts (bags from import + currency storage = total):',
    ...currencyLines(snap.currencies).map((line) => `- ${line}`),
    '',
    'Parse:',
    ...parseLines(snap.parse).map((line) => (line.startsWith('- ') || line === 'Sources:' ? line : `- ${line}`)),
    '',
    'Question:',
  ]
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
  if (url.length > URL_MAX_LENGTH || !url.startsWith('https://grok.com/')) return 'https://grok.com/'
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
