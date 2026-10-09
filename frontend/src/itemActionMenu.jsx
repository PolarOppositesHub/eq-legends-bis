/**
 * The item menu used by Known Loot, Character, and Best in Slot.
 * Hover stays with the caller. This module only handles the click menu.
 */
import React from 'react'

export function bisItemHandlers({ name, onHover, onMove, onLeave, onOpenMenu }) {
  return {
    onMouseEnter: (event) => onHover(event),
    onMouseMove: (event) => onMove(event),
    onMouseLeave: () => onLeave(),
    onBlur: () => onLeave(),
    onClick: (event) => {
      event.preventDefault()
      event.stopPropagation()
      onOpenMenu(name, event)
    },
  }
}

export function BisItemName({
  name,
  className = 'bis-item-name zone-link',
  onHover,
  onMove,
  onLeave,
  onOpenMenu,
  children,
}) {
  const handlers = bisItemHandlers({ name, onHover, onMove, onLeave, onOpenMenu })
  return (
    <button type="button" className={className} data-bis-item="1" data-item-tip-trigger="1" {...handlers}>
      {children || name}
    </button>
  )
}

export function ItemActionMenu({ menu, wishPinned, onSearch, onWiki, onWish, onClose }) {
  if (!menu) return null
  const pinned = !!wishPinned
  return (
    <div
      className="mob-drop-menu"
      style={{ left: menu.x, top: menu.y }}
      role="menu"
      aria-label={`Open ${menu.name}`}
      data-testid="item-action-menu"
    >
      <div className="mob-drop-menu-title">{menu.name}</div>
      <button type="button" role="menuitem" className="mob-drop-menu-item" onClick={() => onSearch(menu.name)}>
        Open in Item Search
      </button>
      {menu.allowWiki !== false ? (
        <button type="button" role="menuitem" className="mob-drop-menu-item" onClick={() => onWiki(menu.url)}>
          Open on eqlwiki
        </button>
      ) : null}
      <button
        type="button"
        role="menuitem"
        className="mob-drop-menu-item"
        data-testid="item-menu-wish"
        onClick={() => onWish(menu.name)}
      >
        {pinned ? 'Unpin from Wish list' : 'Pin to Wish list'}
      </button>
      <button type="button" role="menuitem" className="mob-drop-menu-item" onClick={onClose}>
        Close
      </button>
    </div>
  )
}

export function WishPin({ name, pinned, onToggle }) {
  return (
    <button
      type="button"
      className="wish-pin"
      aria-pressed={pinned ? 'true' : 'false'}
      data-wish-pin={name}
      onClick={(event) => {
        event.preventDefault()
        event.stopPropagation()
        onToggle(name)
      }}
    >
      {pinned ? 'Unpin' : 'Pin'}
    </button>
  )
}
