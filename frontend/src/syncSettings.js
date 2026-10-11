/**
 * Sync settings copy and the snapshot exchanged with the sidecar.
 * Counts, pins, and section rows come from the caller. This file does not invent them.
 */

import { characterFromInventoryFile } from './currenciesView.js'
import { applySyncedSections } from './inventorySections.js'

export const ICLOUD_TIP = 'If this folder is in iCloud Drive, mark it Always keep on this device.'
export const ICLOUD_WAITING = 'waiting for iCloud to download'

export const SYNC_PROVIDERS = [
  { id: 'folder', label: 'Sync folder' },
  { id: 'onedrive', label: 'OneDrive' },
]

export function snapshotFromWorkspace(state) {
  const names = new Set()
  for (const map of [
    state?.wishByCharacter,
    state?.upgradeProgressByCharacter,
    state?.upgradeTierByCharacter,
    state?.posManualByCharacter,
    state?.posIgnoredByCharacter,
    state?.achievementsByCharacter,
  ]) {
    if (!map || typeof map !== 'object') continue
    for (const key of Object.keys(map)) {
      if (key) names.add(key)
    }
  }
  const inventoryCharacter = state?.inventoryCharacter
    || characterFromInventoryFile(state?.importMeta?.source || '')
  if (inventoryCharacter) names.add(inventoryCharacter)
  const characters = {}
  for (const name of names) {
    const row = {
      wishes: [...(state?.wishByCharacter?.[name] || [])].map((item) => ({ name: item })),
      settings: {
        upgrade_progress: { ...(state?.upgradeProgressByCharacter?.[name] || {}) },
        upgrade_tier: { ...(state?.upgradeTierByCharacter?.[name] || {}) },
        pos_manual: { ...(state?.posManualByCharacter?.[name] || {}) },
        pos_ignored: [...(state?.posIgnoredByCharacter?.[name] || [])],
        achievements: state?.achievementsByCharacter?.[name] || '',
      },
    }
    if (name === inventoryCharacter && Array.isArray(state?.importMeta?.section_events)) {
      row.inventory_events = state.importMeta.section_events
    }
    characters[name] = row
  }
  return { characters }
}

function sameJson(left, right) {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null)
}

export function mergeProjection(local, projection) {
  const characters = projection?.characters || {}
  const next = {
    wishByCharacter: { ...(local?.wishByCharacter || {}) },
    upgradeProgressByCharacter: { ...(local?.upgradeProgressByCharacter || {}) },
    upgradeTierByCharacter: { ...(local?.upgradeTierByCharacter || {}) },
    posManualByCharacter: { ...(local?.posManualByCharacter || {}) },
    posIgnoredByCharacter: { ...(local?.posIgnoredByCharacter || {}) },
    achievementsByCharacter: { ...(local?.achievementsByCharacter || {}) },
    importMeta: local?.importMeta || null,
  }
  let changed = false
  const inventoryCharacter = local?.inventoryCharacter
    || characterFromInventoryFile(local?.importMeta?.source || '')
  for (const [name, body] of Object.entries(characters)) {
    if (!body || typeof body !== 'object') continue
    if (Array.isArray(body.wishes) && !sameJson(next.wishByCharacter[name] || [], body.wishes)) {
      next.wishByCharacter[name] = body.wishes
      changed = true
    }
    const settings = body.settings || {}
    if (settings.upgrade_progress && !sameJson(next.upgradeProgressByCharacter[name] || {}, settings.upgrade_progress)) {
      next.upgradeProgressByCharacter[name] = settings.upgrade_progress
      changed = true
    }
    if (settings.upgrade_tier && !sameJson(next.upgradeTierByCharacter[name] || {}, settings.upgrade_tier)) {
      next.upgradeTierByCharacter[name] = settings.upgrade_tier
      changed = true
    }
    if (settings.pos_manual && !sameJson(next.posManualByCharacter[name] || {}, settings.pos_manual)) {
      next.posManualByCharacter[name] = settings.pos_manual
      changed = true
    }
    if (Array.isArray(settings.pos_ignored) && !sameJson(next.posIgnoredByCharacter[name] || [], settings.pos_ignored)) {
      next.posIgnoredByCharacter[name] = settings.pos_ignored
      changed = true
    }
    if (typeof settings.achievements === 'string' && (next.achievementsByCharacter[name] || '') !== settings.achievements) {
      next.achievementsByCharacter[name] = settings.achievements
      changed = true
    }
    if (name === inventoryCharacter && Array.isArray(body.section_events)) {
      const applied = applySyncedSections(next.importMeta, body.section_events)
      if (!sameJson(applied?.section_events || [], next.importMeta?.section_events || [])) {
        next.importMeta = applied
        changed = true
      }
    }
  }
  return changed ? next : null
}

export function syncStatusText(status) {
  if (!status) return ''
  if (status.message === ICLOUD_WAITING) return ICLOUD_WAITING
  if (status.error) return String(status.error)
  if (status.status === 'offline') return 'Offline. Changes stay on this PC until sync can reach the folder or OneDrive.'
  return ''
}
