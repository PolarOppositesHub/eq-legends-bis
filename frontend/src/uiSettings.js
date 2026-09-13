/** Persisted UI settings + help copy + loading flavor text. */

export const UI_SETTINGS_KEY = 'eq-legends-bis-ui-settings-v1'

export const THEME_OPTIONS = [
  { id: 'classic', label: 'Classic Dark', blurb: 'Black panels with gold accents' },
  { id: 'light', label: 'Light', blurb: 'Bright workspace, dark text' },
  { id: 'dusk', label: 'Dusk', blurb: 'Slate night with soft gold' },
  { id: 'forge', label: 'Forge', blurb: 'Warm charcoal and copper' },
]

export const DEFAULT_UI_SETTINGS = {
  theme: 'classic',
  funnyLoadingTips: true,
  compactBadges: true,
  reduceMotion: false,
}

export function loadUiSettings() {
  try {
    const raw = localStorage.getItem(UI_SETTINGS_KEY)
    if (!raw) return { ...DEFAULT_UI_SETTINGS }
    const parsed = JSON.parse(raw)
    return { ...DEFAULT_UI_SETTINGS, ...(parsed && typeof parsed === 'object' ? parsed : {}) }
  } catch (_) {
    return { ...DEFAULT_UI_SETTINGS }
  }
}

export function saveUiSettings(next) {
  try {
    localStorage.setItem(UI_SETTINGS_KEY, JSON.stringify(next))
  } catch (_) {
    /* ignore quota / private mode */
  }
}

export function applyThemeToDocument(themeId) {
  const id = THEME_OPTIONS.some((t) => t.id === themeId) ? themeId : 'classic'
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', id)
  }
  return id
}

/** EQ-flavored loading quips (rotate while busy). */
export const LOADING_SAYINGS = [
  'Making elves’ ears pointier…',
  'Polishing plate until it blinds the ogres…',
  'Convincing the banker to open just one more bag…',
  'Counting Wind Runes (again)…',
  'Teaching a gnome not to click every orb…',
  'Bribing a froglok for directions…',
  'Untangling Plane of Sky key rings…',
  'Calibrating haste: highest item + spell stacks…',
  'Asking Lucan if he has a minute…',
  'Warming up the forge in Sol A…',
  'Checking if that skullcap is +2 or +10…',
  'Herding three classes into one trio…',
  'Dusting off a Raw-Hide Skullcap…',
  'Negotiating with Marshal Anrey…',
  'Sorting General slots alphabetically (don’t)…',
  'Whispering /outputfile inventory into the void…',
  'Measuring DMG/DLY like a true nerd…',
  'Hiding from the Train to Freeport…',
]

export function pickLoadingSaying(seed = Date.now()) {
  const i = Math.abs(Number(seed) || 0) % LOADING_SAYINGS.length
  return LOADING_SAYINGS[i]
}

export const APP_HELP = {
  title: 'How to use EQ Legends BiS',
  intro:
    'Pick up to three classes, then use the side menu to plan BiS, simulate your worn gear, search bags, and look up quests. Data comes from decoded eqlegendstools / eqlwiki sources — stats are never invented.',
  sections: [
    {
      id: 'bis',
      title: 'Best in Slot',
      body: [
        'Choose Mode (Priority Stat, Max All Stats, or AI Choice) and your upgrade level (+0…+10).',
        'Update BiS builds a recommended loadout for your trio. Hover item names for icons and stat tips.',
        'Weapons may show dual-wield vs two-hand picks based on class and character level.',
      ],
    },
    {
      id: 'sim',
      title: 'Simulator',
      body: [
        'Compare Worn vs BiS per slot. Each side has its own +N enchant level.',
        'Import Inventory.txt (or Update from EQ folder on desktop) to fill worn gear and bag contents.',
        'Live Totals use race/class pools, gear, optional Cast Buffs, and haste rules (highest worn haste stacks with spell haste; caps at 175%, or 185% with Monk).',
        'Default upgrade + Apply to all slots sets every piece; otherwise edit +N under each slot.',
      ],
    },
    {
      id: 'upgrades',
      title: 'Upgrade Priority',
      body: [
        'Ranks what to chase next versus your BiS list after an inventory import.',
        'Each entry can show zone, drop mobs, and quest steps when known from the catalog / eqlwiki.',
      ],
    },
    {
      id: 'bags',
      title: 'Search My Bags',
      body: [
        'Search every occupied line from your last inventory import (worn, bags, bank, nested slots — empty slots hidden).',
        'Names match the tools catalog and eqlwiki item list. Wiki-only names may show without stats yet.',
      ],
    },
    {
      id: 'quests',
      title: 'Quest Hub',
      body: [
        'Search quests linked from item reward data. Single-click to preview; double-click (or the side rail) to maximize the walkthrough.',
        'Steps come from eqlwiki when available. Prerequisites include walkthrough mentions of other quests — click hub-listed ones to open them.',
        'Rewards list catalog items with a +0…+10 slider for stats.',
      ],
    },
    {
      id: 'mobs',
      title: 'Mobs',
      body: [
        'Browse eqlwiki NPCs filtered by Raid, Mini Boss, Named, or Standard. Same expand/collapse layout as Quest Hub.',
        'Detail shows wiki fields when available and known drops reverse-linked from the item catalog.',
        'Hover a known drop for an item-stats preview; click it for a small menu — Item Search or eqlwiki.',
      ],
    },
    {
      id: 'search',
      title: 'Item Search',
      body: [
        'Look up any EQ Legends item by name (gear and non-equipables). Open a result for stats and wiki description when available.',
        'Catalog unions eqlegendstools decoded items with the full eqlwiki item name list — stats are never invented.',
      ],
    },
    {
      id: 'settings',
      title: 'Settings (cog)',
      body: [
        'Change color theme, compact badges, reduced motion, and funny loading tips.',
        'Settings save in this browser / desktop profile (localStorage).',
      ],
    },
    {
      id: 'inventory',
      title: 'Inventory tips',
      body: [
        'In game: /outputfile inventory — file lands in the EQ install root as Character_server-Inventory.txt.',
        'Desktop: Set EQ folder once, then Update from EQ folder on Simulator or Bags.',
        'You can still use the file picker anytime.',
      ],
    },
  ],
}
