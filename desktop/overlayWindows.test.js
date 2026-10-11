const assert = require('node:assert/strict')
const test = require('node:test')
const {
  overlayBrowserOptions,
  clickThroughCall,
  snapBounds,
  overlayRoute,
  readOverlayMap,
} = require('./overlayWindows')

test('a locked overlay is click-through and not resizable', () => {
  const options = overlayBrowserOptions('dps', { locked: true, x: 12, y: 40, width: 300, height: 200 })
  assert.equal(options.frame, false)
  assert.equal(options.transparent, true)
  assert.equal(options.alwaysOnTop, true)
  assert.equal(options.resizable, false)
  assert.equal(options.movable, false)
  assert.deepEqual(clickThroughCall(true), { ignore: true, forward: true })
  assert.deepEqual(clickThroughCall(false), { ignore: false })
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
})
