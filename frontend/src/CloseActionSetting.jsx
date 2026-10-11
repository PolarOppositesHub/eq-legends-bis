import { useEffect, useState } from 'react'

function desktop() {
  if (typeof window === 'undefined') return null
  return window.eqDesktop || null
}

export function xButtonValue(settings) {
  if (settings?.xButton === 'tray' || settings?.xButton === 'quit') return settings.xButton
  if (settings?.closeToTray === true) return 'tray'
  return 'quit'
}

export function CloseActionSetting({ value, onChange, error = '' }) {
  const action = value === 'tray' ? 'tray' : 'quit'
  return (
    <div className="settings-row" data-testid="x-button-setting">
      <div>
        <label htmlFor="x-button-action">X button</label>
        <span className="muted">
          Quit closes the app. Minimize to tray keeps it running. The first time it goes to the tray, a notice says how to open it again.
        </span>
      </div>
      <div>
        <select
          id="x-button-action"
          aria-label="X button"
          value={action}
          onChange={(event) => onChange?.(event.target.value)}
        >
          <option value="quit">Quit</option>
          <option value="tray">Minimize to tray</option>
        </select>
        {error ? <p className="warn-box" role="alert" data-testid="x-button-error">{error}</p> : null}
      </div>
    </div>
  )
}

export function CloseActionSettingHost() {
  const [value, setValue] = useState('quit')
  const [error, setError] = useState('')

  useEffect(() => {
    const desk = desktop()
    if (!desk?.getSettings) return undefined
    let cancel = false
    desk.getSettings().then((settings) => {
      if (!cancel) setValue(xButtonValue(settings))
    }).catch((err) => {
      if (!cancel) setError(String(err?.message || err || 'Could not read the X button setting.'))
    })
    return () => { cancel = true }
  }, [])

  return (
    <CloseActionSetting
      value={value}
      error={error}
      onChange={async (next) => {
        const action = next === 'tray' ? 'tray' : 'quit'
        setValue(action)
        setError('')
        const desk = desktop()
        if (!desk?.setSettings) {
          setError('This setting is saved in the desktop app.')
          return
        }
        try {
          const saved = await desk.setSettings({ xButton: action })
          if (saved && saved.ok === false) {
            setError(saved.message || 'Could not save the X button setting.')
          } else if (saved?.xButton) {
            setValue(xButtonValue(saved))
          }
        } catch (err) {
          setError(String(err?.message || err || 'Could not save the X button setting.'))
        }
      }}
    />
  )
}
