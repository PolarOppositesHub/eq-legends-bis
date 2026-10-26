import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import OverlayApp from './OverlayApp.jsx'
import { formatAlertRates, formatPerSecond } from './parserView.js'
import { parserStreamPath } from './parserApi.js'
import {
  OVERLAY_CHOICES,
  alertSoundRoute,
  closeAllIds,
  dismissAlertContent,
  meterPollDelay,
  meterRows,
  overlayChromeStyle,
  overlayCloseControl,
  overlayIdFromSearch,
} from './overlayView.js'

test('zone meter rows sum damage and heals and leave DPS off', () => {
  const rows = meterRows({
    scope: 'zone',
    rows: [{ source: 'Zasariz', damage: 10, heals: 4, dps: 99 }],
  })
  assert.equal(rows[0].damage, 10)
  assert.equal(rows[0].heals, 4)
  assert.equal('dps' in rows[0], false)
})

test('fight meter rows keep the stored DPS', () => {
  const rows = meterRows({
    scope: 'fight',
    rows: [{ source: 'Zasariz', damage: 80, heals: 0, dps: 8, sdps: 2.7, hps: 1.25 }],
  })
  assert.equal(rows[0].dps, 8)
  assert.equal(rows[0].sdps, 2.7)
  assert.equal(rows[0].hps, 1.25)
})

test('DPS and HPS display one decimal and sorting stays on the raw rate', () => {
  assert.equal(formatPerSecond(212.3453433), '212.3')
  assert.equal(formatPerSecond(1.25), '1.3')
  const rows = [
    { source: 'A', dps: 212.3453433, hps: 10.04 },
    { source: 'B', dps: 212.31, hps: 99.96 },
  ]
  const sorted = [...rows].sort((a, b) => b.dps - a.dps || b.hps - a.hps)
  assert.equal(sorted[0].source, 'A')
  assert.equal(sorted[0].dps, 212.3453433)
  assert.equal(formatPerSecond(sorted[0].dps), '212.3')
  assert.equal(formatPerSecond(sorted[1].dps), '212.3')
  assert.equal(formatPerSecond(sorted[1].hps), '100.0')
  assert.equal(formatAlertRates('spike 212.3453433 DPS then 10.04 HPS'), 'spike 212.3 DPS then 10.0 HPS')
  const kept = meterRows({
    scope: 'fight',
    rows: [{ source: 'A', damage: 1, heals: 2, dps: 212.3453433, hps: 10.04 }],
  })
  assert.equal(kept[0].dps, 212.3453433)
  assert.equal(kept[0].hps, 10.04)
  const chrome = overlayChromeStyle({ backgroundOpacity: 0.2, textOpacity: 1, backgroundColor: '#0a0a0a' })
  assert.equal(chrome.backgroundColor, 'rgba(10, 10, 10, 0.2)')
  assert.equal(chrome.color, 'rgba(245, 240, 230, 1)')
})

test('alert sounds play from a hidden window and a banner dismiss leaves the window up', () => {
  const speech = alertSoundRoute({ sound: 'speech', message: 'You died.' })
  assert.equal(speech.host, 'hidden-window')
  assert.equal(speech.visibleOverlay, false)
  assert.equal(speech.injection, false)
  assert.equal(speech.speak, true)
  const file = alertSoundRoute({ sound: 'file', sound_file: 'horn.wav' })
  assert.equal(file.file, 'horn.wav')
  assert.equal(file.speak, false)
  const dismissed = dismissAlertContent()
  assert.equal(dismissed.hideWindow, false)
  assert.equal(dismissed.closeWindow, false)
  assert.equal(dismissed.contentVisible, false)
})

test('the unlocked drag bar closes with an X and Close all targets open meters', () => {
  const unlocked = overlayCloseControl(false)
  assert.equal(unlocked.visible, true)
  assert.equal(unlocked.noDrag, true)
  assert.equal(unlocked.label, 'Close overlay')
  assert.equal(unlocked.text, '×')
  assert.equal(overlayCloseControl(true).visible, false)
  const html = renderToStaticMarkup(React.createElement(OverlayApp))
  assert.match(html, /aria-label="Close overlay"/)
  assert.match(html, /overlay-no-drag/)
  assert.match(html, /data-testid="overlay-close"/)
  assert.equal(html.includes('>Close<'), false)
  const ids = closeAllIds({
    dps: { open: true },
    heal: { open: false },
    alert: { open: true },
  }, OVERLAY_CHOICES)
  assert.deepEqual(ids, ['dps', 'alert'])
})

test('overlay route ids include the meters and the tracking cards', () => {
  assert.equal(overlayIdFromSearch('?overlay=dps'), 'dps')
  assert.equal(overlayIdFromSearch('?overlay=heal'), 'heal')
  assert.equal(overlayIdFromSearch('?overlay=alert'), 'alert')
  assert.equal(overlayIdFromSearch('?overlay=xp'), 'xp')
  assert.equal(overlayIdFromSearch('?overlay=con'), 'con')
  assert.equal(overlayIdFromSearch('?overlay=buffs'), 'buffs')
  assert.equal(overlayIdFromSearch('?overlay=nope'), '')
})

test('meter polls back off when the parser is busy and overlays can listen for alerts only', () => {
  assert.equal(meterPollDelay(2000, false), 2000)
  assert.equal(meterPollDelay(2000, true), 4000)
  assert.equal(meterPollDelay(4000, true), 8000)
  assert.equal(meterPollDelay(8000, true), 8000)
  assert.equal(parserStreamPath(undefined), '/api/parser/stream')
  assert.equal(parserStreamPath(['alert']), '/api/parser/stream?events=alert')
  assert.equal(parserStreamPath(['progress', 'upgrade']), '/api/parser/stream?events=progress%2Cupgrade')
})
