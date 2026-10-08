/** Filename and bag-count helpers for the Currencies tab. Counts come from the import. */

export function characterFromInventoryFile(name) {
  const base = String(name || '').split(/[/\\]/).pop() || ''
  const match = /^([^_]+)_.*-Inventory\.txt$/i.exec(base)
  return match ? match[1] : ''
}

export function bagCountsFromImport(parsed) {
  const counts = {}
  for (const row of parsed?.motes || []) {
    if (row?.name) counts[row.name] = Number(row.count) || 0
  }
  const voidTouched = parsed?.void_touched
  if (voidTouched?.name) counts[voidTouched.name] = Number(voidTouched.count) || 0
  for (const row of parsed?.wind_runes || []) {
    if (row?.name) counts[row.name] = Number(row.count) || 0
  }
  return counts
}
