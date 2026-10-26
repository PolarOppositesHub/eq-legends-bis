const BASE = ''

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch (_) {
      /* keep status text */
    }
    const error = new Error(typeof detail === 'string' ? detail : 'Parser request failed')
    error.status = res.status
    throw error
  }
  return res.json()
}

export const getParserConfig = () => req('/api/parser/config')

export const postParserConfig = (body) =>
  req('/api/parser/config', { method: 'POST', body: JSON.stringify(body) })

export const getParserLogs = () => req('/api/parser/logs')

export const postParserLoad = (path) =>
  req('/api/parser/load', { method: 'POST', body: JSON.stringify({ path }) })

export const postParserLive = (body) =>
  req('/api/parser/live', { method: 'POST', body: JSON.stringify(body) })

export const getParserFights = (character, options = {}) => {
  const q = new URLSearchParams()
  if (character) q.set('character', character)
  if (options.limit) q.set('limit', String(options.limit))
  if (options.offset) q.set('offset', String(options.offset))
  const qs = q.toString()
  return req(`/api/parser/fights${qs ? `?${qs}` : ''}`)
}

export const getParserFight = (id, mergePets) => {
  const q = new URLSearchParams({ merge_pets: mergePets ? 'true' : 'false' })
  return req(`/api/parser/fights/${encodeURIComponent(id)}?${q}`)
}

export const getParserTimeline = (id, ability) => {
  const q = new URLSearchParams()
  if (ability) q.set('ability', ability)
  const qs = q.toString()
  return req(`/api/parser/fights/${encodeURIComponent(id)}/timeline${qs ? `?${qs}` : ''}`)
}

export const getParserLoot = (character, options = {}) => {
  const q = new URLSearchParams()
  if (character) q.set('character', character)
  q.set('limit', String(options.limit || 2000))
  if (options.offset) q.set('offset', String(options.offset))
  return req(`/api/parser/loot?${q}`)
}

export const getParserRoster = (character) => {
  const q = new URLSearchParams({ character })
  return req(`/api/parser/roster?${q}`)
}

export const postParserPet = (body) =>
  req('/api/parser/pets', { method: 'POST', body: JSON.stringify(body) })

export const postParserCandidate = (body) =>
  req('/api/parser/candidates', { method: 'POST', body: JSON.stringify(body) })

export const postParserGroup = (body) =>
  req('/api/parser/group', { method: 'POST', body: JSON.stringify(body) })

/** Lines for one fight, re-read from the log. The database does not store them. */
export const getParserFightLines = (id) =>
  req(`/api/parser/fights/${encodeURIComponent(id)}/lines`)

export const postParserClearHistory = (character) =>
  req('/api/parser/history/clear', { method: 'POST', body: JSON.stringify({ character }) })

export const postParserIdentity = (body) =>
  req('/api/parser/identity', { method: 'POST', body: JSON.stringify(body) })

export const getParserMeters = (character, scope = 'fight') => {
  const q = new URLSearchParams({ character: character || '', scope: scope || 'fight' })
  return req(`/api/parser/meters?${q}`)
}

export const getParserAlerts = () => req('/api/parser/alerts')

export const postParserAlert = (rule) =>
  req('/api/parser/alerts', { method: 'POST', body: JSON.stringify({ rule }) })

export const postParserAlertImport = (text) =>
  req('/api/parser/alerts/import', { method: 'POST', body: JSON.stringify({ text }) })

export const getParserAlertsRecent = () => req('/api/parser/alerts/recent')

const characterQuery = (character) => {
  const q = new URLSearchParams()
  if (character) q.set('character', character)
  return q
}

export const getDashboardOverview = (character) => req(`/api/parser/dashboards/overview?${characterQuery(character)}`)
export const getDashboardLoot = (character) => req(`/api/parser/dashboards/loot?${characterQuery(character)}`)
export const getDashboardLeveling = (character) => req(`/api/parser/dashboards/leveling?${characterQuery(character)}`)
export const getDashboardRaids = (character) => req(`/api/parser/dashboards/raids?${characterQuery(character)}`)
export const getDashboardConsidered = (character) => req(`/api/parser/dashboards/considered?${characterQuery(character)}`)
export const getDashboardMob = (character, name) => {
  const q = characterQuery(character)
  q.set('name', name || '')
  return req(`/api/parser/dashboards/mob?${q}`)
}
export const getDashboardOverlay = (character, kind) => {
  const q = characterQuery(character)
  q.set('kind', kind || 'xp')
  return req(`/api/parser/dashboards/overlay?${q}`)
}
export const postDashboardFavourite = (body) =>
  req('/api/parser/dashboards/favourites', { method: 'POST', body: JSON.stringify(body) })
export const postDashboardLockout = (body) =>
  req('/api/parser/dashboards/lockouts', { method: 'POST', body: JSON.stringify(body) })
export const postDashboardMoteGrade = (grade) =>
  req('/api/parser/dashboards/mote-grade', { method: 'POST', body: JSON.stringify({ grade }) })
export const postDashboardWishes = (character, wishes) =>
  req('/api/parser/dashboards/wishes', { method: 'POST', body: JSON.stringify({ character, wishes: wishes || [] }) })

export const getCompanionBuffs = (character, loadout) => {
  const q = characterQuery(character)
  q.set('loadout', loadout || '')
  return req(`/api/parser/companion/buffs?${q}`)
}
export const postCompanionDuration = (body) =>
  req('/api/parser/companion/duration', { method: 'POST', body: JSON.stringify(body) })
export const postCompanionManual = (body) =>
  req('/api/parser/companion/manual', { method: 'POST', body: JSON.stringify(body) })
export const getCompanionRespawns = (character) =>
  req(`/api/parser/companion/respawns?${characterQuery(character)}`)
export const postCompanionRespawn = (body) =>
  req('/api/parser/companion/respawn', { method: 'POST', body: JSON.stringify(body) })
export const getCompanionMaps = (character) =>
  req(`/api/parser/companion/maps?${characterQuery(character)}`)
export const postCompanionExaltations = (body) =>
  req('/api/parser/companion/exaltations', { method: 'POST', body: JSON.stringify(body) })
export const postCompanionExaltationNote = (body) =>
  req('/api/parser/companion/exaltation-note', { method: 'POST', body: JSON.stringify(body) })
export const postCompanionResists = (body) =>
  req('/api/parser/companion/resists', { method: 'POST', body: JSON.stringify(body) })
export const postCompanionExport = (body) =>
  req('/api/parser/companion/export', { method: 'POST', body: JSON.stringify(body) })
export const postCompanionImport = (body) =>
  req('/api/parser/companion/import', { method: 'POST', body: JSON.stringify(body) })
export const getCompanionPerf = () => req('/api/parser/companion/perf')

/** SSE path. `events` limits the hub to those types. Empty means every event. */
export function parserStreamPath(events) {
  const list = Array.isArray(events) ? events : []
  const cleaned = list.map((item) => String(item || '').trim()).filter(Boolean)
  if (!cleaned.length) return '/api/parser/stream'
  return `/api/parser/stream?events=${encodeURIComponent(cleaned.join(','))}`
}

/** SSE for replay progress and live fight updates. No-op when EventSource is missing. */
export function openParserStream(handlers = {}) {
  if (typeof EventSource === 'undefined') {
    return { close() {} }
  }
  const source = new EventSource(parserStreamPath(handlers.events))
  const types = ['hello', 'progress', 'fight', 'live', 'reset', 'upgrade', 'roster', 'message', 'alert', 'toast']
  for (const type of types) {
    source.addEventListener(type, (ev) => {
      let data = null
      try {
        data = JSON.parse(ev.data)
      } catch (_) {
        data = null
      }
      const fn = handlers[type] || handlers.onEvent
      if (typeof fn === 'function') fn(data, ev)
    })
  }
  source.onerror = () => {
    if (typeof handlers.onError === 'function') handlers.onError()
  }
  return {
    close() {
      source.close()
    },
  }
}
