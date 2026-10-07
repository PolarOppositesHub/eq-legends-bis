/**
 * Item-stat popup session.
 *
 * A hover starts a generation. Leaving the trigger, scrolling, blurring,
 * opening a menu, changing tabs, Escape, or an outside click dismisses that
 * generation. A detail fetch that finishes later must not show the popup
 * again — that late write is what left tips stuck on screen.
 */

export const HOVER_DISMISS_REASONS = [
  'pointerleave',
  'scroll',
  'blur',
  'menu',
  'tab',
  'escape',
  'outside',
]

const NO_STATS = 'No catalog stats yet — click for Item Search or eqlwiki.'

export function createHoverTipSession() {
  let generation = 0
  return {
    get generation() {
      return generation
    },
    arm() {
      generation += 1
      return generation
    },
    dismiss() {
      generation += 1
      return generation
    },
    isCurrent(gen) {
      return gen === generation
    },
  }
}

export function dismissHover(session, reason) {
  if (!session || !HOVER_DISMISS_REASONS.includes(reason)) return session ? session.generation : 0
  return session.dismiss()
}

/**
 * Which floating layer Escape or an outside click should close.
 * Menus and confirms sit above the stat popup. A click on the trigger
 * or inside the popup/menu is not an outside click.
 */
export function floatingDismissAction(event, layers) {
  const open = layers || {}
  if (event?.type === 'keydown' && event.key === 'Escape') {
    if (open.confirm) return 'confirm'
    if (open.menu) return 'menu'
    if (open.tip) return 'tip'
    if (open.modal) return 'modal'
    return null
  }
  if (event?.type !== 'mousedown' && event?.type !== 'pointerdown') return null
  const target = event.target
  if (target && typeof target.closest === 'function') {
    if (target.closest('.hover-tip, .mob-drop-menu, .wiki-confirm-menu, .modal, .modal-backdrop')) return null
    if (target.closest('[data-item-tip-trigger]')) return null
  }
  if (open.tip || open.menu || open.confirm) return 'outside'
  return null
}

export function startItemHover(session, {
  name,
  cached,
  load,
  tipText,
  coords,
  onShow,
  delayMs = 90,
  schedule = (fn, ms) => setTimeout(fn, ms),
  clear = (id) => clearTimeout(id),
} = {}) {
  const gen = session.arm()
  const place = () => (typeof coords === 'function' ? (coords() || {}) : {})
  const show = (tip) => {
    if (!session.isCurrent(gen)) return false
    onShow({ ...tip, gen })
    return true
  }
  if (cached) {
    show({
      name: cached.name || name,
      statsText: typeof tipText === 'function' ? tipText(cached) : '',
      ...place(),
    })
    return {
      gen,
      cancel() {
        session.dismiss()
      },
    }
  }
  show({ name, statsText: 'Loading…', ...place() })
  let timer = schedule(async () => {
    timer = null
    let detail = null
    let failed = false
    try {
      detail = await load(name)
    } catch (_) {
      failed = true
    }
    if (!session.isCurrent(gen)) return
    if (failed || !detail) {
      show({ name, statsText: NO_STATS, ...place() })
      return
    }
    show({
      name: detail.name || name,
      statsText: typeof tipText === 'function' ? tipText(detail) : '',
      ...place(),
    })
  }, delayMs)
  return {
    gen,
    cancel() {
      if (timer != null) clear(timer)
      timer = null
      session.dismiss()
    },
  }
}
