import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { SyncSettings } from './SyncSettings.jsx'
import {
  CONNECTED_APP_FOLDER,
  ICLOUD_TIP,
  ICLOUD_WAITING,
  SIGN_IN_TEXT,
  UPDATE_SIGN_IN_TEXT,
  connectionResultText,
  formatSyncedAt,
  mergeProjection,
  skippedFilesText,
  snapshotFromWorkspace,
  syncFailureText,
  syncStatusText,
} from './syncSettings.js'

test('sync folder settings include the iCloud keep-on-device tip', () => {
  const html = renderToStaticMarkup(React.createElement(SyncSettings, {
    status: {
      provider: 'folder',
      folder: 'C:\\Users\\Josh\\iCloudDrive\\EQLegendsBiS',
      device_name: 'Home PC',
      icloud_tip: ICLOUD_TIP,
      message: ICLOUD_WAITING,
      error: '',
    },
    deviceName: 'Home PC',
  }))
  assert.match(html, /data-testid="sync-settings"/)
  assert.match(html, /Sync folder/)
  assert.match(html, /OneDrive/)
  assert.equal(html.includes(ICLOUD_TIP), true)
  assert.equal(html.includes(ICLOUD_WAITING), true)
  assert.match(html, /data-testid="sync-now"/)
  assert.match(html, /Choose folder/)
  assert.equal(html.includes('Sign in'), false)
  assert.equal(html.includes('Test connection'), false)
})

test('OneDrive settings offer sign in until an account is stored', () => {
  const signedOut = renderToStaticMarkup(React.createElement(SyncSettings, {
    status: { provider: 'onedrive', account: '' },
    deviceName: 'Home PC',
  }))
  assert.match(signedOut, /data-testid="sync-sign-in"/)
  const signedIn = renderToStaticMarkup(React.createElement(SyncSettings, {
    status: { provider: 'onedrive', account: 'josh@example.com', last_synced: '2026-10-11T12:00:00' },
    deviceName: 'Home PC',
  }))
  assert.match(signedIn, /data-testid="sync-sign-out"/)
  assert.match(signedIn, /Last synced 2026-10-11 12:00:00/)
  assert.equal(syncStatusText({ message: ICLOUD_WAITING, error: 'nope' }), ICLOUD_WAITING)
  assert.match(signedOut, /data-testid="sync-test-connection"/)
  assert.match(signedOut, /Test connection/)
})

test('Sync now shows syncing, the local time, and the error', () => {
  const syncing = renderToStaticMarkup(React.createElement(SyncSettings, {
    status: { provider: 'onedrive', account: 'josh@example.com' },
    deviceName: 'Home PC',
    syncing: true,
  }))
  assert.match(syncing, /Syncing…/)
  assert.match(syncing, /disabled/)
  assert.match(syncing, /aria-busy="true"/)
  assert.equal(syncing.includes('>Sync now<'), false)

  const done = renderToStaticMarkup(React.createElement(SyncSettings, {
    status: { provider: 'folder', folder: 'C:\\sync' },
    deviceName: 'Home PC',
    syncedAt: '3:45 PM',
  }))
  assert.match(done, /data-testid="sync-synced-at"/)
  assert.match(done, /Synced at 3:45 PM/)
  assert.match(done, />Sync now</)
  assert.equal(done.includes('Syncing'), false)

  const failed = renderToStaticMarkup(React.createElement(SyncSettings, {
    status: { provider: 'onedrive', account: 'josh@example.com' },
    deviceName: 'Home PC',
    syncError: 'OneDrive sign-in expired. Sign in again.',
  }))
  assert.match(failed, /data-testid="sync-status"/)
  assert.match(failed, /OneDrive sign-in expired\. Sign in again\./)
  assert.equal(syncFailureText({ ok: false, error: 'Sync is not ready.' }), 'Sync is not ready.')
  assert.equal(syncFailureText({ ok: true, status: 'ok', error: '' }), '')

  const skipped = renderToStaticMarkup(React.createElement(SyncSettings, {
    status: { provider: 'onedrive', account: 'josh@example.com', status: 'ok', skipped: 2, error: '' },
    deviceName: 'Home PC',
    syncedAt: '3:45 PM',
  }))
  assert.match(skipped, /Synced at 3:45 PM/)
  assert.match(skipped, /data-testid="sync-skipped"/)
  assert.match(skipped, /Synced with 2 files skipped/)
  assert.equal(skipped.includes('role="alert"'), false)
  assert.equal(skippedFilesText(1), 'Synced with 1 file skipped')
  assert.equal(skippedFilesText(0), '')
  assert.equal(skippedFilesText(3), 'Synced with 3 files skipped')
  assert.equal(formatSyncedAt(new Date('not-a-date')), '')
  assert.notEqual(formatSyncedAt(new Date('2026-10-11T15:45:00')), '')
})

test('OneDrive Test connection shows connected, Graph errors, and the sign-in prompts', () => {
  const connected = renderToStaticMarkup(React.createElement(SyncSettings, {
    status: { provider: 'onedrive', account: 'OneDrive' },
    deviceName: 'Home PC',
    connectionText: CONNECTED_APP_FOLDER,
  }))
  assert.match(connected, /data-testid="sync-test-connection"/)
  assert.match(connected, /data-testid="sync-connection"/)
  assert.match(connected, /Connected to OneDrive App Folder/)

  const graphError = 'OneDrive Graph 401 InvalidAuthenticationToken: IDX14100: JWT is not well formed, there are no dots (.).'
  const failed = renderToStaticMarkup(React.createElement(SyncSettings, {
    status: { provider: 'onedrive', account: '' },
    deviceName: 'Home PC',
    connectionText: graphError,
  }))
  assert.match(failed, /data-testid="sync-connection"/)
  assert.match(failed, /401/)
  assert.match(failed, /InvalidAuthenticationToken/)
  assert.match(failed, /IDX14100/)

  const testing = renderToStaticMarkup(React.createElement(SyncSettings, {
    status: { provider: 'onedrive', account: 'OneDrive' },
    deviceName: 'Home PC',
    testingConnection: true,
  }))
  assert.match(testing, /Testing…/)

  const signedOut = renderToStaticMarkup(React.createElement(SyncSettings, {
    status: { provider: 'onedrive', account: '', error: SIGN_IN_TEXT },
    deviceName: 'Home PC',
  }))
  assert.match(signedOut, new RegExp(SIGN_IN_TEXT))
  assert.equal(signedOut.includes('expired'), false)

  const update = renderToStaticMarkup(React.createElement(SyncSettings, {
    status: { provider: 'onedrive', account: 'OneDrive', reauth: true, error: UPDATE_SIGN_IN_TEXT },
    deviceName: 'Home PC',
  }))
  assert.match(update, /data-testid="sync-sign-in"/)
  assert.match(update, /Sign in to OneDrive again to finish the update/)
  assert.equal(connectionResultText({ ok: true, message: CONNECTED_APP_FOLDER }), CONNECTED_APP_FOLDER)
  assert.equal(
    connectionResultText({ ok: false, message: graphError }),
    graphError,
  )
})

test('workspace snapshot is per character and a projection can add a pin', () => {
  const snapshot = snapshotFromWorkspace({
    wishByCharacter: { Zasariz: ['Mask of Song'], Other: ['Cloak of Flames'] },
    upgradeProgressByCharacter: { Zasariz: { 'Cloak of Flames': 8 } },
    importMeta: { source: 'Zasariz_qeynos-Inventory.txt', section_events: [{ id: 's1' }] },
  })
  assert.deepEqual(snapshot.characters.Zasariz.wishes, [{ name: 'Mask of Song' }])
  assert.deepEqual(snapshot.characters.Other.wishes, [{ name: 'Cloak of Flames' }])
  assert.equal(snapshot.characters.Zasariz.settings.upgrade_progress['Cloak of Flames'], 8)
  assert.deepEqual(snapshot.characters.Zasariz.inventory_events, [{ id: 's1' }])
  assert.equal(snapshot.characters.Other.inventory_events, undefined)
  const local = {
    wishByCharacter: { Zasariz: ['Mask of Song'] },
    inventoryCharacter: 'Zasariz',
    importMeta: null,
  }
  const merged = mergeProjection(local, {
    characters: {
      Zasariz: { wishes: ['Mask of Song', 'Cloak of Flames'], settings: {}, section_events: [] },
    },
  })
  assert.deepEqual(merged.wishByCharacter.Zasariz, ['Mask of Song', 'Cloak of Flames'])
})
