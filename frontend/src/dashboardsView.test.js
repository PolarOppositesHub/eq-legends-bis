import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { HomeOverview, LevelingPanel } from './dashboardsView.jsx'
import {
  MULTI_CLASS_CAVEAT,
  dropRateLabel,
  formatLevelsPerHour,
  homeDpsText,
  homeFightStatus,
  homeLoadout,
  homeMobLine,
  toastsFromStream,
} from './dashboardsView.js'

test('drop rate is loots over kills and stays unknown without a kill', () => {
  assert.equal(dropRateLabel(2, 4).rate, 0.5)
  assert.equal(dropRateLabel(2, 4).text, '2 / 4')
  assert.equal(dropRateLabel(3, 0).text, 'unknown')
  assert.equal(dropRateLabel(3, 0).rate, null)
})

test('toasts never come from a replay', () => {
  const level = { live: true, toast: { kind: 'level', level: 24, live: true } }
  assert.deepEqual(toastsFromStream(level, { live: false }), [])
  assert.deepEqual(toastsFromStream({ live: false, toast: level.toast }, { live: true }), [])
  assert.equal(toastsFromStream(level, { live: true })[0].level, 24)
  const loot = { live: true, toast: { kind: 'loot', item: 'A Shimmering Orb', reasons: ['bis'], live: true } }
  assert.equal(toastsFromStream(loot, { live: true })[0].item, 'A Shimmering Orb')
})

test('the home screen groups the overview and leaves missing numbers unknown', () => {
  assert.equal(homeLoadout({ classes: ['WIZ', 'ENC', 'MAG'], level: 50 }), 'WIZ / ENC / MAG · 50')
  assert.equal(homeLoadout({ classes: [], level: null }), 'classes unknown · level unknown')
  assert.equal(homeFightStatus({ status: 'fighting', names: ['a rat'] }), 'Fighting')
  assert.equal(homeFightStatus({ status: 'between fights' }), 'Between fights')
  assert.equal(homeFightStatus({ status: 'no fight yet' }), 'No fight yet')
  assert.equal(homeFightStatus({}), 'No fight open')
  assert.equal(homeMobLine({ status: 'fighting', names: ['a rat', ''] }), 'a rat')
  assert.equal(homeMobLine({ status: 'fighting', names: [] }), 'unknown')
  assert.equal(homeMobLine({ status: 'no fight yet' }), 'No fight yet')
  assert.equal(homeDpsText(212.3453433), '212.3 DPS')
  assert.equal(homeDpsText(null), 'unknown')
  const html = renderToStaticMarkup(React.createElement(HomeOverview, {
    character: 'Zasariz',
    body: {
      caveat: MULTI_CLASS_CAVEAT,
      current_mob: { status: 'fighting', names: ['a rat'], zone: 'Befallen', last_targets: ['a bat'] },
      dps: { your_dps: 12.34, targets: ['a rat'], curve: { available: false, reason: 'No DPS curve is stored for this fight.' } },
      leveling: { classes: ['WIZ'], level: 20, levels_per_hour: null, hours_to_level: null },
      recent_loots: [{ item: 'Cloth Cap', from: 'a rat' }],
      recent_kills: [{ mob: 'a rat' }],
      zones: [{ zone: 'Befallen', ts: '2026-10-30T00:00:00' }],
    },
  }))
  assert.match(html, /data-testid="home-character"/)
  assert.match(html, /Zasariz/)
  assert.match(html, /data-testid="home-loadout"/)
  assert.match(html, /WIZ · 20/)
  assert.match(html, /data-testid="home-status">Fighting</)
  assert.match(html, /Right now/)
  assert.match(html, /Recent/)
  assert.match(html, /data-testid="home-jumps"/)
  assert.match(html, /Item Search/)
  assert.match(html, /Cloth Cap from a rat/)
  assert.match(html, /unknown/)
  assert.match(html, /Press \? for keyboard shortcuts/)
  const empty = renderToStaticMarkup(React.createElement(HomeOverview, { character: 'Zasariz' }))
  assert.equal(empty.includes('data-testid="card-dps"'), false)
  assert.equal(empty.includes('0 DPS'), false)
  assert.equal(empty.includes('classes unknown'), false)
  assert.equal(empty.includes('No fight open'), false)
  assert.match(empty, /Press \? for keyboard shortcuts/)
})

test('leveling shows the multi-class caveat and levels of progress', () => {
  assert.match(formatLevelsPerHour(0.3), /levels of progress/)
  assert.equal(formatLevelsPerHour(null), 'unknown')
  const html = renderToStaticMarkup(React.createElement(LevelingPanel, {
    payload: {
      caveat: MULTI_CLASS_CAVEAT,
      levels_per_hour: 0.3,
      hours_to_level: 0.7 / 0.3,
      progress_pct: 30,
      bar_known: true,
      aa_per_hour: 2,
      aa_total: 11,
      history: [
        { classes: 'WIZ/ENC/MAG', start_level: 50, end_level: 50 },
        { classes: 'CLR/DRU/SHM', start_level: 10, end_level: 10 },
      ],
      new_at_level: [{ name: 'Resolution', class: 'Cleric', level: 42 }],
      zone_band: { zone: 'Befallen', status: 'unknown', note: 'No sourced level band for this zone is in the app data.' },
    },
  }))
  assert.match(html, /data-testid="leveling-caveat"/)
  assert.match(html, /50 then 10/)
  assert.match(html, /0\.30 levels of progress/)
  assert.match(html, /Resolution/)
  assert.match(html, /unknown/)
})
