import assert from 'node:assert/strict'
import test from 'node:test'
import {
  HOVER_DISMISS_REASONS,
  createHoverTipSession,
  dismissHover,
  floatingDismissAction,
  startItemHover,
} from './hoverTip.js'

const MASK = 'Polished Mithril Mask (Exaltation)'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

test('a stat popup that resolves after the pointer leaves does not come back', async () => {
  const session = createHoverTipSession()
  const pending = deferred()
  const shown = []
  const hover = startItemHover(session, {
    name: MASK,
    load: () => pending.promise,
    tipText: (detail) => (detail.tooltipLines || []).join('\n'),
    coords: () => ({ x: 12, y: 24 }),
    onShow: (tip) => shown.push(tip.statsText),
    delayMs: 0,
  })
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.deepEqual(shown, ['Loading…'])
  hover.cancel()
  pending.resolve({ name: MASK, tooltipLines: ['AC: 12'] })
  await new Promise((resolve) => setTimeout(resolve, 0))
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(shown.some((text) => String(text).includes('AC:')), false)
  assert.equal(session.isCurrent(hover.gen), false)
})

test('scroll, blur, menu, tab, Escape, and an outside click dismiss a stuck popup', async () => {
  for (const reason of HOVER_DISMISS_REASONS) {
    const session = createHoverTipSession()
    const pending = deferred()
    const shown = []
    const hover = startItemHover(session, {
      name: MASK,
      load: () => pending.promise,
      tipText: (detail) => (detail.tooltipLines || []).join('\n'),
      coords: () => ({ x: 1, y: 2 }),
      onShow: (tip) => shown.push(tip.statsText),
      delayMs: 0,
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
    dismissHover(session, reason)
    pending.resolve({ name: MASK, tooltipLines: ['AC: 4'] })
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))
    assert.equal(shown.some((text) => String(text).includes('AC:')), false, reason)
    assert.equal(session.isCurrent(hover.gen), false, reason)
  }
})

test('a newer hover wins over an older detail fetch', async () => {
  const session = createHoverTipSession()
  const first = deferred()
  const shown = []
  startItemHover(session, {
    name: 'Old Mask',
    load: () => first.promise,
    tipText: (detail) => detail.tooltipLines.join('\n'),
    coords: () => ({ x: 1, y: 1 }),
    onShow: (tip) => shown.push(`${tip.name}:${tip.statsText}`),
    delayMs: 0,
  })
  await new Promise((resolve) => setTimeout(resolve, 0))
  const second = startItemHover(session, {
    name: 'New Mask',
    cached: { name: 'New Mask', tooltipLines: ['HP: 10'] },
    tipText: (detail) => detail.tooltipLines.join('\n'),
    coords: () => ({ x: 3, y: 4 }),
    onShow: (tip) => shown.push(`${tip.name}:${tip.statsText}`),
  })
  first.resolve({ name: 'Old Mask', tooltipLines: ['AC: 1'] })
  await new Promise((resolve) => setTimeout(resolve, 0))
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(shown.some((text) => text.startsWith('Old Mask:AC')), false)
  assert.equal(shown.some((text) => text.startsWith('New Mask:')), true)
  assert.equal(session.isCurrent(second.gen), true)
})

test('Escape closes the top popup and an outside click closes a tip', () => {
  const escape = { type: 'keydown', key: 'Escape' }
  assert.equal(floatingDismissAction(escape, { confirm: true, menu: true, tip: true }), 'confirm')
  assert.equal(floatingDismissAction(escape, { menu: true, tip: true }), 'menu')
  assert.equal(floatingDismissAction(escape, { tip: true }), 'tip')
  assert.equal(floatingDismissAction(escape, { modal: true }), 'modal')
  assert.equal(floatingDismissAction(escape, {}), null)

  const outside = { type: 'mousedown', target: { closest: () => null } }
  assert.equal(floatingDismissAction(outside, { tip: true }), 'outside')
  const onTrigger = {
    type: 'mousedown',
    target: { closest: (sel) => (sel.includes('data-item-tip-trigger') ? {} : null) },
  }
  assert.equal(floatingDismissAction(onTrigger, { tip: true }), null)
  const onMenu = {
    type: 'mousedown',
    target: { closest: (sel) => (sel.includes('mob-drop-menu') ? {} : null) },
  }
  assert.equal(floatingDismissAction(onMenu, { menu: true }), null)
})
