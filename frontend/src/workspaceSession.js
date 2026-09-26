/**
 * Working-session snapshot for EQ Legends BiS.
 *
 * Saved loadouts stay in their own localStorage key. This module only
 * describes the automatic "where I left off" state and refuses shapes that
 * would crash the UI after a catalog change.
 */
import { DEFAULT_UI_SETTINGS, THEME_OPTIONS } from './uiSettings.js'

export const WORKSPACE_VERSION = 1

export const WORKSPACE_TABS = ['bis', 'sim', 'upgrades', 'bags', 'quests', 'mobs', 'search']
export const MOB_KINDS = ['all', 'raid', 'mini_boss', 'named', 'standard']
export const MOB_ERAS = ['all', 'classic', 'kunark', 'velious', 'planes', 'untagged']
export const CAST_BUFF_MODES = ['off', 'quick']
export const MAX_LEVEL = 50
export const EMPTY_TIERS = ['', '', '']

const THEME_IDS = new Set(THEME_OPTIONS.map((t) => t.id))

function clampUpgrade(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return 0
  return Math.max(0, Math.min(10, Math.trunc(v)))
}

function pickUpgradeLevel(value, fallback) {
  if (value == null || value === '') return fallback
  const v = Number(value)
  if (!Number.isFinite(v)) return fallback
  return Math.max(0, Math.min(10, Math.trunc(v)))
}

function pickBool(value, fallback) {
  return typeof value === 'boolean' ? value : fallback
}

function pickText(value, max) {
  if (typeof value !== 'string') return ''
  return value.slice(0, max)
}

function cleanItemName(value) {
  if (typeof value === 'string') {
    const s = value.trim()
    if (!s || s.length > 300) return ''
    return s
  }
  if (value && typeof value === 'object' && !Array.isArray(value) && typeof value.name === 'string') {
    return cleanItemName(value.name)
  }
  return ''
}

function knownSlots(catalog) {
  return Array.isArray(catalog?.slots) ? catalog.slots.filter((s) => typeof s === 'string' && s) : []
}

function slotAllowed(slot, slots) {
  if (!slot || typeof slot !== 'string') return false
  const name = slot.trim()
  if (!name) return false
  if (slots.length) return slots.includes(name)
  return /^[A-Za-z0-9]{1,24}$/.test(name)
}

export function catalogFromMeta(meta) {
  const races = []
  const raceRows = meta?.races?.races
  if (Array.isArray(raceRows)) {
    for (const row of raceRows) {
      const name = typeof row === 'string' ? row : row?.name
      if (typeof name === 'string' && name.trim()) races.push(name.trim())
    }
  }
  return {
    classes: Array.isArray(meta?.classes) ? meta.classes.filter((c) => typeof c === 'string' && c) : [],
    races,
    slots: Array.isArray(meta?.slots) ? meta.slots.filter((s) => typeof s === 'string' && s) : [],
    stats: Array.isArray(meta?.priority_stats)
      ? meta.priority_stats.map((s) => s?.key).filter((k) => typeof k === 'string' && k)
      : [],
    modes: Array.isArray(meta?.modes)
      ? meta.modes.map((m) => m?.id).filter((id) => typeof id === 'string' && id)
      : [],
    levels: Array.isArray(meta?.character_levels)
      ? meta.character_levels.filter((n) => Number.isFinite(n))
      : [],
    itemExists: typeof meta?.itemExists === 'function' ? meta.itemExists : null,
  }
}

export function defaultWorkspace(catalog) {
  const races = catalog?.races || []
  const race = races.includes('Human') ? 'Human' : (races[0] || 'Human')
  const levels = catalog?.levels || []
  const level = levels.length
    ? Math.min(MAX_LEVEL, Math.max(...levels))
    : MAX_LEVEL
  return {
    tab: 'bis',
    classes: [],
    mode: 'priority',
    primaryStats: [...EMPTY_TIERS],
    secondaryStats: [...EMPTY_TIERS],
    tertiaryStats: [...EMPTY_TIERS],
    maximizeHpRegen: false,
    upgrade: 10,
    wornUpgrades: {},
    bisUpgrades: {},
    preferRanged: true,
    race,
    characterLevel: level,
    castBuffsMode: 'off',
    assumeMaxAas: true,
    equipment: {},
    bisOverrides: {},
    bagsQ: '',
    bagsLoc: '',
    questQ: '',
    selectedQuestName: '',
    questListCollapsed: false,
    questRewardUpgrade: 0,
    mobQ: '',
    mobKind: 'all',
    mobEra: 'all',
    selectedMobName: '',
    mobListCollapsed: false,
    searchQ: '',
    searchSlot: '',
    searchSelectedName: '',
    searchItemUpgrade: 0,
    buildName: '',
    selectedBuildId: '',
    importMeta: null,
    uiSettings: null,
  }
}

function pickClasses(value, catalog) {
  const known = catalog?.classes || []
  const out = []
  const list = Array.isArray(value) ? value : []
  for (const entry of list) {
    if (out.length >= 3) break
    if (typeof entry !== 'string') continue
    const name = entry.trim()
    if (!name) continue
    if (known.length) {
      const match = known.find((c) => c.toLowerCase() === name.toLowerCase())
      if (!match || out.includes(match)) continue
      out.push(match)
    } else if (!out.includes(name) && name.length <= 40) {
      out.push(name)
    }
  }
  return out
}

function pickMode(value, catalog) {
  const modes = catalog?.modes?.length ? catalog.modes : ['priority', 'max', 'ai']
  if (typeof value === 'string' && modes.includes(value)) return value
  return modes.includes('priority') ? 'priority' : modes[0]
}

function pickTiers(value, catalog) {
  const allowed = catalog?.stats || []
  const next = [...EMPTY_TIERS]
  const arr = Array.isArray(value) ? value : []
  for (let i = 0; i < 3; i += 1) {
    const raw = arr[i]
    if (typeof raw !== 'string') continue
    const key = raw.trim()
    if (!key) continue
    if (allowed.length && !allowed.includes(key)) continue
    if (!allowed.length && key.length > 40) continue
    next[i] = key
  }
  return next
}

function pickRace(value, catalog) {
  const races = catalog?.races || []
  const fallback = races.includes('Human') ? 'Human' : (races[0] || 'Human')
  if (typeof value !== 'string' || !value.trim()) return fallback
  const name = value.trim()
  if (!races.length) return name.slice(0, 40)
  return races.find((r) => r.toLowerCase() === name.toLowerCase()) || fallback
}

function pickLevel(value, catalog) {
  const levels = (catalog?.levels || []).filter((n) => n >= 1 && n <= MAX_LEVEL)
  const fallback = levels.length ? Math.min(MAX_LEVEL, Math.max(...levels)) : MAX_LEVEL
  const v = Number(value)
  if (!Number.isFinite(v)) return fallback
  const lv = Math.trunc(v)
  if (lv < 1 || lv > MAX_LEVEL) return fallback
  if (levels.length && !levels.includes(lv)) return fallback
  return lv
}

function pickUpgradeMap(value, slots) {
  const out = {}
  if (!value || typeof value !== 'object' || Array.isArray(value)) return out
  for (const [key, raw] of Object.entries(value)) {
    if (!slotAllowed(key, slots)) continue
    out[key.trim()] = clampUpgrade(raw)
  }
  return out
}

function pickNameMap(value, slots, itemExists) {
  const out = {}
  if (!value || typeof value !== 'object' || Array.isArray(value)) return out
  for (const [key, raw] of Object.entries(value)) {
    if (!slotAllowed(key, slots)) continue
    const name = cleanItemName(raw)
    if (!name) continue
    if (itemExists && !itemExists(name)) continue
    out[key.trim()] = name
  }
  return out
}

function pickEnum(value, allowed, fallback) {
  return typeof value === 'string' && allowed.includes(value) ? value : fallback
}

function sanitizeUiSettings(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const theme = typeof raw.theme === 'string' && THEME_IDS.has(raw.theme)
    ? raw.theme
    : DEFAULT_UI_SETTINGS.theme
  return {
    theme,
    funnyLoadingTips: pickBool(raw.funnyLoadingTips, DEFAULT_UI_SETTINGS.funnyLoadingTips),
    compactBadges: pickBool(raw.compactBadges, DEFAULT_UI_SETTINGS.compactBadges),
    reduceMotion: pickBool(raw.reduceMotion, DEFAULT_UI_SETTINGS.reduceMotion),
  }
}

function sanitizeImportRow(row) {
  if (typeof row === 'string') {
    const name = cleanItemName(row)
    if (!name || name.toLowerCase() === 'empty') return null
    return { name, base_name: name, location: '' }
  }
  if (!row || typeof row !== 'object' || Array.isArray(row)) return null
  const name = cleanItemName(row.base_name || row.name)
  if (!name || name.toLowerCase() === 'empty') return null
  const upgrade = row.upgrade_from_name
  return {
    location: pickText(row.location, 200),
    name: cleanItemName(row.name) || name,
    base_name: name,
    upgrade_from_name: upgrade == null || upgrade === '' ? null : clampUpgrade(upgrade),
    id: pickText(row.id, 64),
    count: pickText(row.count == null ? '' : String(row.count), 32),
    slots: pickText(row.slots, 200),
    in_catalog: !!row.in_catalog,
    catalog_source: row.catalog_source ? pickText(String(row.catalog_source), 40) : null,
    has_stats: !!row.has_stats,
    unmatched: !!row.unmatched,
    reason: row.reason ? pickText(String(row.reason), 120) : null,
    planner_slot: typeof row.planner_slot === 'string' ? pickText(row.planner_slot, 40) : null,
  }
}

function sanitizeImportMeta(raw, slots, itemExists) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const equipment = pickNameMap(raw.equipment, slots, null)
  const wornUpgrades = pickUpgradeMap(raw.wornUpgrades || raw.upgrade_hints, slots)
  const allItems = []
  if (Array.isArray(raw.all_items)) {
    for (const row of raw.all_items) {
      if (allItems.length >= 5000) break
      const clean = sanitizeImportRow(row)
      if (!clean) continue
      if (itemExists && clean.base_name && !itemExists(clean.base_name) && clean.in_catalog) {
        continue
      }
      allItems.push(clean)
    }
  }
  const unmatched = []
  if (Array.isArray(raw.unmatched)) {
    for (const row of raw.unmatched) {
      if (unmatched.length >= 500) break
      const clean = sanitizeImportRow(row)
      if (clean) unmatched.push(clean)
    }
  }
  const source = pickText(raw.source, 240)
  if (!Object.keys(equipment).length && !allItems.length && !unmatched.length && !source) {
    return null
  }
  return {
    equipment,
    wornUpgrades,
    all_items: allItems,
    unmatched,
    unmatched_count: Number.isFinite(Number(raw.unmatched_count))
      ? Math.max(0, Math.trunc(Number(raw.unmatched_count)))
      : unmatched.length,
    skipped_count: Number.isFinite(Number(raw.skipped_count))
      ? Math.max(0, Math.trunc(Number(raw.skipped_count)))
      : 0,
    source,
    upgrade_hints: pickUpgradeMap(raw.upgrade_hints, slots),
  }
}

/**
 * Turn saved JSON into a complete workspace. Never throws.
 * `restored` is false when there is no usable object (missing, corrupt, or
 * the wrong JSON type) so the caller can keep first-launch defaults.
 * Unknown classes, races, slots, stats, modes, and non-string items are
 * dropped. When `catalog.itemExists` is set, names it rejects are dropped too.
 */
export function sanitizeWorkspace(raw, catalog) {
  const cat = catalog || {}
  const defaults = defaultWorkspace(cat)
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return { restored: false, state: defaults }
  }
  try {
    const slots = knownSlots(cat)
    const itemExists = typeof cat.itemExists === 'function' ? cat.itemExists : null
    const searchSlot = typeof raw.searchSlot === 'string' ? raw.searchSlot.trim() : ''
    let searchSelectedName = cleanItemName(raw.searchSelectedName)
    if (itemExists && searchSelectedName && !itemExists(searchSelectedName)) {
      searchSelectedName = ''
    }
    const state = {
      ...defaults,
      tab: pickEnum(raw.tab, WORKSPACE_TABS, 'bis'),
      classes: pickClasses(raw.classes, cat),
      mode: pickMode(raw.mode, cat),
      primaryStats: pickTiers(raw.primaryStats, cat),
      secondaryStats: pickTiers(raw.secondaryStats, cat),
      tertiaryStats: pickTiers(raw.tertiaryStats, cat),
      maximizeHpRegen: pickBool(raw.maximizeHpRegen, false),
      upgrade: pickUpgradeLevel(raw.upgrade, 10),
      wornUpgrades: pickUpgradeMap(raw.wornUpgrades, slots),
      bisUpgrades: pickUpgradeMap(raw.bisUpgrades, slots),
      preferRanged: pickBool(raw.preferRanged, true),
      race: pickRace(raw.race, cat),
      characterLevel: pickLevel(raw.characterLevel, cat),
      castBuffsMode: pickEnum(raw.castBuffsMode, CAST_BUFF_MODES, 'off'),
      assumeMaxAas: pickBool(raw.assumeMaxAas, true),
      equipment: pickNameMap(raw.equipment, slots, itemExists),
      bisOverrides: pickNameMap(raw.bisOverrides, slots, itemExists),
      bagsQ: pickText(raw.bagsQ, 200),
      bagsLoc: pickText(raw.bagsLoc, 120),
      questQ: pickText(raw.questQ, 200),
      selectedQuestName: pickText(raw.selectedQuestName, 200),
      questListCollapsed: pickBool(raw.questListCollapsed, false),
      questRewardUpgrade: clampUpgrade(raw.questRewardUpgrade),
      mobQ: pickText(raw.mobQ, 200),
      mobKind: pickEnum(raw.mobKind, MOB_KINDS, 'all'),
      mobEra: pickEnum(raw.mobEra, MOB_ERAS, 'all'),
      selectedMobName: pickText(raw.selectedMobName, 200),
      mobListCollapsed: pickBool(raw.mobListCollapsed, false),
      searchQ: pickText(raw.searchQ, 200),
      searchSlot: searchSlot && slotAllowed(searchSlot, slots) ? searchSlot : '',
      searchSelectedName,
      searchItemUpgrade: searchSelectedName ? clampUpgrade(raw.searchItemUpgrade) : 0,
      buildName: pickText(raw.buildName, 80),
      selectedBuildId: pickText(raw.selectedBuildId, 80),
      importMeta: sanitizeImportMeta(raw.importMeta, slots, itemExists),
      uiSettings: sanitizeUiSettings(raw.uiSettings),
    }
    return { restored: true, state }
  } catch (_) {
    return { restored: false, state: defaults }
  }
}

/** Persistable object. Saved-build records are never included. */
export function buildWorkspaceSnapshot(input, catalog) {
  const { state } = sanitizeWorkspace({ ...(input || {}), v: WORKSPACE_VERSION }, catalog)
  const snapshot = { v: WORKSPACE_VERSION }
  for (const [key, value] of Object.entries(state)) {
    if (key === 'uiSettings' && !value) continue
    snapshot[key] = value
  }
  return snapshot
}
