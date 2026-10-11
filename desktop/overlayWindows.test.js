const assert = require('node:assert/strict')
const test = require('node:test')
const {
  overlayBrowserOptions,
  clickThroughCall,
  lockWindowCalls,
  overlayAfterLockToggle,
  overlayRaisePlan,
  alertPlaybackPlan,
  alertContentDismiss,
  snapBounds,
  keepOnScreen,
  overlayRoute,
  readOverlayMap,
  appearanceFromRow,
  APPEARANCE_DEFAULTS,
} = require('./overlayWindows')

test('a locked overlay is click-through and not resizable', () => {
  const options = overlayBrowserOptions('dps', { locked: true, x: 12, y: 40, width: 300, height: 200 })
  assert.equal(options.frame, false)
  assert.equal(options.transparent, true)
  assert.equal(options.alwaysOnTop, true)
  assert.equal(options.skipTaskbar, true)
  assert.equal(options.focusable, false)
  assert.equal(options.resizable, false)
  assert.equal(options.movable, false)
  assert.deepEqual(clickThroughCall(true), { ignore: true, forward: true })
  assert.deepEqual(clickThroughCall(false), { ignore: false })
})

test('blur raises the overlay and does not hide or close it', () => {
  for (const reason of ['blur', 'show', 'lock', 'unlock', 'display', 'interval']) {
    const plan = overlayRaisePlan(reason, reason === 'lock')
    assert.equal(plan.hide, false)
    assert.equal(plan.close, false)
    assert.equal(plan.raise, true)
    assert.equal(plan.alwaysOnTop, true)
    assert.equal(plan.level, 'screen-saver')
    assert.equal(plan.fallbackLevel, 'pop-up-menu')
    assert.equal(plan.visibleOnAllWorkspaces, true)
    assert.equal(plan.visibleOnFullScreen, true)
    assert.equal(plan.skipTaskbar, true)
    assert.equal(plan.injection, false)
    assert.equal(plan.intervalMs, 2000)
  }
  assert.equal(overlayRaisePlan('blur', true).focusable, false)
  assert.equal(overlayRaisePlan('unlock', false).focusable, true)
  const sound = alertPlaybackPlan({ sound: 'speech', message: 'You died.' })
  assert.equal(sound.host, 'hidden-window')
  assert.equal(sound.visibleOverlay, false)
  assert.equal(sound.injection, false)
  assert.equal(sound.speak, true)
  assert.equal(alertPlaybackPlan({ sound: 'file', sound_file: 'C:\\alert.wav' }).file, 'C:\\alert.wav')
  assert.equal(alertPlaybackPlan({ sound: 'none' }).speak, false)
  const dismissed = alertContentDismiss()
  assert.equal(dismissed.hideWindow, false)
  assert.equal(dismissed.closeWindow, false)
  assert.equal(dismissed.contentVisible, false)
})

test('an unlocked overlay can move and keeps a saved position', () => {
  const options = overlayBrowserOptions('heal', { locked: false, x: 8, y: 9 })
  assert.equal(options.resizable, true)
  assert.equal(options.movable, true)
  assert.equal(options.x, 8)
  assert.equal(options.y, 9)
})

test('bounds snap to the work area edge', () => {
  const snapped = snapBounds(
    { x: 10, y: 100, width: 200, height: 100 },
    { x: 0, y: 0, width: 1000, height: 800 },
  )
  assert.equal(snapped.x, 0)
  assert.equal(snapped.y, 100)
})

test('overlay routes and saved state round-trip', () => {
  assert.equal(overlayRoute('dps', 'Zasariz', 'zone'), '/?overlay=dps&character=Zasariz&scope=zone')
  const map = readOverlayMap({
    overlays: { dps: { open: true, locked: true, x: 3, y: 4, scope: 'fight', character: 'Zasariz' } },
  })
  assert.equal(map.dps.open, true)
  assert.equal(map.dps.locked, true)
  assert.equal(map.dps.character, 'Zasariz')
  assert.equal(map.dps.backgroundOpacity, 0.78)
  assert.equal(map.dps.textOpacity, 1)
})

test('a window created locked is movable after unlock', () => {
  const created = overlayBrowserOptions('dps', { locked: true, x: 12, y: 40, width: 300, height: 200 })
  assert.equal(created.movable, false)
  assert.equal(created.resizable, false)
  const unlocked = overlayAfterLockToggle(created, false)
  assert.equal(unlocked.movable, true)
  assert.equal(unlocked.resizable, true)
  assert.equal(unlocked.gripVisible, true)
  assert.deepEqual(unlocked.ignoreMouse, { ignore: false })
  assert.deepEqual(lockWindowCalls(false), {
    ignoreMouse: { ignore: false },
    movable: true,
    resizable: true,
    gripVisible: true,
  })
  const lockedAgain = overlayAfterLockToggle(unlocked, true)
  assert.equal(lockedAgain.movable, false)
  assert.equal(lockedAgain.resizable, false)
  assert.equal(lockedAgain.gripVisible, false)
  assert.deepEqual(lockedAgain.ignoreMouse, { ignore: true, forward: true })
  assert.deepEqual(clickThroughCall(true), { ignore: true, forward: true })
})

test('a saved position stays put and an off-screen one returns to a monitor', () => {
  const displays = [
    { workArea: { x: 0, y: 0, width: 1920, height: 1080 } },
    { workArea: { x: 1920, y: 0, width: 1280, height: 800 } },
  ]
  const kept = overlayBrowserOptions('heal', { x: 2000, y: 40, width: 300, height: 200 }, displays)
  assert.equal(kept.x, 2000)
  assert.equal(kept.y, 40)
  assert.equal(kept.width, 300)
  assert.equal(kept.height, 200)
  const lost = keepOnScreen({ x: 9000, y: -2000, width: 320, height: 360 }, [
    { workArea: { x: 0, y: 0, width: 1280, height: 720 } },
  ])
  assert.ok(lost.x >= 0 && lost.x + lost.width <= 1280)
  assert.ok(lost.y >= 0 && lost.y + lost.height <= 720)
  const restored = overlayBrowserOptions('dps', { x: 9000, y: 40, width: 320, height: 200 }, displays)
  assert.ok(restored.x >= 0 && restored.x < 1920)
  assert.equal(appearanceFromRow({}).showTitleWhenLocked, APPEARANCE_DEFAULTS.showTitleWhenLocked)
})
