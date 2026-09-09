const BASE = ''

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = j.detail || JSON.stringify(j)
    } catch (_) {}
    throw new Error(detail)
  }
  return res.json()
}

export const getMeta = () => req('/api/meta')
export const postBis = (body) => req('/api/bis', { method: 'POST', body: JSON.stringify(body) })
export const getPriorityDefaults = (classes) => {
  const q = new URLSearchParams()
  for (const c of classes || []) q.append('classes', c)
  return req(`/api/priority-defaults?${q}`)
}
export const getItems = (params) => {
  const q = new URLSearchParams(params)
  return req(`/api/items?${q}`)
}
export const searchItems = (params) => {
  const q = new URLSearchParams(params)
  return req(`/api/item-search?${q}`)
}
export const getItemDetail = (name) => {
  const q = new URLSearchParams({ name })
  return req(`/api/item-detail?${q}`)
}
export const ensureItemImage = async (name) => {
  const q = new URLSearchParams({ name })
  const info = await req(`/api/item-image/ensure?${q}`, { method: 'POST' })
  if (!info || info.error || info.cached === false) {
    throw new Error((info && info.error) || 'image not available')
  }
  return info
}
export const itemImageUrl = (name) => {
  if (!name) return ''
  return `/api/item-image?name=${encodeURIComponent(name)}`
}
export const spellIconUrl = (icon) => {
  if (!icon) return ''
  return `/api/spell-icon?name=${encodeURIComponent(icon)}`
}
export const postSimulate = (body) => req('/api/simulate', { method: 'POST', body: JSON.stringify(body) })
export const exportXlsx = (classes) => req('/api/export/xlsx', { method: 'POST', body: JSON.stringify({ classes }) })
export const getZones = () => req('/api/zones')
export const getZone = (name, drops_mobs) => {
  const q = new URLSearchParams()
  if (drops_mobs != null) q.set('drops_mobs', drops_mobs)
  const qs = q.toString()
  return req(`/api/zones/${encodeURIComponent(name)}${qs ? `?${qs}` : ''}`)
}
export const getZoneDetail = (zone, drops_mobs = '') => {
  const q = new URLSearchParams({ zone, drops_mobs })
  return req(`/api/zone-detail?${q}`)
}
export const parseInventory = (text) =>
  req('/api/inventory/parse', { method: 'POST', body: JSON.stringify({ text }) })
export const importInventory = (text) =>
  req('/api/inventory/import', { method: 'POST', body: JSON.stringify({ text }) })
export const upgradeSuggestions = (body) =>
  req('/api/inventory/upgrade-suggestions', { method: 'POST', body: JSON.stringify(body) })
export const getInventoryHelp = () => req('/api/help/inventory')
export const listQuests = (params = {}) => {
  const q = new URLSearchParams(params)
  return req(`/api/quests?${q}`)
}
export const getQuestGuide = (name, fetch = true) => {
  const q = new URLSearchParams({ name, fetch: String(!!fetch) })
  return req(`/api/quest-guide?${q}`)
}
export const getQuestDetail = (body) =>
  req('/api/quest-detail', { method: 'POST', body: JSON.stringify(body) })
