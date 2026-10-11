import { useEffect, useState } from 'react'
import { getParserMeters, openParserStream } from './parserApi.js'
import { FULLSCREEN_NOTE, ZONE_METER_NOTE, meterRows, overlayIdFromSearch } from './overlayView.js'

function speak(text) {
  if (!text || typeof window === 'undefined' || !window.speechSynthesis) return
  const utter = new SpeechSynthesisUtterance(text)
  window.speechSynthesis.speak(utter)
}

async function playFile(path) {
  if (!path || !window.eqDesktop?.readSoundFile) return
  const dataUrl = await window.eqDesktop.readSoundFile(path)
  if (!dataUrl) return
  const audio = new Audio(dataUrl)
  audio.play().catch(() => {})
}

function playAlert(alert) {
  if (!alert) return
  if (alert.sound === 'file' && alert.sound_file) {
    playFile(alert.sound_file)
    return
  }
  if (alert.sound === 'none') return
  speak(alert.message || alert.name || 'Alert')
}

export default function OverlayApp() {
  const params = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '')
  const id = overlayIdFromSearch(params.toString() ? `?${params.toString()}` : '')
  const [character, setCharacter] = useState(params.get('character') || '')
  const [scope, setScope] = useState(params.get('scope') === 'zone' ? 'zone' : 'fight')
  const [opacity, setOpacity] = useState(0.85)
  const [meter, setMeter] = useState(null)
  const [banner, setBanner] = useState(null)

  useEffect(() => {
    if (!window.eqDesktop?.onOverlayConfig) return undefined
    return window.eqDesktop.onOverlayConfig((config) => {
      if (!config || config.id !== id) return
      if (typeof config.character === 'string') setCharacter(config.character)
      if (config.scope === 'zone' || config.scope === 'fight') setScope(config.scope)
      if (config.opacity != null) setOpacity(Number(config.opacity) || 0.85)
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
        playAlert(last)
      },
    })
    return () => stream.close()
  }, [])

  const rows = meterRows(meter)
  const title = id === 'heal' ? 'Heal meter' : id === 'alert' ? 'Alerts' : 'DPS meter'
  return (
    <div className="overlay-window" style={{ opacity }} data-overlay-id={id || 'dps'}>
      <header className="overlay-title">{title}</header>
      {id === 'alert' ? (
        <p className="overlay-banner" data-testid="overlay-alert-banner">
          {banner?.message || 'Waiting for an alert.'}
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
                  <span>{row.heals}</span>
                ) : (
                  <span>
                    {row.damage}
                    {scope === 'fight' && row.dps != null ? ` · ${row.dps} DPS` : ''}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <p className="overlay-note">{FULLSCREEN_NOTE}</p>
        </>
      )}
    </div>
  )
}
