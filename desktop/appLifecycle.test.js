const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const lifecycle = require('./appLifecycle')

test('the window X quits unless Minimize to tray was chosen', () => {
  assert.equal(lifecycle.xButtonAction({}), 'quit')
  assert.equal(lifecycle.xButtonAction({ closeToTray: false }), 'quit')
  assert.equal(lifecycle.xButtonAction({ xButton: 'quit', closeToTray: true }), 'quit')
  assert.equal(lifecycle.shouldMinimizeToTray({}), false)
  assert.equal(lifecycle.xButtonAction({ xButton: 'tray' }), 'tray')
  assert.equal(lifecycle.xButtonAction({ closeToTray: true }), 'tray')
  assert.equal(lifecycle.shouldMinimizeToTray({ closeToTray: true }), true)
})

test('the tray notice is shown once the first time the app stays open', () => {
  assert.equal(lifecycle.shouldShowTrayNotice({ xButton: 'tray' }), true)
  assert.equal(lifecycle.shouldShowTrayNotice({ xButton: 'tray', trayNoticeShown: true }), false)
  assert.equal(lifecycle.shouldShowTrayNotice({ xButton: 'quit' }), false)
  assert.match(lifecycle.TRAY_NOTICE, /Open EQ Legends BiS/)
})

test('revealing a window restores, shows, and focuses it', () => {
  const calls = []
  const win = {
    isMinimized: () => true,
    isDestroyed: () => false,
    restore: () => calls.push('restore'),
    show: () => calls.push('show'),
    focus: () => calls.push('focus'),
  }
  assert.deepEqual(lifecycle.revealWindow(win), { action: 'focus' })
  assert.deepEqual(calls, ['restore', 'show', 'focus'])
  assert.deepEqual(lifecycle.revealWindow(null), { action: 'recreate' })
  assert.deepEqual(lifecycle.revealWindow({ isDestroyed: () => true }), { action: 'recreate' })
})

test('Windows kills an orphaned backend tree with taskkill /PID /T /F', () => {
  assert.deepEqual(lifecycle.taskkillArgs(4321), ['/PID', '4321', '/T', '/F'])
})

test('a stale backend is reclaimed only when the health check is this app', () => {
  const recorded = { pid: 4321, port: 8765 }
  assert.equal(lifecycle.shouldReclaimSidecar(recorded, { ok: true, version: '1.1.12' }), true)
  assert.equal(lifecycle.shouldReclaimSidecar(recorded, null), false)
  assert.equal(lifecycle.shouldReclaimSidecar(recorded, { ok: true }), false)
  assert.equal(lifecycle.shouldReclaimSidecar({ port: 8765 }, { ok: true, version: '1.1.12' }), false)
  const netstat = '  TCP    127.0.0.1:8765    0.0.0.0:0    LISTENING    4321\r\n  TCP    127.0.0.1:87650   0.0.0.0:0    LISTENING    99'
  assert.equal(lifecycle.listenerPidFromListing(netstat, 8765), 4321)
  const ss = 'LISTEN 0 128 127.0.0.1:8765 0.0.0.0:* users:(("python",pid=4321,fd=5))'
  assert.equal(lifecycle.listenerPidFromListing(ss, 8765), 4321)
})

test('a 401 refreshes the OneDrive token once and retries once', async () => {
  const calls = []
  let posted = null
  const result = await lifecycle.syncWithAuthRefresh({
    sync: async () => {
      calls.push('sync')
      if (calls.length === 1) {
        return { status: 'error', auth_expired: true, error: 'OneDrive sign-in expired. Sign in again.' }
      }
      return { ok: true, status: 'ok', auth_expired: false, error: '' }
    },
    refresh: async () => {
      calls.push('refresh')
      return { ok: true, access_token: 'new-token', account: 'Josh' }
    },
    postToken: async (body) => {
      posted = body
      calls.push('post')
    },
  })
  assert.deepEqual(calls, ['sync', 'refresh', 'post', 'sync'])
  assert.equal(result.status, 'ok')
  assert.deepEqual(posted, { access_token: 'new-token', account: 'Josh' })
})

test('a failed OneDrive refresh shows Microsoft\'s error and does not retry', async () => {
  let syncs = 0
  let refreshes = 0
  const failed = await lifecycle.syncWithAuthRefresh({
    sync: async () => {
      syncs += 1
      return { status: 'error', auth_expired: true, error: 'nope' }
    },
    refresh: async () => {
      refreshes += 1
      return { ok: false, error: 'invalid_grant: AADSTS70008: The refresh token has expired due to inactivity.' }
    },
    postToken: async () => {
      throw new Error('should not post')
    },
  })
  assert.equal(syncs, 1)
  assert.equal(refreshes, 1)
  assert.match(failed.error, /^invalid_grant: AADSTS70008:/)
  assert.equal(failed.auth_expired, true)

  const generic = await lifecycle.syncWithAuthRefresh({
    sync: async () => ({ status: 'error', auth_expired: true }),
    refresh: async () => ({ ok: false }),
    postToken: async () => {
      throw new Error('should not post')
    },
  })
  assert.equal(generic.error, 'OneDrive sign-in expired. Sign in again.')
  assert.equal(generic.auth_expired, true)

  const signedOut = await lifecycle.syncWithAuthRefresh({
    sync: async () => ({ status: 'error', auth_expired: true }),
    refresh: async () => ({ ok: false, signedOut: true, error: 'Sign in to OneDrive' }),
    postToken: async () => {
      throw new Error('should not post')
    },
  })
  assert.equal(signedOut.error, 'Sign in to OneDrive')
  assert.equal(signedOut.auth_expired, false)
  assert.equal(signedOut.error.includes('expired'), false)

  const update = await lifecycle.syncWithAuthRefresh({
    sync: async () => ({ status: 'error', auth_expired: true }),
    refresh: async () => ({ ok: false, needsUpdate: true, error: 'Sign in to OneDrive again to finish the update' }),
    postToken: async () => {
      throw new Error('should not post')
    },
  })
  assert.equal(update.error, 'Sign in to OneDrive again to finish the update')
  assert.equal(update.auth_expired, false)
  assert.equal(update.reauth, true)

  const thrown = await lifecycle.syncWithAuthRefresh({
    sync: async () => ({ status: 'error', auth_expired: true }),
    refresh: async () => {
      throw new Error('network down')
    },
    postToken: async () => {
      throw new Error('should not post')
    },
  })
  assert.equal(thrown.error, 'network down')
  assert.equal(thrown.auth_expired, false)
})

test('the shell quits on the window X, opens from the tray, and reclaims a stale backend', () => {
  const main = fs.readFileSync(path.join(__dirname, 'main.js'), 'utf8')
  const pkg = require('./package.json')
  assert.match(main, /shouldMinimizeToTray\(readSettings\(\)\)/)
  assert.match(main, /label: 'Open EQ Legends BiS'/)
  assert.match(main, /tray\.on\('double-click'/)
  assert.match(main, /app\.on\('second-instance'/)
  assert.match(main, /focusRunningInstance/)
  assert.match(main, /app\.on\('will-quit'/)
  assert.match(main, /taskkillArgs/)
  assert.match(main, /sidecar\.pid/)
  assert.match(main, /shouldReclaimSidecar/)
  assert.match(main, /listenerPidFromListing/)
  assert.match(main, /eq:sync-now/)
  assert.match(main, /syncWithAuthRefresh/)
  assert.ok(pkg.build.files.includes('appLifecycle.js'))
  const preload = fs.readFileSync(path.join(__dirname, 'preload.js'), 'utf8')
  assert.match(preload, /syncNow:/)
})
