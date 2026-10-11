/**
 * Quit, tray, and OneDrive refresh decisions the shell can test without Electron.
 * The window X quits unless the user explicitly chose Minimize to tray.
 */
const X_QUIT = 'quit'
const X_TRAY = 'tray'
const TRAY_NOTICE_TITLE = 'EQ Legends BiS'
const TRAY_NOTICE = 'EQ Legends BiS is still open in the tray. Use Open EQ Legends BiS to show the window, or Quit to exit.'
const AUTH_EXPIRED_TEXT = 'OneDrive sign-in expired. Sign in again.'

function xButtonAction(settings) {
  const src = settings || {}
  if (src.xButton === X_TRAY || src.xButton === X_QUIT) return src.xButton
  if (src.closeToTray === true) return X_TRAY
  return X_QUIT
}

function shouldMinimizeToTray(settings) {
  return xButtonAction(settings) === X_TRAY
}

function shouldShowTrayNotice(settings) {
  const src = settings || {}
  return shouldMinimizeToTray(src) && src.trayNoticeShown !== true
}

/** Show, restore, and focus a living window. A missing window has to be created again. */
function revealWindow(win) {
  if (!win || (typeof win.isDestroyed === 'function' && win.isDestroyed())) {
    return { action: 'recreate' }
  }
  if (typeof win.isMinimized === 'function' && win.isMinimized()) win.restore()
  win.show()
  win.focus()
  return { action: 'focus' }
}

/** Windows fallback so an orphaned python child does not stay alive. */
function taskkillArgs(pid) {
  return ['/PID', String(pid), '/T', '/F']
}

function shouldReclaimSidecar(recorded, health) {
  if (!recorded || !recorded.pid || recorded.port == null || recorded.port === '') return false
  if (!health || health.ok !== true) return false
  if (typeof health.version !== 'string' || !health.version) return false
  return true
}

function listenerPidFromListing(text, port) {
  const wanted = Number(port)
  if (!Number.isInteger(wanted) || wanted <= 0) return null
  const suffix = `:${wanted}`
  for (const line of String(text || '').split(/\r?\n/)) {
    const bits = line.trim().split(/\s+/)
    const local = bits.find((part) => part.endsWith(suffix))
    if (!local) continue
    const got = Number(local.slice(local.lastIndexOf(':') + 1))
    if (got !== wanted) continue
    const inline = line.match(/pid=(\d+)/)
    if (inline) return Number(inline[1])
    const tail = Number(bits[bits.length - 1])
    if (Number.isInteger(tail) && tail > 0) return tail
  }
  return null
}

function isAuthExpiredStatus(status) {
  return !!(status && status.auth_expired === true)
}

/**
 * One Graph 401 refreshes the OneDrive token, posts it, and retries the sync once.
 * A failed refresh is the sign-in message and does not retry again.
 */
async function syncWithAuthRefresh({ sync, refresh, postToken }) {
  const first = await sync()
  if (!isAuthExpiredStatus(first)) return first
  let refreshed
  try {
    refreshed = await refresh()
  } catch (_) {
    return { ok: false, status: 'error', error: AUTH_EXPIRED_TEXT, auth_expired: true }
  }
  if (!refreshed || refreshed.ok !== true || !refreshed.access_token) {
    return { ok: false, status: 'error', error: AUTH_EXPIRED_TEXT, auth_expired: true }
  }
  await postToken({
    access_token: refreshed.access_token,
    account: refreshed.account || '',
  })
  return sync()
}

module.exports = {
  X_QUIT,
  X_TRAY,
  TRAY_NOTICE_TITLE,
  TRAY_NOTICE,
  AUTH_EXPIRED_TEXT,
  xButtonAction,
  shouldMinimizeToTray,
  shouldShowTrayNotice,
  revealWindow,
  taskkillArgs,
  shouldReclaimSidecar,
  listenerPidFromListing,
  isAuthExpiredStatus,
  syncWithAuthRefresh,
}
