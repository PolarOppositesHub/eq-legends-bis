import { useEffect, useState } from 'react'

function desktop() {
  if (typeof window === 'undefined') return null
  return window.eqDesktop || null
}

/**
 * In-app caption. Dragging uses the CSS drag region, and a double-click there
 * is the native maximize toggle. This component does not also listen for
 * dblclick, or the window would toggle twice.
 * Close goes through the shell, which still quits or minimizes to the tray.
 */
export function TitleBar() {
  const [maximized, setMaximized] = useState(false)

  useEffect(() => {
    const desk = desktop()
    if (!desk) return undefined
    let stop = () => {}
    if (typeof desk.windowState === 'function') {
      desk.windowState().then((state) => {
        if (state && typeof state.maximized === 'boolean') setMaximized(state.maximized)
      }).catch(() => {})
    }
    if (typeof desk.onWindowState === 'function') {
      const unsubscribe = desk.onWindowState((state) => {
        setMaximized(!!(state && state.maximized))
      })
      if (typeof unsubscribe === 'function') stop = unsubscribe
    }
    return () => stop()
  }, [])

  return (
    <header className="app-titlebar" data-testid="app-titlebar">
      <div className="app-titlebar-title">EQ Legends BiS</div>
      <div className="app-titlebar-controls">
        <button
          type="button"
          className="app-titlebar-btn"
          aria-label="Minimize"
          data-testid="titlebar-minimize"
          onClick={() => desktop()?.windowMinimize?.()}
        >
          −
        </button>
        <button
          type="button"
          className="app-titlebar-btn"
          aria-label={maximized ? 'Restore' : 'Maximize'}
          data-testid="titlebar-maximize"
          onClick={() => desktop()?.windowToggleMaximize?.()}
        >
          {maximized ? '❐' : '□'}
        </button>
        <button
          type="button"
          className="app-titlebar-btn app-titlebar-close"
          aria-label="Close"
          data-testid="titlebar-close"
          onClick={() => desktop()?.windowClose?.()}
        >
          ×
        </button>
      </div>
    </header>
  )
}
