/**
 * Overlay window options. Electron is not required here.
 * Lock is click-through. Position is saved per overlay id.
 */

const OVERLAY_IDS = ['dps', 'heal', 'alert']
const SNAP_PX = 16

function defaultSize(id) {
  if (id === 'alert') return { width: 460, height: 140 }
  if (id === 'heal') return { width: 300, height: 280 }
  return { width: 320, height: 360 }
}

function positive(value, fallback) {
  const n = Number(value)
  if (!Number.isFinite(n) || n < 80) return fallback
  return Math.round(n)
}

function overlayBrowserOptions(id, saved = {}) {
  const size = defaultSize(id)
  const locked = !!saved.locked
  const options = {
    width: positive(saved.width, size.width),
    height: positive(saved.height, size.height),
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: !locked,
    movable: !locked,
    hasShadow: false,
    backgroundColor: '#00000000',
  }
  if (saved.x != null && Number.isFinite(Number(saved.x))) options.x = Math.round(Number(saved.x))
  if (saved.y != null && Number.isFinite(Number(saved.y))) options.y = Math.round(Number(saved.y))
  return options
}

function clickThroughCall(locked) {
  if (locked) return { ignore: true, forward: true }
  return { ignore: false }
}

function snapBounds(bounds, area) {
  if (!bounds || !area) return bounds
  const next = {
    x: Number(bounds.x) || 0,
    y: Number(bounds.y) || 0,
    width: Number(bounds.width) || 0,
    height: Number(bounds.height) || 0,
  }
  if (Math.abs(next.x - area.x) <= SNAP_PX) next.x = area.x
  if (Math.abs(next.y - area.y) <= SNAP_PX) next.y = area.y
  const right = area.x + area.width
  const bottom = area.y + area.height
  if (Math.abs(next.x + next.width - right) <= SNAP_PX) next.x = right - next.width
  if (Math.abs(next.y + next.height - bottom) <= SNAP_PX) next.y = bottom - next.height
  return next
}

function overlayRoute(id, character, scope) {
  const params = new URLSearchParams()
  params.set('overlay', OVERLAY_IDS.includes(id) ? id : 'dps')
  if (character) params.set('character', String(character))
  if (scope === 'zone' || scope === 'fight') params.set('scope', scope)
  return `/?${params.toString()}`
}

function readOverlayMap(settings) {
  const raw = settings && settings.overlays
  const out = {}
  if (!raw || typeof raw !== 'object') return out
  for (const id of OVERLAY_IDS) {
    const row = raw[id]
    if (!row || typeof row !== 'object') continue
    out[id] = {
      open: !!row.open,
      locked: !!row.locked,
      x: row.x == null || !Number.isFinite(Number(row.x)) ? null : Number(row.x),
      y: row.y == null || !Number.isFinite(Number(row.y)) ? null : Number(row.y),
      width: positive(row.width, defaultSize(id).width),
      height: positive(row.height, defaultSize(id).height),
      opacity: clampOpacity(row.opacity),
      scope: row.scope === 'zone' ? 'zone' : 'fight',
      character: typeof row.character === 'string' ? row.character.slice(0, 80) : '',
    }
  }
  return out
}

function clampOpacity(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0.85
  return Math.max(0.35, Math.min(1, n))
}

module.exports = {
  OVERLAY_IDS,
  overlayBrowserOptions,
  clickThroughCall,
  snapBounds,
  overlayRoute,
  readOverlayMap,
  defaultSize,
}
