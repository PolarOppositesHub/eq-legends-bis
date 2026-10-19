import { useEffect, useState } from 'react'
import {
  DEFAULT_OVERLAY_APPEARANCE,
  EXCLUSIVE_FULLSCREEN_WARNING,
  OVERLAY_CHOICES,
  OVERLAY_GAME_NOTE,
  closeAllIds,
  overlayAppearance,
} from './overlayView.js'

function desktop() {
  if (typeof window === 'undefined') return null
  return window.eqDesktop || null
}

function emptyState() {
  const state = {}
  for (const choice of OVERLAY_CHOICES) {
    state[choice.id] = {
      id: choice.id,
      open: false,
      locked: false,
      scope: 'fight',
      ...DEFAULT_OVERLAY_APPEARANCE,
    }
  }
  return state
}

export function OverlaysPanel({ character, folder = '', fullscreenWarning = '', loadout = '' }) {
  const [rows, setRows] = useState(emptyState)
  const [notice, setNotice] = useState('')
  const [videoWarning, setVideoWarning] = useState(fullscreenWarning)

  useEffect(() => {
    const desk = desktop()
    if (!desk?.getOverlayState) return undefined
    let cancel = false
    desk.getOverlayState().then((state) => {
      if (cancel || !state) return
      setRows((current) => {
        const next = { ...current }
        for (const choice of OVERLAY_CHOICES) {
          const row = state[choice.id]
          if (!row) continue
          next[choice.id] = {
            ...current[choice.id],
            ...row,
            ...overlayAppearance(row),
            open: !!row.open,
            locked: !!row.locked,
            scope: row.scope === 'zone' ? 'zone' : 'fight',
          }
        }
        return next
      })
    }).catch(() => {})
    const stop = desk.onOverlayState?.((state) => {
      if (!state) return
      setRows((current) => {
        const next = { ...current }
        for (const choice of OVERLAY_CHOICES) {
          const row = state[choice.id]
          if (!row) continue
          next[choice.id] = {
            ...current[choice.id],
            ...row,
            ...overlayAppearance(row),
            open: !!row.open,
            locked: !!row.locked,
            scope: row.scope === 'zone' ? 'zone' : (current[choice.id]?.scope || 'fight'),
          }
        }
        return next
      })
    })
    return () => {
      cancel = true
      if (typeof stop === 'function') stop()
    }
  }, [])

  useEffect(() => {
    const desk = desktop()
    if (!desk?.getVideoMode) return undefined
    let cancel = false
    desk.getVideoMode({ folder }).then((body) => {
      if (cancel || !body) return
      setVideoWarning(body.fullscreen ? (body.warning || EXCLUSIVE_FULLSCREEN_WARNING) : '')
    }).catch(() => {})
    return () => { cancel = true }
  }, [folder])

  const fail = (err) => setNotice(String(err?.message || err))

  const openOrClose = (id) => {
    const desk = desktop()
    const row = rows[id]
    if (!desk?.openOverlay) {
      setNotice('Overlay windows open in the desktop app.')
      return
    }
    setNotice('')
    if (row?.open && desk.closeOverlay) {
      desk.closeOverlay({ id }).catch(fail)
      return
    }
    desk.openOverlay({
      id,
      character: character || '',
      scope: row?.scope === 'zone' ? 'zone' : 'fight',
      loadout: loadout || '',
    }).catch(fail)
  }

  const lockOne = (id, locked) => {
    const desk = desktop()
    if (!desk?.setOverlayLock) {
      setNotice('Overlay windows open in the desktop app.')
      return
    }
    setRows((current) => ({ ...current, [id]: { ...current[id], locked } }))
    desk.setOverlayLock({ id, locked }).catch(fail)
  }

  const closeAll = () => {
    const desk = desktop()
    const ids = closeAllIds(rows, OVERLAY_CHOICES)
    if (!desk?.closeOverlay) {
      setNotice('Overlay windows open in the desktop app.')
      return
    }
    setNotice('')
    for (const id of ids) desk.closeOverlay({ id }).catch(fail)
  }

  const lockAll = (locked) => {
    const desk = desktop()
    if (!desk?.setOverlayLock) {
      setNotice('Overlay windows open in the desktop app.')
      return
    }
    setRows((current) => {
      const next = { ...current }
      for (const choice of OVERLAY_CHOICES) next[choice.id] = { ...next[choice.id], locked }
      return next
    })
    desk.setOverlayLock({ locked }).catch(fail)
  }

  const patchLook = (id, patch) => {
    const desk = desktop()
    setRows((current) => ({
      ...current,
      [id]: { ...current[id], ...overlayAppearance({ ...current[id], ...patch }) },
    }))
    if (!desk?.setOverlayAppearance) return
    desk.setOverlayAppearance({ id, ...patch }).catch(fail)
  }

  return (
    <section className="overlays-panel" data-testid="overlays-panel">
      <h3 className="parser-subhead">Overlays</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        Open a meter, then drag its title bar. Lock makes it click-through. Each meter keeps its own look, and the meter updates as you change it.
      </p>
      <p className="note" data-testid="overlay-game-note">{OVERLAY_GAME_NOTE}</p>
      {videoWarning ? <p className="warn-box" data-testid="overlay-fullscreen-warning">{videoWarning}</p> : null}
      {notice ? <p className="warn-box" role="alert">{notice}</p> : null}
      <div className="overlays-actions">
        <button type="button" data-testid="overlays-close-all" onClick={closeAll}>Close all</button>
        <button type="button" data-testid="overlays-lock-all" onClick={() => lockAll(true)}>Lock all</button>
        <button type="button" data-testid="overlays-unlock-all" onClick={() => lockAll(false)}>Unlock all</button>
      </div>
      {OVERLAY_CHOICES.map((choice) => {
        const row = rows[choice.id] || emptyState()[choice.id]
        const look = overlayAppearance(row)
        return (
          <div className="overlays-row" key={choice.id} data-overlay-row={choice.id}>
            <h3>{choice.label}</h3>
            <span data-testid={`overlay-state-${choice.id}`}>
              {row.open ? 'Open' : 'Closed'}
              {' · '}
              {row.locked ? 'Locked' : 'Unlocked'}
            </span>
            <div className="overlays-actions">
              <button type="button" data-testid={`overlay-toggle-${choice.id}`} onClick={() => openOrClose(choice.id)}>
                {row.open ? `Close ${choice.label}` : `Open ${choice.label}`}
              </button>
              <button
                type="button"
                data-testid={`overlay-lock-${choice.id}`}
                onClick={() => lockOne(choice.id, !row.locked)}
              >
                {row.locked ? 'Unlock' : 'Lock'}
              </button>
              <label>
                Scope
                <select
                  aria-label={`${choice.label} scope`}
                  value={row.scope === 'zone' ? 'zone' : 'fight'}
                  onChange={(event) => {
                    const scope = event.target.value === 'zone' ? 'zone' : 'fight'
                    setRows((current) => ({ ...current, [choice.id]: { ...current[choice.id], scope } }))
                    if (row.open) {
                      desktop()?.openOverlay?.({ id: choice.id, character: character || '', scope })?.catch(fail)
                    }
                  }}
                >
                  <option value="fight">Fight</option>
                  <option value="zone">Zone</option>
                </select>
              </label>
            </div>
            <label>
              Background opacity
              <input
                aria-label={`${choice.label} background opacity`}
                type="range"
                min="0"
                max="100"
                value={Math.round(look.backgroundOpacity * 100)}
                onChange={(event) => patchLook(choice.id, { backgroundOpacity: Number(event.target.value) / 100 })}
              />
            </label>
            <label>
              Text opacity
              <input
                aria-label={`${choice.label} text opacity`}
                type="range"
                min="0"
                max="100"
                value={Math.round(look.textOpacity * 100)}
                onChange={(event) => patchLook(choice.id, { textOpacity: Number(event.target.value) / 100 })}
              />
            </label>
            <label>
              Text size
              <input
                aria-label={`${choice.label} text size`}
                type="range"
                min="10"
                max="32"
                value={look.textSize}
                onChange={(event) => patchLook(choice.id, { textSize: Number(event.target.value) })}
              />
            </label>
            <label>
              Background
              <input
                aria-label={`${choice.label} background color`}
                type="color"
                value={look.backgroundColor}
                onChange={(event) => patchLook(choice.id, { backgroundColor: event.target.value })}
              />
            </label>
            <label>
              Accent
              <input
                aria-label={`${choice.label} accent color`}
                type="color"
                value={look.accentColor}
                onChange={(event) => patchLook(choice.id, { accentColor: event.target.value })}
              />
            </label>
            <label>
              <input
                type="checkbox"
                aria-label={`${choice.label} title when locked`}
                checked={look.showTitleWhenLocked}
                onChange={(event) => patchLook(choice.id, { showTitleWhenLocked: event.target.checked })}
              />
              Title when locked
            </label>
            <button
              type="button"
              data-testid={`overlay-reset-${choice.id}`}
              onClick={() => {
                setRows((current) => ({
                  ...current,
                  [choice.id]: { ...current[choice.id], ...DEFAULT_OVERLAY_APPEARANCE },
                }))
                desktop()?.setOverlayAppearance?.({ id: choice.id, reset: true })?.catch(fail)
              }}
            >
              Reset to defaults
            </button>
          </div>
        )
      })}
    </section>
  )
}
