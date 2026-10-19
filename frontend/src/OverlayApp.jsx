import { useEffect, useState } from 'react'
import { getCompanionBuffs, getDashboardOverlay, getParserMeters, openParserStream } from './parserApi.js'
import { buffOverlayText } from './companionView.js'
import { overlayCardText } from './dashboardsView.jsx'
import { formatAlertRates, formatDamage, formatPerSecond } from './parserView.js'
import {
  FULLSCREEN_NOTE,
  ZONE_METER_NOTE,
  dismissAlertContent,
  meterRows,
  overlayAppearance,
  overlayChromeStyle,
  overlayCloseControl,
  overlayIdFromSearch,
} from './overlayView.js'

function desktop() {
  if (typeof window === 'undefined') return null
  return window.eqDesktop || null
}

export default function OverlayApp() {
  const params = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '')
  const id = overlayIdFromSearch(params.toString() ? `?${params.toString()}` : '')
  const [character, setCharacter] = useState(params.get('character') || '')
  const [loadout, setLoadout] = useState(params.get('loadout') || '')
  const [scope, setScope] = useState(params.get('scope') === 'zone' ? 'zone' : 'fight')
  const [locked, setLocked] = useState(false)
  const [look, setLook] = useState(() => overlayAppearance({}))
  const [meter, setMeter] = useState(null)
  const [banner, setBanner] = useState(null)
  const [card, setCard] = useState(null)

  useEffect(() => {
    const desk = desktop()
    if (!desk?.onOverlayConfig) return undefined
    return desk.onOverlayConfig((config) => {
      if (!config || config.id !== id) return
      if (typeof config.character === 'string') setCharacter(config.character)
      if (typeof config.loadout === 'string') setLoadout(config.loadout)
      if (config.scope === 'zone' || config.scope === 'fight') setScope(config.scope)
      if (typeof config.locked === 'boolean') setLocked(config.locked)
      setLook(overlayAppearance(config))
    })
  }, [id])

  useEffect(() => {
    if (id !== 'buffs') return undefined
    if (!character) return undefined
    let cancelled = false
    const load = () => {
      if (!loadout) return
      getCompanionBuffs(character, loadout).then((body) => {
        if (!cancelled) setCard(body)
      }).catch(() => {})
    }
    load()
    const timer = setInterval(load, 2000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [id, character, loadout])

  useEffect(() => {
    if (id !== 'xp' && id !== 'con') return undefined
    if (!character) return undefined
    let cancelled = false
    const load = () => {
      getDashboardOverlay(character, id).then((body) => {
        if (!cancelled) setCard(body)
      }).catch(() => {})
    }
    load()
    const timer = setInterval(load, 2000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [id, character])

  useEffect(() => {
    if (id === 'alert' || id === 'xp' || id === 'con' || id === 'buffs' || !character) return undefined
    let cancelled = false
    const load = () => {
      getParserMeters(character, scope).then((body) => {
        if (!cancelled) setMeter(body)
      }).catch(() => {})
    }
    load()
    const timer = setInterval(load, 2000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [id, character, scope])

  useEffect(() => {
    const stream = openParserStream({
      alert: (data) => {
        const alerts = Array.isArray(data?.alerts) ? data.alerts : []
        const last = alerts[alerts.length - 1]
        if (!last) return
        setBanner(last)
      },
    })
    return () => stream.close()
  }, [])

  useEffect(() => {
    if (!banner || id !== 'alert') return undefined
    const timer = setTimeout(() => {
      const next = dismissAlertContent()
      if (!next.hideWindow && !next.closeWindow) setBanner(null)
    }, 8000)
    return () => clearTimeout(timer)
  }, [banner, id])

  const rows = meterRows(meter)
  const title = id === 'heal'
    ? 'Heal meter'
    : id === 'alert'
      ? 'Alerts'
      : id === 'xp'
        ? 'Experience'
        : id === 'con'
          ? 'Con card'
          : id === 'buffs'
            ? 'Buff timers'
            : 'DPS meter'
  const chrome = overlayChromeStyle(look)
  const showTitle = locked && look.showTitleWhenLocked
  const closeControl = overlayCloseControl(locked)
  const gripStyle = {
    backgroundColor: chrome.backgroundColor,
    color: chrome.color,
    borderColor: chrome.accent,
    fontSize: chrome.fontSize,
  }
  const bodyStyle = {
    backgroundColor: chrome.backgroundColor,
    color: chrome.color,
    borderColor: chrome.accent,
    fontSize: chrome.fontSize,
  }

  return (
    <div
      className="overlay-shell"
      data-overlay-id={id || 'dps'}
      data-locked={locked ? '1' : '0'}
    >
      {locked ? null : (
        <header className="overlay-grip" style={gripStyle} data-testid="overlay-grip">
          <span className="overlay-grip-title">{title}</span>
          <span className="overlay-grip-actions">
            <button
              type="button"
              className="overlay-no-drag"
              onClick={() => desktop()?.setOverlayLock?.({ id, locked: true })}
            >
              Lock
            </button>
            {closeControl.visible ? (
              <button
                type="button"
                className="overlay-no-drag overlay-close"
                aria-label={closeControl.label}
                data-testid="overlay-close"
                onClick={() => desktop()?.closeOverlay?.({ id })}
              >
                {closeControl.text}
              </button>
            ) : null}
          </span>
        </header>
      )}
      <div className="overlay-window overlay-body" style={bodyStyle}>
        {showTitle ? <header className="overlay-title">{title}</header> : null}
        {id === 'alert' ? (
          <p className="overlay-banner" data-testid="overlay-alert-banner">
            {formatAlertRates(banner?.message) || 'Waiting for an alert.'}
          </p>
        ) : id === 'xp' || id === 'con' ? (
          <p className="overlay-banner" data-testid={id === 'xp' ? 'overlay-xp' : 'overlay-con'}>
            {character ? overlayCardText(card) : 'Choose a character log in the Parser.'}
          </p>
        ) : id === 'buffs' ? (
          <p className="overlay-banner" data-testid="overlay-buffs">
            {character && loadout ? buffOverlayText(card) : 'Open buff timers from the overlays panel so this class loadout is included.'}
          </p>
        ) : (
          <>
            {scope === 'zone' ? <p className="overlay-note">{meter?.note || ZONE_METER_NOTE}</p> : null}
            {!character ? <p className="overlay-note">Choose a character log in the Parser.</p> : null}
            <ul className="overlay-rows" data-testid="overlay-meter-rows">
              {rows.map((row) => (
                <li key={row.source}>
                  <span>{row.source}</span>
                  {id === 'heal' ? (
                    <span>
                      {formatDamage(row.heals)}
                      {scope === 'fight' && row.hps != null ? ` · ${formatPerSecond(row.hps)} HPS` : ''}
                    </span>
                  ) : (
                    <span>
                      {formatDamage(row.damage)}
                      {scope === 'fight' && row.dps != null ? ` · ${formatPerSecond(row.dps)} DPS` : ''}
                    </span>
                  )}
                </li>
              ))}
            </ul>
            <p className="overlay-note">{FULLSCREEN_NOTE}</p>
          </>
        )}
      </div>
    </div>
  )
}
