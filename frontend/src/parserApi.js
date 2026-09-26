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

export const getParserFights = (character) => {
  const q = new URLSearchParams()
  if (character) q.set('character', character)
  const qs = q.toString()
  return req(`/api/parser/fights${qs ? `?${qs}` : ''}`)
}

export const getParserFight = (id, mergePets) => {
  const q = new URLSearchParams({ merge_pets: mergePets ? 'true' : 'false' })
  return req(`/api/parser/fights/${encodeURIComponent(id)}?${q}`)
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

/** SSE for replay progress and live fight updates. No-op when EventSource is missing. */
export function openParserStream(handlers = {}) {
  if (typeof EventSource === 'undefined') {
    return { close() {} }
  }
  const source = new EventSource('/api/parser/stream')
  const types = ['hello', 'progress', 'fight', 'live', 'reset', 'upgrade', 'roster', 'message']
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
