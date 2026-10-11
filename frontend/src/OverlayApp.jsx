import { useEffect, useState } from 'react'
import { getParserMeters, openParserStream } from './parserApi.js'
import { formatAlertRates, formatDamage, formatPerSecond } from './parserView.js'
import {
  FULLSCREEN_NOTE,
  ZONE_METER_NOTE,
  dismissAlertContent,
  meterRows,
  overlayAppearance,
  overlayChromeStyle,
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
  const [scope, setScope] = useState(params.get('scope') === 'zone' ? 'zone' : 'fight')
  const [locked, setLocked] = useState(false)
  const [look, setLook] = useState(() => overlayAppearance({}))
  const [meter, setMeter] = useState(null)
  const [banner, setBanner] = useState(null)

  useEffect(() => {
    const desk = desktop()
    if (!desk?.onOverlayConfig) return undefined
    return desk.onOverlayConfig((config) => {
      if (!config || config.id !== id) return
      if (typeof config.character === 'string') setCharacter(config.character)
      if (config.scope === 'zone' || config.scope === 'fight') setScope(config.scope)
      if (typeof config.locked === 'boolean') setLocked(config.locked)
      setLook(overlayAppearance(config))
    })
  }, [id])

  useEffect(() => {
    if (id === 'alert' || !character) return undefined
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
  const title = id === 'heal' ? 'Heal meter' : id === 'alert' ? 'Alerts' : 'DPS meter'
  const chrome = overlayChromeStyle(look)
  const showTitle = locked && look.showTitleWhenLocked
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
            <button
              type="button"
              className="overlay-no-drag"
              onClick={() => desktop()?.closeOverlay?.({ id })}
            >
              Close
            </button>
          </span>
        </header>
      )}
      <div className="overlay-window overlay-body" style={bodyStyle}>
        {showTitle ? <header className="overlay-title">{title}</header> : null}
        {id === 'alert' ? (
          <p className="overlay-banner" data-testid="overlay-alert-banner">
            {formatAlertRates(banner?.message) || 'Waiting for an alert.'}
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
