/** Display helpers for the mote path and Plane of Sky panes. */

export const WIND_RUNE_PREFIX = 'Wind Rune '

export function copiesFromImport(importMeta) {
  const copies = []
  for (const row of importMeta?.rows || []) {
    if (!row) continue
    const name = row.name_raw || row.name
    if (!name || String(name).toLowerCase() === 'empty') continue
    copies.push({
      name,
      tier: row.tier == null ? null : row.tier,
      count: Number(row.count) > 0 ? Number(row.count) : 1,
    })
  }
  for (const entry of importMeta?.keyring || []) {
    if (!entry?.name) continue
    copies.push({
      name: entry.name,
      tier: entry.tier == null ? null : entry.tier,
      count: Number(entry.count) > 0 ? Number(entry.count) : 1,
    })
  }
  return copies
}

export function inventoryRuneCounts(copies) {
  const counts = {}
  for (const row of copies || []) {
    const name = String(row?.name || '')
    if (!name.startsWith(WIND_RUNE_PREFIX)) continue
    counts[name] = (counts[name] || 0) + (Number(row.count) > 0 ? Number(row.count) : 1)
  }
  return counts
}

export function formatMoteList(rows) {
  const list = Array.isArray(rows) ? rows : []
  if (!list.length) return 'none'
  return list.map((row) => `${row.name} × ${row.count}`).join(', ')
}

export function wishNamesFor(wishByCharacter, character) {
  const key = (character || '').trim()
  const rows = wishByCharacter && wishByCharacter[key]
  return Array.isArray(rows) ? rows.filter((name) => typeof name === 'string' && name) : []
}

export function toggleWish(wishByCharacter, character, itemName) {
  const key = (character || '').trim()
  const name = String(itemName || '').trim()
  const current = wishNamesFor(wishByCharacter, key)
  const next = current.some((entry) => entry.toLowerCase() === name.toLowerCase())
    ? current.filter((entry) => entry.toLowerCase() !== name.toLowerCase())
    : (name ? [...current, name] : current)
  return { ...(wishByCharacter || {}), [key]: next }
}

export function isWished(wishByCharacter, character, itemName) {
  const name = String(itemName || '').trim().toLowerCase()
  return wishNamesFor(wishByCharacter, character).some((entry) => entry.toLowerCase() === name)
}
