/** Item Search request fields. Sort keys are omitted when unset so the server stays alphabetical. */

const SORT_KEYS = ['sort', 'sort2', 'sort3']
const SORT_DIRS = ['sort_dir', 'sort2_dir', 'sort3_dir']

export const DAMAGE_DELAY_SORT = 'damage_delay_ratio'

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
  usableClasses = null,
  usableMatch = 'any',
  compareLevel = 0,
  stat = '',
  statMin = '',
  ratioMin = '',
  sorts = [],
  limit = 80,
} = {}) {
  const params = { q: q || '', limit }
  if (slot) params.slot = slot
  if (typeName) params.type = typeName
  if (usableClass) params.usable_class = usableClass
  const classList = Array.isArray(usableClasses)
    ? usableClasses.filter(Boolean).slice(0, 3)
    : (usableClass ? [usableClass] : [])
  if (classList.length === 1 && !params.usable_class) params.usable_class = classList[0]
  if (classList.length) params.usable_classes = classList.join(',')
  if (classList.length > 1 || usableMatch === 'all') {
    params.usable_match = usableMatch === 'all' ? 'all' : 'any'
  }
  const level = Number(compareLevel)
  const clamped = Number.isFinite(level) ? Math.max(0, Math.min(10, Math.trunc(level))) : 0
  params.compare_level = String(clamped)
  if (stat) {
    params.stat = stat
    if (statMin !== '' && statMin != null && Number.isFinite(Number(statMin))) {
      params.stat_min = String(statMin)
    }
  }
  if (ratioMin !== '' && ratioMin != null && Number.isFinite(Number(ratioMin))) {
    params.ratio_min = String(ratioMin)
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
