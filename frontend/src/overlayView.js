/** Display helpers for overlay meters. Zone scope does not invent a DPS rate. */

export const ZONE_METER_NOTE = 'Totals are the sum of saved fights in this zone. DPS stays on the fight meter.'
export const FULLSCREEN_NOTE = 'Exclusive fullscreen draws over every window. This overlay does not send input to the game.'
export const AUTO_HIDE_NOTE = 'Auto-hide when EverQuest is not the focused window stays off. This version does not query the foreground window.'
export const OVERLAY_GAME_NOTE = 'For overlays over the game, set EQ Legends to borderless/windowed fullscreen. Exclusive fullscreen hides overlays (sound alerts still work).'
export const EXCLUSIVE_FULLSCREEN_WARNING = "EQ Legends is set to exclusive fullscreen, so overlays can't show over it. Switch to windowed/borderless (Fullscreen=0, window sized to your screen) or press Alt+Enter in game."

/** Voice and file alerts play in a hidden window, not the meter the game can cover. */
export function alertSoundRoute(alert) {
  const sound = alert && alert.sound
  return {
    host: 'hidden-window',
    visibleOverlay: false,
    injection: false,
    speak: sound !== 'none' && sound !== 'file',
    file: sound === 'file' ? String(alert.sound_file || '') : '',
  }
}

/** Clearing an alert banner leaves the overlay window open. */
export function dismissAlertContent() {
  return { hideWindow: false, closeWindow: false, contentVisible: false }
}

export const OVERLAY_CHOICES = [
  { id: 'dps', label: 'DPS' },
  { id: 'heal', label: 'Heal' },
  { id: 'alert', label: 'Alerts' },
]

export const DEFAULT_OVERLAY_APPEARANCE = {
  backgroundOpacity: 0.78,
  textOpacity: 1,
  textSize: 13,
  backgroundColor: '#0a0a0a',
  accentColor: '#b8962e',
  showTitleWhenLocked: true,
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

function hexRgb(value) {
  const hex = hexColor(value, '#000000').slice(1)
  const n = Number.parseInt(hex, 16)
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 }
}

export function overlayAppearance(raw) {
  const src = raw && typeof raw === 'object' ? raw : {}
  const legacyBackground = src.backgroundOpacity == null ? src.opacity : src.backgroundOpacity
  return {
    backgroundOpacity: clampUnit(legacyBackground, DEFAULT_OVERLAY_APPEARANCE.backgroundOpacity, 0, 1),
    textOpacity: clampUnit(src.textOpacity, DEFAULT_OVERLAY_APPEARANCE.textOpacity, 0, 1),
    textSize: Math.round(clampUnit(src.textSize, DEFAULT_OVERLAY_APPEARANCE.textSize, 10, 32)),
    backgroundColor: hexColor(src.backgroundColor, DEFAULT_OVERLAY_APPEARANCE.backgroundColor),
    accentColor: hexColor(src.accentColor, DEFAULT_OVERLAY_APPEARANCE.accentColor),
    showTitleWhenLocked: src.showTitleWhenLocked == null
      ? DEFAULT_OVERLAY_APPEARANCE.showTitleWhenLocked
      : !!src.showTitleWhenLocked,
  }
}

/** Background alpha is separate from the text color alpha. */
export function overlayChromeStyle(raw) {
  const look = overlayAppearance(raw)
  const bg = hexRgb(look.backgroundColor)
  return {
    backgroundColor: `rgba(${bg.r}, ${bg.g}, ${bg.b}, ${look.backgroundOpacity})`,
    color: `rgba(245, 240, 230, ${look.textOpacity})`,
    borderColor: look.accentColor,
    fontSize: `${look.textSize}px`,
    accent: look.accentColor,
  }
}

export function meterRows(payload) {
  const scope = payload?.scope === 'zone' ? 'zone' : 'fight'
  const rows = Array.isArray(payload?.rows) ? payload.rows : []
  return rows.map((row) => {
    const line = {
      source: row?.source || '',
      damage: Number(row?.damage) || 0,
      heals: Number(row?.heals) || 0,
    }
    if (scope === 'fight') {
      line.dps = row?.dps == null ? null : row.dps
      line.sdps = row?.sdps == null ? null : row.sdps
      line.hps = row?.hps == null ? null : row.hps
    }
    return line
  })
}

export function overlayCloseControl(locked) {
  return {
    visible: !locked,
    noDrag: true,
    label: 'Close overlay',
    text: '×',
  }
}

export function closeAllIds(rows, choices) {
  const list = Array.isArray(choices) ? choices : []
  return list.filter((choice) => rows?.[choice.id]?.open).map((choice) => choice.id)
}

export function overlayIdFromSearch(search) {
  const params = new URLSearchParams(search || '')
  const id = params.get('overlay')
  if (id === 'dps' || id === 'heal' || id === 'alert') return id
  return ''
}
