import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { ParserPanel } from './ParserTab.jsx'
import { CreditsDialog } from './parserChrome.jsx'
import {
  LEVEL_LOADOUT_NOTE,
  PARSER_EMPTY,
  describeLevelChange,
  formatZone,
} from './parserView.js'

function markup(element) {
  return renderToStaticMarkup(element)
}

const noop = () => {}

function panel(extra) {
  return React.createElement(ParserPanel, {
    folder: 'C:\\Users\\Public\\Daybreak Game Company\\Installed Games\\EverQuest Legends',
    logs: [],
    logsStatus: 'ready',
    selectedPath: '',
    onSelectLog: noop,
    live: false,
    onToggleLive: noop,
    loadingLog: false,
    fights: [],
    selectedFightId: null,
    onSelectFight: noop,
    detail: null,
    detailStatus: 'idle',
    mergePets: true,
    onMergePetsChange: noop,
    onLoadLog: noop,
    onRefresh: noop,
    onSetEqFolder: noop,
    canSetFolder: true,
    onOpenCredits: noop,
    ...extra,
  })
}

const sampleFight = {
  id: 7,
  start_ts: '2026-08-04T22:00:01',
  zone: 'Befallen',
  instance: { scope: 'Group', number: 2, tier: 'Awakened' },
  targets: ['a Teir`Dal priest', 'a Teir`Dal priestess'],
  duration_seconds: 95,
  damage: 853,
  open: false,
  player_died: false,
}

test('empty state tells you to turn logging on and check the folder and chat filters', () => {
  const html = markup(panel())
  assert.match(html, /data-testid="parser-empty"/)
  assert.match(html, /No combat logs found/)
  assert.equal(html.includes('/log on'), true)
  assert.equal(html.includes('EQ install folder'), true)
  assert.match(html, /chat filter/i)
  assert.equal(html.includes('parser-fights'), false)
  assert.equal(html.includes(PARSER_EMPTY.logOn), true)
  assert.match(html, /EverQuest Legends/)
})

test('fight list renders time, zone, targets, duration, and total damage', () => {
  const html = markup(panel({
    logs: [{ path: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt', name: 'eqlog_Zasariz_qeynos.txt', character: 'Zasariz', server: 'qeynos' }],
    logsStatus: 'ready',
    selectedPath: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt',
    fights: [sampleFight, {
      id: 8,
      start_ts: 'not-a-timestamp',
      zone: '',
      targets: [],
      duration_seconds: 12,
      damage: 0,
    }],
  }))
  assert.match(html, /data-testid="parser-fights"/)
  assert.match(html, /Aug 4, 2026 22:00:01/)
  assert.match(html, /Befallen · Group · 2 · Awakened/)
  assert.match(html, /a Teir`Dal priest, a Teir`Dal priestess/)
  assert.match(html, />1:35</)
  assert.match(html, />853</)
  assert.match(html, />unknown</)
  assert.equal(formatZone({ zone: '' }), 'unknown')
  assert.equal(html.includes('data-testid="parser-empty"'), false)
})

test('merge-pets toggle nests pets when on and lists them separately when off', () => {
  const merged = {
    id: 7,
    duration_seconds: 30,
    totals: { damage: 140, dps: 4.6 },
    sources: [
      {
        source: 'Zasariz',
        kind: 'self',
        damage: 100,
        dps: 10,
        sdps: 3.3,
        pets: [{ source: 'a warder', kind: 'pet', damage: 20, dps: 2, sdps: 0.7 }],
      },
      {
        source: 'Amop',
        kind: 'group',
        damage: 40,
        dps: 4,
        sdps: 1.3,
        pets: [],
      },
    ],
  }
  const split = {
    id: 7,
    duration_seconds: 30,
    totals: { damage: 140, dps: 4.6 },
    sources: [
      { source: 'Zasariz', kind: 'self', damage: 80, dps: 8, sdps: 2.7, pets: [] },
      { source: 'a warder', kind: 'pet', damage: 20, dps: 2, sdps: 0.7, pets: [] },
      { source: 'Amop', kind: 'group', damage: 40, dps: 4, sdps: 1.3, pets: [] },
    ],
  }
  const base = {
    logs: [{ path: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt', name: 'eqlog_Zasariz_qeynos.txt', character: 'Zasariz', server: 'qeynos' }],
    logsStatus: 'ready',
    selectedPath: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt',
    fights: [sampleFight],
    selectedFightId: 7,
    detailStatus: 'ready',
  }
  const onHtml = markup(panel({ ...base, mergePets: true, detail: merged }))
  const offHtml = markup(panel({ ...base, mergePets: false, detail: split }))

  assert.match(onHtml, /data-testid="parser-merge-pets"/)
  assert.match(onHtml, /Merge pets/)
  assert.match(onHtml, /<input[^>]*checked=""[^>]*>/)
  assert.match(onHtml, /data-source="a warder" data-nested="1"/)
  assert.match(onHtml, /data-source="Zasariz" data-nested="0"/)
  assert.match(onHtml, /data-source="Amop" data-nested="0"/)
  assert.match(onHtml, /↳ a warder/)

  assert.equal(/<input[^>]*checked=""/.test(offHtml), false)
  assert.match(offHtml, /data-source="a warder" data-nested="0"/)
  assert.equal(offHtml.includes('data-nested="1"'), false)
  assert.match(offHtml, />Pet</)
  assert.match(offHtml, />You</)
  assert.match(offHtml, />Group</)
})

test('fight history shows retention, defaulting to keep everything, and a per-character clear', () => {
  const html = markup(panel({
    logs: [{
      path: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt',
      name: 'eqlog_Zasariz_qeynos.txt',
      character: 'Zasariz',
      server: 'qeynos',
    }],
    logsStatus: 'ready',
    selectedPath: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt',
    character: 'Zasariz',
    retentionDays: 0,
  }))
  assert.match(html, /data-testid="parser-history"/)
  assert.match(html, /data-testid="parser-retention"/)
  assert.match(html, /value="0"/)
  assert.match(html, /0 keeps every saved fight/)
  assert.match(html, /data-testid="parser-clear-history"/)
  assert.match(html, /Clear this character/)
  assert.equal(/data-testid="parser-clear-history"[^>]*disabled/.test(html), false)
  const idle = markup(panel())
  assert.match(idle, /data-testid="parser-clear-history"[^>]*disabled/)
})

test('an in-progress parser upgrade shows a short updating state', () => {
  const html = markup(panel({ upgrading: true }))
  assert.match(html, /data-testid="parser-upgrade"/)
  assert.equal(html.includes('Updating parser data…'), true)
  const idle = markup(panel())
  assert.equal(idle.includes('data-testid="parser-upgrade"'), false)
})

test('load progress bar shows line count and percent', () => {
  const html = markup(panel({
    logs: [{
      path: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt',
      name: 'eqlog_Zasariz_qeynos.txt',
      character: 'Zasariz',
      server: 'qeynos',
    }],
    logsStatus: 'ready',
    selectedPath: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt',
    loadingLog: true,
    progress: { active: true, done: false, pct: 40, lines: 50000 },
  }))
  assert.match(html, /data-testid="parser-progress"/)
  assert.match(html, /aria-valuenow="40"/)
  assert.match(html, /50,000 lines/)
  assert.match(html, /40%/)
})

test('a level drop is kept and is not an error', () => {
  const drop = describeLevelChange(50, 29)
  assert.equal(drop.error, false)
  assert.equal(/\berror\b/i.test(drop.text), false)
  assert.match(drop.text, /50/)
  assert.match(drop.text, /29/)
  const html = markup(panel())
  assert.match(html, /data-testid="parser-level-note"/)
  assert.equal(html.includes(LEVEL_LOADOUT_NOTE), true)
  assert.equal(/\berror\b/i.test(LEVEL_LOADOUT_NOTE), false)
  const note = html.slice(html.indexOf('parser-level-note'))
  assert.equal(note.includes('warn-box'), false)
})

test('credits name eqlwiki CC BY-SA and eqlegendstools.com', () => {
  const html = markup(React.createElement(CreditsDialog, { onClose: noop }))
  assert.match(html, /data-testid="credits-dialog"/)
  assert.match(html, /eqlwiki\.com/)
  assert.match(html, /CC BY-SA 4\.0/)
  assert.match(html, /eqlegendstools\.com/)
  assert.match(html, /creativecommons\.org\/licenses\/by-sa\/4\.0/)
})
