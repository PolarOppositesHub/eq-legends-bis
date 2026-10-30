/**
 * Keyboard shortcuts for 1.1.19.
 * g, then a letter, opens a page that already exists. ? opens the list.
 * Shortcuts do not add pages or change what those pages show.
 */

export const CHORD_PREFIX = 'g'
export const CHORD_MS = 1200

export const SHORTCUTS = [
  { key: 'o', tab: 'overview', label: 'Overview' },
  { key: 'l', tab: 'loot', label: 'Loot' },
  { key: 'v', tab: 'leveling', label: 'Leveling' },
  { key: 'r', tab: 'raids', label: 'Raid targets' },
  { key: 'n', tab: 'companion', label: 'Companion' },
  { key: 'm', tab: 'maps', label: 'Maps' },
  { key: 'b', tab: 'bis', label: 'Best in Slot' },
  { key: 's', tab: 'sim', label: 'Simulator' },
  { key: 'u', tab: 'upgrades', label: 'Upgrade Priority' },
  { key: 'e', tab: 'requirements', label: 'Requirements' },
  { key: 'w', tab: 'wishlist', label: 'Wish list' },
  { key: 'c', tab: 'character', label: 'Character' },
  { key: 'y', tab: 'currencies', label: 'Currencies' },
  { key: 'q', tab: 'quests', label: 'Quest Hub' },
  { key: 'k', tab: 'mobs', label: 'Mobs' },
  { key: 'i', tab: 'search', label: 'Item Search' },
  { key: 'p', tab: 'parser', label: 'Parser' },
  { key: 'a', tab: 'alerts', label: 'Alerts' },
]

const GO = Object.fromEntries(SHORTCUTS.map((row) => [row.key, row.tab]))

export function shortcutHelpLines() {
  return [
    'Press ? to open the shortcut list. Press g, then a letter, to open a page.',
    'Shortcuts do nothing while the cursor is in a text field, or while a dialog is open.',
    ...SHORTCUTS.map((row) => `g then ${row.key} opens ${row.label}.`),
  ]
}

export function isTypingTarget(target) {
  if (!target || typeof target !== 'object') return false
  const tag = String(target.tagName || '').toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true
  if (target.isContentEditable) return true
  return false
}

/**
 * @returns {{ type: 'help' | 'arm' | 'clear' } | { type: 'go', tab: string } | null}
 */
export function nextShortcut(event, armed) {
  if (!event || event.metaKey || event.ctrlKey || event.altKey || event.repeat) return null
  if (isTypingTarget(event.target)) return armed ? { type: 'clear' } : null
  const key = typeof event.key === 'string' ? event.key : ''
  if (key === '?') return { type: 'help' }
  const lower = key.toLowerCase()
  if (!/^[a-z]$/.test(lower)) return armed ? { type: 'clear' } : null
  if (!armed) {
    if (lower === CHORD_PREFIX) return { type: 'arm' }
    return null
  }
  const tab = GO[lower]
  if (!tab) return { type: 'clear' }
  return { type: 'go', tab }
}
