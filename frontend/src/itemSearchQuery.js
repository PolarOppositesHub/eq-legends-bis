/** Item Search request fields. Sort keys are omitted when unset so the server stays alphabetical. */

const SORT_KEYS = ['sort', 'sort2', 'sort3']
const SORT_DIRS = ['sort_dir', 'sort2_dir', 'sort3_dir']

export const SEARCH_STAT_LABELS = {
  AC: 'AC',
  HP: 'HP',
  MANA: 'Mana',
  END: 'END',
  STR: 'STR',
  STA: 'STA',
  AGI: 'AGI',
  DEX: 'DEX',
  WIS: 'WIS',
  INT: 'INT',
  CHA: 'CHA',
  Haste: 'Haste',
  DMG: 'DMG',
  DLY: 'DLY',
  HP_REGEN: 'HP Regen',
  MANA_REGEN: 'Mana Regen',
  END_REGEN: 'End Regen',
  SVF: 'SV Fire',
  SVC: 'SV Cold',
  SVM: 'SV Magic',
  SVP: 'SV Poison',
  SVD: 'SV Disease',
  ATK: 'ATK',
  FIRE_DMG: 'FIRE_DMG',
  COLD_DMG: 'COLD_DMG',
}

export function searchStatLabel(key) {
  if (!key) return ''
  return SEARCH_STAT_LABELS[key] || key
}

export function buildItemSearchParams({
  q = '',
  slot = '',
  typeName = '',
  usableClass = '',
  stat = '',
  statMin = '',
  sorts = [],
  limit = 80,
} = {}) {
  const params = { q: q || '', limit }
  if (slot) params.slot = slot
  if (typeName) params.type = typeName
  if (usableClass) params.usable_class = usableClass
  if (stat) {
    params.stat = stat
    if (statMin !== '' && statMin != null && Number.isFinite(Number(statMin))) {
      params.stat_min = String(statMin)
    }
  }
  const levels = Array.isArray(sorts) ? sorts : []
  levels.slice(0, 3).forEach((level, index) => {
    const key = level && level.key ? String(level.key) : ''
    if (!key) return
    params[SORT_KEYS[index]] = key
    params[SORT_DIRS[index]] = level.dir === 'desc' ? 'desc' : 'asc'
  })
  return params
}
