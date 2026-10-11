import { useEffect, useState } from 'react'
import {
  getParserAlerts,
  getParserAlertsRecent,
  openParserStream,
  postParserAlert,
  postParserAlertImport,
} from './parserApi.js'
import { AUTO_HIDE_NOTE, FULLSCREEN_NOTE } from './overlayView.js'

const CHARM_NOTE = 'Charm break is unverified. No matching line is in the log corpus, so this rule stays off.'

function desktop() {
  return typeof window !== 'undefined' ? window.eqDesktop : null
}

export function AlertsPanel({ character }) {
  const [rules, setRules] = useState([])
  const [share, setShare] = useState('')
  const [recent, setRecent] = useState([])
  const [importText, setImportText] = useState('')
  const [notice, setNotice] = useState('')
  const [name, setName] = useState('')
  const [pattern, setPattern] = useState('')
  const [scope, setScope] = useState('fight')
  const [locked, setLocked] = useState(false)
  const [opacity, setOpacity] = useState(0.85)
  const [closeToTray, setCloseToTray] = useState(false)

  const refresh = () => {
    getParserAlerts().then((body) => {
      setRules(body?.rules || [])
      setShare(body?.share || '')
    }).catch((err) => setNotice(String(err?.message || err)))
    getParserAlertsRecent().then((body) => {
      setRecent(body?.alerts || [])
    }).catch(() => {})
  }

  useEffect(() => {
    refresh()
    const stream = openParserStream({
      alert: () => refresh(),
    })
    const desk = desktop()
    if (desk?.getSettings) {
      desk.getSettings().then((settings) => {
        if (settings?.closeToTray === true) setCloseToTray(true)
      }).catch(() => {})
    }
    return () => stream.close()
  }, [])

  const saveRule = async (rule) => {
    setNotice('')
    try {
      const body = await postParserAlert(rule)
      setRules(body?.rules || [])
    } catch (err) {
      setNotice(String(err?.message || err))
    }
  }

  const openOverlay = (id) => {
    const desk = desktop()
    if (!desk?.openOverlay) {
      setNotice('Overlay windows open in the desktop app.')
      return
    }
    desk.openOverlay({ id, character: character || '', scope, locked, opacity }).catch((err) => {
      setNotice(String(err?.message || err))
    })
  }

  return (
    <div className="panel" data-testid="alerts-panel">
      <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Alerts</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Built-in alerts use log lines the parser already reads. Charm break stays off.
        A shared string only adds rules. It does not delete rules you already have.
      </p>
      <p className="note">{FULLSCREEN_NOTE}</p>
      <p className="note">{AUTO_HIDE_NOTE}</p>
      {notice ? <p className="warn-box" role="alert">{notice}</p> : null}

      <div className="parser-toolbar">
        <button type="button" onClick={() => openOverlay('dps')}>Open DPS meter</button>
        <button type="button" onClick={() => openOverlay('heal')}>Open heal meter</button>
        <button type="button" onClick={() => openOverlay('alert')}>Open alert banner</button>
        <label>
          Scope
          <select aria-label="Overlay scope" value={scope} onChange={(event) => setScope(event.target.value)}>
            <option value="fight">Fight</option>
            <option value="zone">Zone</option>
          </select>
        </label>
        <label>
          <input type="checkbox" checked={locked} onChange={(event) => {
            const next = event.target.checked
            setLocked(next)
            desktop()?.setOverlayLock?.({ locked: next })
          }} />
          Lock (click-through)
        </label>
        <label>
          Opacity
          <input
            aria-label="Overlay opacity"
            type="range"
            min="35"
            max="100"
            value={Math.round(opacity * 100)}
            onChange={(event) => {
              const next = Number(event.target.value) / 100
              setOpacity(next)
              desktop()?.setOverlayOpacity?.({ opacity: next })
            }}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={closeToTray}
            onChange={(event) => {
              const next = event.target.checked
              setCloseToTray(next)
              desktop()?.setSettings?.({ closeToTray: next })
            }}
          />
          Close to tray
        </label>
      </div>
      <p className="muted">Close to tray is off, so the window X still quits. Snap pulls a meter to the screen edge when you move it.</p>

      <ul className="parser-loadouts" data-testid="alert-rules">
        {rules.map((rule) => (
          <li key={rule.id}>
            <label>
              <input
                type="checkbox"
                checked={!!rule.enabled && !rule.gated}
                disabled={!!rule.gated}
                onChange={(event) => saveRule({ ...rule, enabled: event.target.checked })}
              />
              {rule.name}
            </label>
            {rule.gated ? <span className="note">{rule.note || CHARM_NOTE}</span> : null}
            {rule.note && !rule.gated ? <span className="muted"> {rule.note}</span> : null}
            {rule.kind === 'raid_slain' ? (
              <input
                aria-label="Raid target names"
                value={(rule.names || []).join(', ')}
                placeholder="Names, separated by commas"
                onChange={(event) => {
                  const names = event.target.value.split(',').map((part) => part.trim()).filter(Boolean)
                  saveRule({ ...rule, names })
                }}
              />
            ) : null}
            {rule.kind === 'regex' ? (
              <input
                aria-label={`Pattern for ${rule.name}`}
                value={rule.pattern || ''}
                onChange={(event) => saveRule({ ...rule, pattern: event.target.value.slice(0, 200) })}
              />
            ) : null}
            <label>
              Cooldown seconds
              <input
                aria-label={`Cooldown for ${rule.name}`}
                type="number"
                min="0"
                value={rule.cooldown || 0}
                onChange={(event) => saveRule({ ...rule, cooldown: Number(event.target.value) || 0 })}
              />
            </label>
            <label>
              Sound
              <select
                aria-label={`Sound for ${rule.name}`}
                value={rule.sound || 'speech'}
                onChange={(event) => saveRule({ ...rule, sound: event.target.value })}
              >
                <option value="speech">OS speech</option>
                <option value="file">Sound file</option>
                <option value="none">None</option>
              </select>
            </label>
            {rule.sound === 'file' ? (
              <button type="button" onClick={async () => {
                const picked = await desktop()?.pickSoundFile?.()
                if (picked?.path) saveRule({ ...rule, sound_file: picked.path })
              }}>
                {rule.sound_file || 'Choose .wav or .mp3'}
              </button>
            ) : null}
          </li>
        ))}
      </ul>

      <form
        className="parser-toolbar"
        onSubmit={(event) => {
          event.preventDefault()
          const id = `custom-${Date.now()}`
          saveRule({
            id,
            name: name || 'Custom line',
            enabled: true,
            kind: 'regex',
            pattern: pattern.slice(0, 200),
            cooldown: 0,
            sound: 'speech',
            builtin: false,
          })
          setName('')
          setPattern('')
        }}
      >
        <input aria-label="Alert name" value={name} placeholder="Alert name" onChange={(event) => setName(event.target.value)} />
        <input aria-label="Alert pattern" value={pattern} placeholder="Log line pattern" onChange={(event) => setPattern(event.target.value)} />
        <button type="submit">Add line rule</button>
      </form>

      <label className="field">
        Share string
        <textarea aria-label="Alert share string" readOnly value={share} rows={3} />
      </label>
      <form
        onSubmit={async (event) => {
          event.preventDefault()
          setNotice('')
          try {
            const body = await postParserAlertImport(importText)
            setRules(body?.rules || [])
            setImportText('')
            setNotice(body?.added ? `Added ${body.added}.` : 'No new rules.')
            const listed = await getParserAlerts()
            setShare(listed?.share || '')
          } catch (err) {
            setNotice(String(err?.message || err))
          }
        }}
      >
        <label className="field">
          Import share string
          <textarea aria-label="Import alert share" value={importText} rows={3} onChange={(event) => setImportText(event.target.value)} />
        </label>
        <button type="submit">Import</button>
      </form>

      <h3 className="parser-subhead">Recent alerts</h3>
      {recent.length ? (
        <ul>
          {recent.map((row) => (
            <li key={`${row.rule_id}:${row.ts}:${row.message}`}>{row.ts} · {row.message}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">No alerts yet.</p>
      )}
    </div>
  )
}
