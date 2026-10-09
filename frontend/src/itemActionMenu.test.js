import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { BisItemName, ItemActionMenu, bisItemHandlers } from './itemActionMenu.jsx'

test('best in slot click opens the shared menu and hover does not', () => {
  const calls = []
  const handlers = bisItemHandlers({
    name: 'Cloak of Flames',
    onHover: () => calls.push('hover'),
    onMove: () => calls.push('move'),
    onLeave: () => calls.push('leave'),
    onOpenMenu: (name) => calls.push(`menu:${name}`),
  })
  handlers.onMouseEnter()
  handlers.onClick({ preventDefault() {}, stopPropagation() {} })
  assert.deepEqual(calls, ['hover', 'menu:Cloak of Flames'])
  const html = renderToStaticMarkup(React.createElement(BisItemName, {
    name: 'Cloak of Flames',
    onHover() {},
    onMove() {},
    onLeave() {},
    onOpenMenu() {},
  }))
  assert.match(html, /data-bis-item="1"/)
  assert.match(html, /Cloak of Flames/)
})

test('the item menu is the same Item Search and eqlwiki actions', () => {
  const html = renderToStaticMarkup(React.createElement(ItemActionMenu, {
    menu: { name: 'Mask of Song', url: 'https://eqlwiki.com/Mask_of_Song', allowWiki: true, x: 1, y: 2 },
    wishPinned: false,
    onSearch() {},
    onWiki() {},
    onWish() {},
    onClose() {},
  }))
  assert.match(html, /data-testid="item-action-menu"/)
  assert.match(html, /Open in Item Search/)
  assert.match(html, /Open on eqlwiki/)
  assert.match(html, /Pin to Wish list/)
  const pinned = renderToStaticMarkup(React.createElement(ItemActionMenu, {
    menu: { name: 'Mask of Song', allowWiki: false, x: 1, y: 2 },
    wishPinned: true,
    onSearch() {},
    onWiki() {},
    onWish() {},
    onClose() {},
  }))
  assert.equal(pinned.includes('Open on eqlwiki'), false)
  assert.match(pinned, /Unpin from Wish list/)
})
