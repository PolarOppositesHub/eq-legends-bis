import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  HealingPanel,
  SpellPage,
  TimelineChart,
} from './parserDepth.jsx'
import {
  FIGHT_PAGE_SIZE,
  capIds,
  chartValue,
  filterFights,
  formatParseCsv,
  formatParseHtml,
  formatParseText,
  formatParseTsv,
  mergeFightDetails,
  pageSlice,
  sliceFromMark,
  spellStats,
  zoneSession,
} from './parserDepth.js'

function detail(extra) {
  return {
    id: 1,
    character: 'Zasariz',
    zone: 'Befallen',
    start_ts: '2026-08-04T22:00:01',
    end_ts: '2026-08-04T22:00:21',
    duration_seconds: 20,
    targets: ['a goblin'],
    merge_pets: true,
    sources: [
      {
        source: 'Zasariz',
        kind: 'self',
        damage: 100,
        hits: 2,
        misses: 0,
        crits: 1,
        max_hit: 80,
        active_seconds: 10,
        melee: 100,
        spell: 0,
        dot: 0,
        ds: 0,
        heals: 0,
        heals_full: 0,
        overheal: 0,
        damage_taken: 0,
        pets: [],
        abilities: [
          { source: 'Zasariz', category: 'melee', ability: 'slash', damage: 100, hits: 2, crits: 1, misses: 0, max_hit: 80 },
        ],
      },
    ],
    abilities: [
      { source: 'Zasariz', category: 'melee', ability: 'slash', damage: 100, hits: 2, crits: 1, misses: 0, max_hit: 80 },
    ],
    healing: { rows: [], totals: {} },
    tanking: { incoming: [], avoidance: [], runes: [], self_damage: [] },
    deaths: [],
    resists: [],
    procs: { count: 0, per_minute: 0, items: [] },
    multi_attack: { estimate: true, note: 'Estimate from swings that share a timestamp second.', sources: [] },
    ...extra,
  }
}

test('merged fights sum damage and overheal once', () => {
  const a = detail()
  const b = detail({
    id: 2,
    zone: 'Befallen',
    start_ts: '2026-08-04T22:10:00',
    end_ts: '2026-08-04T22:10:10',
    duration_seconds: 10,
    sources: [
      {
        source: 'Zasariz',
        kind: 'self',
        damage: 40,
        hits: 1,
        misses: 1,
        crits: 0,
        max_hit: 40,
        active_seconds: 5,
        melee: 40,
        spell: 0,
        dot: 0,
        ds: 0,
        heals: 10,
        heals_full: 10,
        overheal: 0,
        damage_taken: 0,
        pets: [],
        abilities: [
          { source: 'Zasariz', category: 'melee', ability: 'slash', damage: 40, hits: 1, crits: 0, misses: 1, max_hit: 40 },
        ],
      },
    ],
    abilities: [
      { source: 'Zasariz', category: 'melee', ability: 'slash', damage: 40, hits: 1, crits: 0, misses: 1, max_hit: 40 },
    ],
    healing: {
      rows: [{ source: 'Amop', target: 'Zasariz', spell: 'Valor', over_time: false, actual: 204, full: 216, overheal: 12, hits: 1, crits: 1 }],
    },
  })
  const merged = mergeFightDetails([a, b])
  assert.equal(merged.merged_count, 2)
  assert.deepEqual(merged.merged_ids, [1, 2])
  assert.equal(merged.duration_seconds, 30)
  const you = merged.sources.find((row) => row.source === 'Zasariz')
  assert.equal(you.damage, 140)
  assert.equal(you.hits, 3)
  assert.equal(you.misses, 1)
  assert.equal(you.max_hit, 80)
  assert.equal(you.abilities.length, 1)
  assert.equal(you.abilities[0].damage, 140)
  assert.equal(you.abilities[0].hits, 3)
  assert.equal(merged.healing.rows[0].overheal, 12)
  assert.equal(merged.healing.totals.overheal, 12)
  const text = formatParseText(merged, [you])
  assert.match(text, /merged 2/)
  assert.match(text, /140 dmg/)
  assert.match(text, /slash/)
  assert.equal(/[^\x0a\x20-\x7e]/.test(text), false)
  assert.equal(/told you/i.test(text), false)
})

test('copy text, tsv, csv, and html stay plain data', () => {
  const one = detail()
  const sources = one.sources
  const tsv = formatParseTsv(one, sources)
  assert.match(tsv, /Source\tKind\tAbility/)
  assert.match(tsv, /slash/)
  const csv = formatParseCsv(one, [{ ...sources[0], source: 'Za,riz' }])
  assert.match(csv, /"Za,riz"/)
  const html = formatParseHtml(one, sources)
  assert.match(html, /<!DOCTYPE html>/)
  assert.match(html, /#d4af37/)
  assert.match(html, /does not send anything to EverQuest/)
  assert.equal(html.includes('<script'), false)
  const nasty = formatParseHtml(detail({ targets: ['<script>'] }), sources)
  assert.equal(nasty.includes('<script>'), false)
  assert.match(nasty, /&lt;script&gt;/)
})

test('a 204 (216) heal is 12 overheal on the spell page', () => {
  const row = {
    source: 'Amop',
    target: 'Zasariz',
    spell: 'Valor',
    over_time: false,
    actual: 204,
    full: 216,
    overheal: 12,
    hits: 1,
    crits: 1,
  }
  const stats = spellStats(row)
  assert.equal(stats.overheal, 12)
  assert.equal(stats.avg, 204)
  const html = renderToStaticMarkup(React.createElement(SpellPage, { row, onClose: () => {} }))
  assert.match(html, /data-testid="parser-spell-page"/)
  assert.match(html, /Valor/)
  assert.match(html, /data-testid="parser-spell-overheal"/)
  assert.match(html, />12</)
  assert.match(html, /Direct heal/)
})

test('history paging keeps a long fight list off one table', () => {
  const fights = Array.from({ length: 100 }, (_, i) => ({
    id: i + 1,
    zone: i % 2 ? 'Befallen' : 'Unrest',
    targets: ['a rat'],
    start_ts: `2026-08-04T22:${String(i % 60).padStart(2, '0')}:00`,
  }))
  const filtered = filterFights(fights, 'bef')
  assert.equal(filtered.length, 50)
  const page = pageSlice(fights, 3, FIGHT_PAGE_SIZE)
  assert.equal(page.pages, 3)
  assert.equal(page.rows.length, 20)
  assert.equal(page.rows[0].id, 81)
  assert.equal(capIds(fights.map((row) => row.id)).length, 40)
})

test('zone session and session mark follow the log times', () => {
  const fights = [
    { id: 1, zone: 'Unrest', start_ts: '2026-08-04T21:00:00' },
    { id: 2, zone: 'Befallen', start_ts: '2026-08-04T22:00:00' },
    { id: 3, zone: 'Befallen', start_ts: '2026-08-04T22:05:00' },
    { id: 4, zone: 'Guk', start_ts: '2026-08-04T23:00:00' },
  ]
  assert.deepEqual(zoneSession(fights, 3).map((row) => row.id), [2, 3])
  assert.deepEqual(sliceFromMark(fights, '2026-08-04T22:05:00').map((row) => row.id), [3, 4])
})

test('timeline series are damage per bin and healing rows render', () => {
  const point = chartValue({ t: 0, you: 140, pets: 50, group: 0, other: 0, incoming: 30, incoming_group: 0, heals: 0 }, 'group', 1)
  assert.equal(point.outgoing, 190)
  assert.equal(point.incoming, 30)
  const self = chartValue({ t: 0, you: 140, pets: 50, group: 10, other: 0, incoming: 30, incoming_group: 4, heals: 0 }, 'self', 1)
  assert.equal(self.outgoing, 140)
  assert.equal(self.incoming, 30)
  const html = renderToStaticMarkup(React.createElement(TimelineChart, {
    buckets: [{ t: 0, you: 140, pets: 0, group: 0, other: 0, incoming: 30, incoming_group: 0, heals: 0 }],
    binSeconds: 1,
    summary: 'Peak You 140.0 DPS at 0s.',
    series: [
      { id: 'outgoing', label: 'You', stroke: 'var(--gold)', value: (bucket) => bucket.you },
      { id: 'incoming', label: 'Incoming', stroke: 'var(--danger)', value: (bucket) => bucket.incoming },
    ],
  }))
  assert.match(html, /data-testid="parser-timeline-chart"/)
  assert.match(html, /data-series="outgoing"/)
  assert.match(html, /Peak You 140.0 DPS/)
  const heals = renderToStaticMarkup(React.createElement(HealingPanel, {
    healing: {
      rows: [{ source: 'Amop', target: 'Zasariz', spell: 'Valor', over_time: false, actual: 204, full: 216, overheal: 12, hits: 1, crits: 1 }],
    },
    names: new Set(['amop']),
  }))
  assert.match(heals, /data-testid="parser-healing"/)
  assert.match(heals, /Valor/)
  assert.match(heals, />12</)
})
