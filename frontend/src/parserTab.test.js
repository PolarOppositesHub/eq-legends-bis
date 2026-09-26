import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { ParserPanel } from './ParserTab.jsx'
import { CreditsDialog, WhatsNewDialog } from './parserChrome.jsx'
import {
  LEVEL_LOADOUT_NOTE,
  PARSER_EMPTY,
  PET_LEADER_HINT,
  RAID_SCOPE_NOTE,
  WHATS_NEW_TITLE,
  describeLevelChange,
  formatZone,
  sourcesForScope,
  visibleDamage,
  visibleRate,
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
  assert.match(html, /Clearing fights keeps pet assignments, dismissals, and the group allowlist/)
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

test('scope filter, pet prompt, and group allowlist render on the Parser tab', () => {
  const html = markup(panel({
    logs: [{ path: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt', name: 'eqlog_Zasariz_qeynos.txt', character: 'Zasariz', server: 'qeynos' }],
    logsStatus: 'ready',
    selectedPath: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt',
    fights: [sampleFight],
    selectedFightId: 7,
    detailStatus: 'ready',
    scope: 'group',
    character: 'Zasariz',
    candidates: [{ pet: 'Jaber', evidence: 'nominate', status: 'open' }],
    groupMembers: [{ name: 'Amop', via: 'log' }],
    allowlist: ['Cara'],
    loadouts: [
      { name: 'Zasariz', classes: 'PAL/DRU/WIZ', level: 36 },
      { name: 'Zasariz', classes: 'WAR/SHD/PAL', level: 12 },
    ],
    detail: {
      id: 7,
      duration_seconds: 30,
      totals: { damage: 100, dps: 3.3 },
      sources: [
        { source: 'Zasariz', kind: 'self', damage: 80, dps: 8, sdps: 2.7, pets: [] },
        { source: 'Amop', kind: 'group', damage: 20, dps: 2, sdps: 0.7, pets: [] },
      ],
    },
  }))
  assert.match(html, /data-testid="parser-scope"/)
  assert.match(html, /data-testid="parser-scope-self"/)
  assert.match(html, /data-testid="parser-scope-group"/)
  assert.match(html, /data-testid="parser-scope-pets"/)
  assert.match(html, /data-testid="parser-scope-raid"/)
  assert.match(html, /data-testid="parser-scope-all"/)
  assert.match(html, /data-testid="parser-scope-group"[^>]*aria-pressed="true"|aria-pressed="true"[^>]*data-testid="parser-scope-group"/)
  assert.match(html, /data-testid="parser-pet-prompt"/)
  assert.match(html, /Jaber — your pet\?/)
  assert.match(html, /Set as pet of…/)
  assert.match(html, /Unassign/)
  assert.match(html, /data-testid="parser-group"/)
  assert.match(html, /From the log: Amop/)
  assert.match(html, /data-testid="parser-allow-list"/)
  assert.match(html, />Cara</)
  assert.match(html, /PAL\/DRU\/WIZ · 36/)
  assert.match(html, /WAR\/SHD\/PAL · 12/)
  assert.equal(html.includes(PET_LEADER_HINT), true)
  assert.equal(html.includes(RAID_SCOPE_NOTE), false)
  assert.match(html, /Total damage 100/)
  assert.match(html, /3\.3 DPS/)

  const raid = markup(panel({
    logs: [{ path: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt', name: 'eqlog_Zasariz_qeynos.txt', character: 'Zasariz', server: 'qeynos' }],
    logsStatus: 'ready',
    selectedPath: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt',
    fights: [sampleFight],
    scope: 'raid',
  }))
  assert.match(raid, /data-testid="parser-raid-note"/)
  assert.equal(raid.includes(RAID_SCOPE_NOTE), true)
})

test('pets scope with merge pets totals the pet rows on screen', () => {
  const detail = {
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
        pets: [{ source: 'a warder', kind: 'pet', owner: 'Zasariz', damage: 20, dps: 2, sdps: 0.7 }],
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
  const html = markup(panel({
    logs: [{ path: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt', name: 'eqlog_Zasariz_qeynos.txt', character: 'Zasariz', server: 'qeynos' }],
    logsStatus: 'ready',
    selectedPath: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt',
    fights: [sampleFight],
    selectedFightId: 7,
    detailStatus: 'ready',
    scope: 'pets',
    mergePets: true,
    detail,
  }))
  assert.match(html, /data-testid="parser-scope-pets"/)
  assert.match(html, /data-source="a warder" data-nested="1"/)
  assert.equal(html.includes('data-source="Zasariz"'), false)
  assert.match(html, /Total damage 20/)
  assert.equal(visibleDamage(sourcesForScope(detail, 'pets')), 20)
  assert.equal(visibleDamage(sourcesForScope(detail, 'group')), 140)
  assert.equal(visibleRate(sourcesForScope(detail, 'pets'), 30), 20 / 30)
})

test("what's new dialog shows the 1.1.1 notes", () => {
  const html = markup(React.createElement(WhatsNewDialog, { onClose: noop }))
  assert.match(html, /data-testid="whats-new-dialog"/)
  assert.equal(WHATS_NEW_TITLE, "What's new in 1.1.1")
  assert.match(html, /<h2>What&#x27;s new in 1\.1\.1<\/h2>/)
  assert.match(html, /Woven Skull Cap shows Wizard Test of Focus/)
  assert.match(html, /rebuilds the existing 1\.1\.0 parse from the log/)
  assert.match(html, /dragon-eye seal/)
  assert.equal(/<h2>What&#x27;s new in 1\.1\.0<\/h2>/.test(html), false)
})

test('scope filter keeps a candidate out of group and raid players who hit the same NPC', () => {
  const detail = {
    sources: [
      { source: 'Zasariz', kind: 'self', damage: 10, pets: [] },
      { source: 'Amop', kind: 'group', damage: 4, pets: [] },
      { source: 'Jenann', kind: 'pet', owner: 'Zasariz', damage: 3, pets: [] },
      { source: 'Jaber', kind: 'candidate', damage: 40, pets: [] },
      { source: 'Brinn', kind: 'other', damage: 8, pets: [] },
      { source: 'a rat', kind: 'npc', damage: 6, pets: [] },
    ],
  }
  const names = (scope) => sourcesForScope(detail, scope, ['Cara']).map((row) => row.source)
  assert.deepEqual(names('self'), ['Zasariz'])
  assert.deepEqual(names('group'), ['Zasariz', 'Amop', 'Jenann'])
  assert.deepEqual(names('pets'), ['Jenann'])
  assert.deepEqual(names('raid'), ['Zasariz', 'Amop', 'Jenann', 'Brinn'])
  assert.deepEqual(names('all'), ['Zasariz', 'Amop', 'Jenann', 'Jaber', 'Brinn', 'a rat'])
  assert.equal(names('group').includes('Jaber'), false)
  assert.equal(visibleRate(sourcesForScope(detail, 'group', ['Cara']), 2), 8.5)
  assert.equal(visibleRate(sourcesForScope(detail, 'all', ['Cara']), 2), 35.5)
})

test('parser depth shows one page of fights, detail tabs, and copy actions', () => {
  const fights = Array.from({ length: 80 }, (_, i) => ({
    id: i + 1,
    start_ts: '2026-08-04T22:00:01',
    zone: 'Befallen',
    targets: ['a rat'],
    duration_seconds: 12,
    damage: 10,
    your_dps: 2,
  }))
  const html = markup(panel({
    logs: [{ path: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt', name: 'eqlog_Zasariz_qeynos.txt', character: 'Zasariz', server: 'qeynos' }],
    logsStatus: 'ready',
    selectedPath: 'C:\\EQ\\Logs\\eqlog_Zasariz_qeynos.txt',
    fights,
    selectedFightId: 1,
    detailStatus: 'ready',
    character: 'Zasariz',
    detail: {
      id: 1,
      duration_seconds: 12,
      targets: ['a rat'],
      zone: 'Befallen',
      sources: [{
        source: 'Zasariz',
        kind: 'self',
        damage: 10,
        dps: 2,
        sdps: 1,
        hits: 2,
        crits: 1,
        max_hit: 8,
        pets: [],
        abilities: [
          { source: 'Zasariz', category: 'melee', ability: 'slash', damage: 10, hits: 2, crits: 1, misses: 0, max_hit: 8 },
        ],
      }],
      healing: { rows: [] },
      multi_attack: { estimate: true, note: 'Estimate from swings that share a timestamp second.', sources: [] },
      procs: { count: 0, per_minute: 0, items: [] },
    },
  }))
  assert.equal((html.match(/data-fight-id=/g) || []).length, 40)
  assert.match(html, /of 80/)
  assert.match(html, /data-testid="parser-merge-fights"/)
  assert.match(html, /data-testid="parser-set-mark"/)
  assert.match(html, /data-testid="parser-tab-healing"/)
  assert.match(html, /data-testid="parser-tab-timeline"/)
  assert.match(html, /data-testid="parser-tab-loot"/)
  assert.match(html, /data-testid="parser-copy-text"/)
  assert.match(html, /data-testid="parser-expand"/)
  assert.match(html, /data-source="Zasariz"/)
  assert.equal(html.includes('data-testid="parser-abilities"'), false)
})

test('credits name eqlwiki CC BY-SA and eqlegendstools.com', () => {
  const html = markup(React.createElement(CreditsDialog, { onClose: noop }))
  assert.match(html, /data-testid="credits-dialog"/)
  assert.match(html, /eqlwiki\.com/)
  assert.match(html, /CC BY-SA 4\.0/)
  assert.match(html, /eqlegendstools\.com/)
  assert.match(html, /creativecommons\.org\/licenses\/by-sa\/4\.0/)
})
