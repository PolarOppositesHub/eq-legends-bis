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
export const getItems = (params) => {
  const q = new URLSearchParams(params)
  return req(`/api/items?${q}`)
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
