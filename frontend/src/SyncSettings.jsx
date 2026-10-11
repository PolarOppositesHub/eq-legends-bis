import { useEffect, useState } from 'react'
import { ICLOUD_TIP, ICLOUD_WAITING, SYNC_PROVIDERS, syncStatusText } from './syncSettings.js'

export function SyncSettings({
  status,
  deviceName,
  onDeviceName,
  onProvider,
  onChooseFolder,
  onSignIn,
  onSignOut,
  onSyncNow,
  onDeviceNameCommit,
}) {
  const provider = status?.provider === 'onedrive' ? 'onedrive' : (status?.provider === 'folder' ? 'folder' : '')
  const line = syncStatusText(status)
  const waiting = status?.message === ICLOUD_WAITING
  return (
    <div className="settings-row" data-testid="sync-settings">
      <div>
        <label htmlFor="sync-provider">Sync</label>
        <span className="muted">
          Currency counts, wish list pins, class and level, and inventory sections for each character.
          Google Drive is a later version.
        </span>
      </div>
      <div>
        <select
          id="sync-provider"
          aria-label="Sync provider"
          value={provider}
          onChange={(event) => onProvider?.(event.target.value)}
        >
          <option value="">Off</option>
          {SYNC_PROVIDERS.map((choice) => (
            <option key={choice.id} value={choice.id}>{choice.label}</option>
          ))}
        </select>
        <label htmlFor="sync-device-name" style={{ display: 'block', marginTop: '0.45rem' }}>
          Device name
          <input
            id="sync-device-name"
            aria-label="Device name"
            value={deviceName || ''}
            onChange={(event) => onDeviceName?.(event.target.value)}
            onBlur={() => onDeviceNameCommit?.(deviceName)}
          />
        </label>
        {provider === 'folder' && (
          <div style={{ marginTop: '0.45rem' }}>
            <button type="button" data-testid="sync-choose-folder" onClick={() => onChooseFolder?.()}>
              Choose folder
            </button>
            {status?.folder ? <p className="muted" data-testid="sync-folder">{status.folder}</p> : null}
            <p className="note" data-testid="sync-icloud-tip">{status?.icloud_tip || ICLOUD_TIP}</p>
          </div>
        )}
        {provider === 'onedrive' && (
          <div style={{ marginTop: '0.45rem' }}>
            {status?.account ? <p className="muted" data-testid="sync-account">{status.account}</p> : null}
            {status?.account ? (
              <button type="button" data-testid="sync-sign-out" onClick={() => onSignOut?.()}>Sign out</button>
            ) : (
              <button type="button" data-testid="sync-sign-in" onClick={() => onSignIn?.()}>Sign in</button>
            )}
          </div>
        )}
        <div style={{ marginTop: '0.45rem' }}>
          <button type="button" data-testid="sync-now" onClick={() => onSyncNow?.()}>Sync now</button>
        </div>
        {status?.last_synced ? (
          <p className="muted" data-testid="sync-last">Last synced {String(status.last_synced).replace('T', ' ')}</p>
        ) : null}
        {line ? (
          <p className={waiting ? 'note' : 'warn-box'} role={waiting ? 'status' : 'alert'} data-testid="sync-status">
            {line}
          </p>
        ) : null}
      </div>
    </div>
  )
}

function desktop() {
  if (typeof window === 'undefined') return null
  return window.eqDesktop || null
}

export function SyncSettingsHost() {
  const [status, setStatus] = useState(null)
  const [deviceName, setDeviceName] = useState('')

  const load = async () => {
    try {
      const response = await fetch('/api/sync/status')
      if (!response.ok) return
      const body = await response.json()
      setStatus(body)
      setDeviceName(body.device_name || '')
    } catch (_) {
      /* Browser preview has no sidecar. */
    }
  }

  useEffect(() => {
    load()
  }, [])

  const save = async (patch) => {
    try {
      const response = await fetch('/api/sync/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      })
      if (!response.ok) return
      const body = await response.json()
      setStatus(body)
      if (body.device_name) setDeviceName(body.device_name)
    } catch (_) { /* leave the form as the user left it */ }
  }

  return (
    <SyncSettings
      status={status}
      deviceName={deviceName}
      onDeviceName={setDeviceName}
      onDeviceNameCommit={(name) => save({ device_name: name })}
      onProvider={(provider) => save({ provider })}
      onChooseFolder={async () => {
        const picked = await desktop()?.pickSyncFolder?.()
        if (picked?.folder) await save({ provider: 'folder', folder: picked.folder })
        else await load()
      }}
      onSignIn={async () => {
        const result = await desktop()?.signInOneDrive?.()
        if (result && result.ok === false) {
          setStatus((prev) => ({
            ...(prev || {}),
            provider: 'onedrive',
            status: 'error',
            error: result.error || 'OneDrive sign-in failed.',
          }))
          return
        }
        await load()
      }}
      onSignOut={async () => {
        await desktop()?.signOutOneDrive?.()
        try {
          await fetch('/api/sync/onedrive/sign-out', { method: 'POST' })
        } catch (_) { /* status reload shows the signed-out row */ }
        await load()
      }}
      onSyncNow={async () => {
        try {
          await fetch('/api/sync/now', { method: 'POST' })
        } catch (_) { /* the status line stays on the last error */ }
        await load()
      }}
    />
  )
}
