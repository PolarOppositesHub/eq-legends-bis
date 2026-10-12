import { useEffect, useState } from 'react'
import {
  GOOGLE_UNVERIFIED_NOTE,
  ICLOUD_TIP,
  ICLOUD_WAITING,
  SYNC_PROVIDERS,
  connectionResultText,
  formatSyncedAt,
  skippedFilesText,
  syncFailureText,
  syncStatusText,
} from './syncSettings.js'

export function SyncSettings({
  status,
  deviceName,
  onDeviceName,
  onProvider,
  onChooseFolder,
  onSignIn,
  onSignOut,
  onSyncNow,
  onTestConnection,
  onDeviceNameCommit,
  syncing = false,
  syncedAt = '',
  syncError = '',
  connectionText = '',
  testingConnection = false,
}) {
  const provider = status?.provider === 'onedrive' || status?.provider === 'google' || status?.provider === 'folder'
    ? status.provider
    : ''
  const cloud = provider === 'onedrive' || provider === 'google'
  const line = syncError || syncStatusText(status)
  const waiting = !syncError && status?.message === ICLOUD_WAITING
  const skippedNote = !syncError && !syncing ? skippedFilesText(status?.skipped) : ''
  return (
    <div className="settings-row" data-testid="sync-settings">
      <div>
        <label htmlFor="sync-provider">Sync</label>
        <span className="muted">
          Currency counts, wish list pins, class and level, and inventory sections for each character.
          Sync folder, OneDrive, or the hidden Google Drive app folder.
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
        {cloud && (
          <div style={{ marginTop: '0.45rem' }}>
            {provider === 'google' ? (
              <p className="note" data-testid="sync-google-unverified">{GOOGLE_UNVERIFIED_NOTE}</p>
            ) : null}
            {status?.account ? <p className="muted" data-testid="sync-account">{status.account}</p> : null}
            {(!status?.account || status?.reauth) ? (
              <button type="button" data-testid="sync-sign-in" onClick={() => onSignIn?.()}>Sign in</button>
            ) : null}
            {status?.account ? (
              <button type="button" data-testid="sync-sign-out" onClick={() => onSignOut?.()}>Sign out</button>
            ) : null}
            <div style={{ marginTop: '0.45rem' }}>
              <button
                type="button"
                data-testid="sync-test-connection"
                disabled={!!testingConnection}
                onClick={() => { if (!testingConnection) onTestConnection?.() }}
              >
                {testingConnection ? 'Testing…' : 'Test connection'}
              </button>
            </div>
            {connectionText ? (
              <p className="note" role="status" data-testid="sync-connection">{connectionText}</p>
            ) : null}
          </div>
        )}
        <div style={{ marginTop: '0.45rem' }}>
          <button
            type="button"
            data-testid="sync-now"
            disabled={!!syncing}
            aria-busy={syncing ? 'true' : 'false'}
            onClick={() => { if (!syncing) onSyncNow?.() }}
          >
            {syncing ? 'Syncing…' : 'Sync now'}
          </button>
        </div>
        {syncedAt && !syncing ? (
          <p className="muted" data-testid="sync-synced-at">Synced at {syncedAt}</p>
        ) : null}
        {skippedNote ? (
          <p className="note" role="status" data-testid="sync-skipped">{skippedNote}</p>
        ) : null}
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
  const [syncing, setSyncing] = useState(false)
  const [syncedAt, setSyncedAt] = useState('')
  const [syncError, setSyncError] = useState('')
  const [connectionText, setConnectionText] = useState('')
  const [testingConnection, setTestingConnection] = useState(false)

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
    const onError = (event) => {
      const message = event && event.detail
      if (message) setSyncError(String(message))
    }
    window.addEventListener('eq-sync-error', onError)
    return () => window.removeEventListener('eq-sync-error', onError)
  }, [])

  const save = async (patch) => {
    try {
      const response = await fetch('/api/sync/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      })
      if (!response.ok) {
        let message = `Sync settings could not be saved (${response.status}).`
        try {
          const body = await response.json()
          if (typeof body?.detail === 'string' && body.detail) message = body.detail
        } catch (_) { /* the status line uses the status code */ }
        setSyncError(message)
        return
      }
      const body = await response.json()
      setStatus(body)
      setSyncError('')
      if (body.device_name) setDeviceName(body.device_name)
    } catch (err) {
      setSyncError(String(err?.message || err || 'Sync settings could not be saved.'))
    }
  }

  return (
    <SyncSettings
      status={status}
      deviceName={deviceName}
      onDeviceName={setDeviceName}
      onDeviceNameCommit={(name) => save({ device_name: name })}
      onProvider={(provider) => {
        setSyncError('')
        setConnectionText('')
        setSyncedAt('')
        save({ provider })
      }}
      onChooseFolder={async () => {
        const picked = await desktop()?.pickSyncFolder?.()
        if (picked?.folder) await save({ provider: 'folder', folder: picked.folder })
        else await load()
      }}
      onSignIn={async () => {
        const google = status?.provider === 'google'
        const signIn = google ? desktop()?.signInGoogleDrive : desktop()?.signInOneDrive
        if (typeof signIn !== 'function') {
          const message = google
            ? 'Google Drive sign-in is available in the desktop app.'
            : 'OneDrive sign-in is available in the desktop app.'
          setSyncError(message)
          return
        }
        const result = await signIn()
        if (result && result.ok === false) {
          const message = result.error || (google ? 'Google Drive sign-in failed.' : 'OneDrive sign-in failed.')
          setSyncError(message)
          setStatus((prev) => ({
            ...(prev || {}),
            provider: google ? 'google' : 'onedrive',
            status: 'error',
            error: message,
          }))
          return
        }
        setSyncError('')
        await load()
      }}
      onTestConnection={async () => {
        const google = status?.provider === 'google'
        setTestingConnection(true)
        setConnectionText('')
        try {
          const response = await fetch(google ? '/api/sync/google/test' : '/api/sync/onedrive/test', { method: 'POST' })
          let body = null
          try { body = await response.json() } catch (_) { body = null }
          setConnectionText(connectionResultText(body, response.ok ? 0 : response.status, google ? 'google' : 'onedrive'))
          if (body && body.ok === true) setSyncError('')
        } catch (err) {
          setConnectionText(String(err?.message || err || (google ? 'Google Drive connection test failed.' : 'OneDrive connection test failed.')))
        } finally {
          setTestingConnection(false)
          await load()
        }
      }}
      onSignOut={async () => {
        const google = status?.provider === 'google'
        try {
          if (google) await desktop()?.signOutGoogleDrive?.()
          else await desktop()?.signOutOneDrive?.()
          const response = await fetch(google ? '/api/sync/google/sign-out' : '/api/sync/onedrive/sign-out', { method: 'POST' })
          if (!response.ok) {
            setSyncError(`${google ? 'Google Drive' : 'OneDrive'} sign-out failed (${response.status}).`)
          } else {
            setSyncError('')
            setConnectionText('')
          }
        } catch (err) {
          setSyncError(String(err?.message || err || (google ? 'Google Drive sign-out failed.' : 'OneDrive sign-out failed.')))
        }
        await load()
      }}
      onSyncNow={async () => {
        setSyncing(true)
        setSyncError('')
        try {
          const result = await requestSyncNow()
          const problem = syncFailureText(result)
          if (problem) {
            setSyncError(problem)
            setSyncedAt('')
            setStatus((prev) => ({
              ...(prev || {}),
              ...result,
              status: result.status || 'error',
              error: problem,
            }))
          } else if (result.status === 'waiting') {
            setSyncedAt('')
            setStatus((prev) => ({ ...(prev || {}), ...result, error: '' }))
          } else {
            setSyncedAt(formatSyncedAt(new Date()))
            setStatus((prev) => ({ ...(prev || {}), ...result, error: '' }))
          }
        } catch (err) {
          const message = String(err?.message || err || 'Sync failed.')
          setSyncError(message)
          setSyncedAt('')
          setStatus((prev) => ({ ...(prev || {}), status: 'error', error: message }))
        } finally {
          setSyncing(false)
          await load()
        }
      }}
      syncing={syncing}
      syncedAt={syncedAt}
      syncError={syncError}
      connectionText={connectionText}
      testingConnection={testingConnection}
    />
  )
}

async function requestSyncNow() {
  const desk = desktop()
  if (desk?.syncNow) {
    const result = await desk.syncNow()
    if (!result || typeof result !== 'object') throw new Error('Sync did not return a status.')
    return result
  }
  const response = await fetch('/api/sync/now', { method: 'POST' })
  let body = null
  try { body = await response.json() } catch (_) { body = null }
  if (!response.ok) {
    const detail = body && (body.detail || body.error)
    throw new Error(typeof detail === 'string' ? detail : `Sync failed (${response.status}).`)
  }
  if (!body || typeof body !== 'object') throw new Error('Sync did not return a status.')
  return body
}
