import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { LevelingPanel } from './dashboardsView.jsx'
import {
  MULTI_CLASS_CAVEAT,
  dropRateLabel,
  formatLevelsPerHour,
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
