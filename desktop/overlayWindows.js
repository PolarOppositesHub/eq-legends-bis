/**
 * Overlay window options. Electron is not required here.
 * Lock is click-through. Position and size are saved per overlay id.
 * Unlock must set movable again: a window created locked stays stuck
 * if the toggle only calls setResizable.
 */

const OVERLAY_IDS = ['dps', 'heal', 'alert', 'xp', 'con']
const SNAP_PX = 16

const APPEARANCE_DEFAULTS = {
  backgroundOpacity: 0.78,
  textOpacity: 1,
  textSize: 13,
  backgroundColor: '#0a0a0a',
  accentColor: '#b8962e',
  showTitleWhenLocked: true,
}

function defaultSize(id) {
  if (id === 'alert') return { width: 460, height: 140 }
  if (id === 'xp' || id === 'con') return { width: 320, height: 120 }
  if (id === 'heal') return { width: 300, height: 280 }
  return { width: 320, height: 360 }
}

function positive(value, fallback) {
  const n = Number(value)
  if (!Number.isFinite(n) || n < 80) return fallback
  return Math.round(n)
}

function clampUnit(value, fallback, min, max) {
  const n = Number(value)
  if (!Number.isFinite(n)) return fallback
  return Math.max(min, Math.min(max, n))
}

function hexColor(value, fallback) {
  const text = String(value || '').trim()
  if (/^#[0-9a-fA-F]{6}$/.test(text)) return text.toLowerCase()
  return fallback
}

function appearanceFromRow(row) {
  const src = row && typeof row === 'object' ? row : {}
  const legacyBackground = src.backgroundOpacity == null ? src.opacity : src.backgroundOpacity
  return {
    backgroundOpacity: clampUnit(legacyBackground, APPEARANCE_DEFAULTS.backgroundOpacity, 0, 1),
    textOpacity: clampUnit(src.textOpacity, APPEARANCE_DEFAULTS.textOpacity, 0, 1),
    textSize: Math.round(clampUnit(src.textSize, APPEARANCE_DEFAULTS.textSize, 10, 32)),
    backgroundColor: hexColor(src.backgroundColor, APPEARANCE_DEFAULTS.backgroundColor),
    accentColor: hexColor(src.accentColor, APPEARANCE_DEFAULTS.accentColor),
    showTitleWhenLocked: src.showTitleWhenLocked == null ? APPEARANCE_DEFAULTS.showTitleWhenLocked : !!src.showTitleWhenLocked,
  }
}

function workAreas(displays) {
  if (!displays) return []
  const list = Array.isArray(displays) ? displays : [displays]
  const areas = []
  for (const item of list) {
    const area = item && item.workArea ? item.workArea : item
    if (!area) continue
    const width = Number(area.width) || 0
    const height = Number(area.height) || 0
    if (width < 80 || height < 80) continue
    areas.push({
      x: Number(area.x) || 0,
      y: Number(area.y) || 0,
      width,
      height,
    })
  }
  return areas
}

function overlapBox(bounds, area) {
  const left = Math.max(bounds.x, area.x)
  const top = Math.max(bounds.y, area.y)
  const right = Math.min(bounds.x + bounds.width, area.x + area.width)
  const bottom = Math.min(bounds.y + bounds.height, area.y + area.height)
  const width = right - left
  const height = bottom - top
  if (width <= 0 || height <= 0) return null
  return { width, height, area: width * height }
}

/**
 * Keep a saved window on a connected monitor. A position that misses every
 * work area (monitor unplugged or rearranged) moves onto the first display.
 */
function keepOnScreen(bounds, displays) {
  if (!bounds) return bounds
  const next = {
    x: Math.round(Number(bounds.x) || 0),
    y: Math.round(Number(bounds.y) || 0),
    width: positive(bounds.width, 320),
    height: positive(bounds.height, 200),
  }
  const areas = workAreas(displays)
  if (!areas.length) return next
  let best = null
  for (const area of areas) {
    const hit = overlapBox(next, area)
    if (hit && (!best || hit.area > best.area)) best = { ...hit, areaBox: area }
  }
  if (best && best.width >= 48 && best.height >= 28) {
    const area = best.areaBox
    if (next.width > area.width) {
      next.width = area.width
      next.x = area.x
    } else {
      if (next.x < area.x) next.x = area.x
      if (next.x + next.width > area.x + area.width) next.x = area.x + area.width - next.width
    }
    if (next.height > area.height) {
      next.height = area.height
      next.y = area.y
    } else {
      if (next.y < area.y) next.y = area.y
      if (next.y + 28 > area.y + area.height) next.y = area.y + area.height - 28
    }
    return next
  }
  const home = areas[0]
  const width = Math.min(next.width, home.width)
  const height = Math.min(next.height, home.height)
  return {
    x: home.x + Math.max(0, Math.round((home.width - width) / 2)),
    y: home.y + Math.max(0, Math.round((home.height - height) / 2)),
    width,
    height,
  }
}

function overlayBrowserOptions(id, saved = {}, displays) {
  const size = defaultSize(id)
  const locked = !!saved.locked
  const width = positive(saved.width, size.width)
  const height = positive(saved.height, size.height)
  const options = {
    width,
    height,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: !locked,
    resizable: !locked,
    movable: !locked,
    hasShadow: false,
    backgroundColor: '#00000000',
  }
  const hasX = saved.x != null && Number.isFinite(Number(saved.x))
  const hasY = saved.y != null && Number.isFinite(Number(saved.y))
  if (hasX || hasY) {
    const placed = keepOnScreen({
      x: hasX ? Number(saved.x) : 0,
      y: hasY ? Number(saved.y) : 0,
      width,
      height,
    }, displays)
    options.x = placed.x
    options.y = placed.y
    options.width = placed.width
    options.height = placed.height
  }
  return options
}

function clickThroughCall(locked) {
  if (locked) return { ignore: true, forward: true }
  return { ignore: false }
}

/**
 * Calls the lock toggle must make. A window created with movable:false
 * stays immovable until setMovable(true). setResizable alone does not move it.
 */
function lockWindowCalls(locked) {
  const on = !!locked
  return {
    ignoreMouse: clickThroughCall(on),
    movable: !on,
    resizable: !on,
    gripVisible: !on,
  }
}

function overlayAfterLockToggle(options, locked) {
  const calls = lockWindowCalls(locked)
  return {
    ...(options || {}),
    locked: !!locked,
    movable: calls.movable,
    resizable: calls.resizable,
    ignoreMouse: calls.ignoreMouse,
    gripVisible: calls.gripVisible,
  }
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
    const appearance = appearanceFromRow(row)
    out[id] = {
      open: !!row.open,
      locked: !!row.locked,
      x: row.x == null || !Number.isFinite(Number(row.x)) ? null : Number(row.x),
      y: row.y == null || !Number.isFinite(Number(row.y)) ? null : Number(row.y),
      width: positive(row.width, defaultSize(id).width),
      height: positive(row.height, defaultSize(id).height),
      opacity: appearance.backgroundOpacity,
      scope: row.scope === 'zone' ? 'zone' : 'fight',
      character: typeof row.character === 'string' ? row.character.slice(0, 80) : '',
      ...appearance,
    }
  }
  return out
}

function clampOpacity(value) {
  return appearanceFromRow({ opacity: value }).backgroundOpacity
}

const ALWAYS_ON_TOP_LEVEL = 'screen-saver'
const ALWAYS_ON_TOP_FALLBACK = 'pop-up-menu'
const RAISE_INTERVAL_MS = 2000

/**
 * Clicking the game used to cover a meter: alwaysOnTop without a level
 * stays at 'floating', which a borderless game draws over, and lock never
 * set the level again. Blur must only raise the window.
 */
function overlayRaisePlan(reason, locked) {
  const onTimer = reason === 'interval'
  return {
    reason: reason || 'show',
    hide: false,
    close: false,
    raise: true,
    alwaysOnTop: true,
    level: ALWAYS_ON_TOP_LEVEL,
    fallbackLevel: ALWAYS_ON_TOP_FALLBACK,
    visibleOnAllWorkspaces: true,
    visibleOnFullScreen: true,
    skipTaskbar: true,
    focusable: !locked,
    // The 2s timer keeps z-order. It must not focus, show, or flip focusable.
    // setFocusable(true) on that timer blurs a text box in the main window.
    focus: false,
    show: false,
    moveTop: false,
    setFocusable: !onTimer,
    unfocusableDuringRaise: onTimer,
    intervalMs: RAISE_INTERVAL_MS,
    injection: false,
  }
}

/**
 * If a raise moved focus onto the overlay, put it back on the window that had it.
 * A raise that left focus alone does nothing.
 */
function focusAfterRaise({ beforeId, afterId, overlayId }) {
  if (afterId && overlayId && afterId === overlayId && beforeId && beforeId !== overlayId) {
    return { restoreFocusId: beforeId }
  }
  return { restoreFocusId: null }
}

/** Sounds play off the visible meter so exclusive fullscreen can still be heard. */
function alertPlaybackPlan(alert) {
  const sound = alert && alert.sound
  return {
    host: 'hidden-window',
    visibleOverlay: false,
    injection: false,
    speak: sound !== 'none' && sound !== 'file',
    file: sound === 'file' ? String((alert && alert.sound_file) || '') : '',
  }
}

function alertContentDismiss() {
  return { hideWindow: false, closeWindow: false, contentVisible: false }
}

/** Closing a meter keeps the saved row and records that it is not open. */
function closedOverlayPatch() {
  return { open: false }
}

module.exports = {
  OVERLAY_IDS,
  APPEARANCE_DEFAULTS,
  ALWAYS_ON_TOP_LEVEL,
  ALWAYS_ON_TOP_FALLBACK,
  RAISE_INTERVAL_MS,
  overlayBrowserOptions,
  clickThroughCall,
  lockWindowCalls,
  overlayAfterLockToggle,
  overlayRaisePlan,
  focusAfterRaise,
  alertPlaybackPlan,
  alertContentDismiss,
  closedOverlayPatch,
  snapBounds,
  keepOnScreen,
  overlayRoute,
  readOverlayMap,
  appearanceFromRow,
  defaultSize,
  clampOpacity,
}
