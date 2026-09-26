/**
 * Where the working session is stored.
 *
 * The desktop shell loads the UI from http://127.0.0.1:<port>/ and picks a
 * new free port every launch. localStorage is origin-scoped (scheme + host +
 * port), so a value saved on one launch is invisible on the next.
 *
 * In the desktop app the session is written through Electron into userData
 * (AppData), which is not versioned and is left in place by the NSIS
 * installer and electron-updater. Browser dev (stable Vite origin) falls
 * back to localStorage. Saved loadouts keep their own key and are not
 * read or written here.
 */

export const WORKSPACE_STORAGE_KEY = 'eq-legends-bis-workspace-session-v1'
export const WORKSPACE_SAVE_DEBOUNCE_MS = 400

function defaultEnv() {
  return {
    getDesktop() {
      if (typeof window === 'undefined') return null
      return window.eqDesktop || null
    },
    storage() {
      try {
        if (typeof localStorage === 'undefined') return null
        return localStorage
      } catch (_) {
        return null
      }
    },
  }
}

function desktopApi(env) {
  const desktop = env.getDesktop?.()
  if (!desktop || !desktop.isDesktop) return null
  if (typeof desktop.getWorkspace !== 'function') return null
  return desktop
}

export async function loadWorkspaceSession(env = defaultEnv()) {
  const desktop = desktopApi(env)
  if (desktop) {
    try {
      const res = await desktop.getWorkspace()
      if (res && res.ok && res.workspace && typeof res.workspace === 'object') {
        return res.workspace
      }
    } catch (_) {
      /* missing file or bridge failure → first-launch defaults */
    }
    return null
  }
  const storage = env.storage?.()
  if (!storage) return null
  try {
    const raw = storage.getItem(WORKSPACE_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    return parsed
  } catch (_) {
    return null
  }
}

export async function saveWorkspaceSession(session, env = defaultEnv()) {
  if (!session || typeof session !== 'object' || Array.isArray(session)) {
    return { ok: false }
  }
  const desktop = desktopApi(env)
  if (desktop && typeof desktop.setWorkspace === 'function') {
    try {
      const res = await desktop.setWorkspace(session)
      return res && res.ok === false ? res : { ok: true }
    } catch (e) {
      return { ok: false, message: String(e && e.message ? e.message : e) }
    }
  }
  const storage = env.storage?.()
  if (!storage) return { ok: false }
  try {
    storage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(session))
    return { ok: true }
  } catch (e) {
    return { ok: false, message: String(e && e.message ? e.message : e) }
  }
}

export async function clearWorkspaceSession(env = defaultEnv()) {
  const desktop = desktopApi(env)
  if (desktop && typeof desktop.clearWorkspace === 'function') {
    try {
      await desktop.clearWorkspace()
      return { ok: true }
    } catch (e) {
      return { ok: false, message: String(e && e.message ? e.message : e) }
    }
  }
  const storage = env.storage?.()
  if (!storage) return { ok: false }
  try {
    storage.removeItem(WORKSPACE_STORAGE_KEY)
    return { ok: true }
  } catch (e) {
    return { ok: false, message: String(e && e.message ? e.message : e) }
  }
}
