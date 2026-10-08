/**
 * Same owned-name rules as backend/app/item_names.py.
 * Hyphens and spaces match. Apostrophe marks match each other and their absence.
 * Extra spaces collapse. The old Slime Blood spelling stays an alias.
 */

const APOSTROPHES = /[’‘`'ʼ´']/g

export const CANONICAL_ALIASES = {
  'Slime Blood of Cazic Thule': 'Slime Blood of Cazic-Thule',
}

export function itemBaseName(name) {
  let n = String(name || '').trim()
  if (n.endsWith('*')) n = n.slice(0, -1).trim()
  const match = n.match(/(?:\s*\+\s*\d+)\s*$/)
  if (match) n = n.slice(0, match.index).trim()
  return n
}

export function ownedNameKey(name) {
  let n = itemBaseName(name)
  n = n.replace(/\u00a0/g, ' ').replace(/\u200b/g, '')
  n = n.replace(APOSTROPHES, '')
  n = n.replace(/-/g, ' ')
  n = n.replace(/\s+/g, ' ').trim().toLowerCase()
  return n
}

export function namesMatch(a, b) {
  const left = ownedNameKey(a)
  const right = ownedNameKey(b)
  return Boolean(left) && left === right
}

export function canonicalItemName(name) {
  const base = itemBaseName(name)
  const key = ownedNameKey(base)
  if (!key) return ''
  for (const [oldName, canon] of Object.entries(CANONICAL_ALIASES)) {
    if (ownedNameKey(oldName) === key || ownedNameKey(canon) === key) return canon
  }
  return base
}

export function itemIdText(value) {
  if (value == null) return ''
  const text = String(value).trim()
  if (!text || text === '0' || text === 'None') return ''
  return text
}

/** Lore only when a flags string contains the word. Blank flags are not lore. */
export function itemIsLore(flags) {
  return /\blore\b/i.test(String(flags || ''))
}
