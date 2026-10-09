import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { RequirementsPanel, WishListPanel } from './requirementsView.jsx'
import { copiesFromImport, formatMoteList, isWished, toggleWish } from './requirementsView.js'

test('mote lists and wish pins are per character', () => {
  assert.equal(formatMoteList([]), 'none')
  assert.equal(
    formatMoteList([{ name: 'Mote of Potential', count: 2 }]),
    'Mote of Potential × 2',
  )
  const first = toggleWish({}, 'Zasariz', 'Mask of Song')
  const again = toggleWish(first, 'Zasariz', 'Mask of Song')
  assert.equal(isWished(first, 'Zasariz', 'Mask of Song'), true)
  assert.equal(isWished(again, 'Zasariz', 'Mask of Song'), false)
  assert.equal(isWished(first, 'Other', 'Mask of Song'), false)
  const copies = copiesFromImport({
    rows: [
      { name: 'Cloak of Flames', name_raw: 'Cloak of Flames +5', tier: 5, count: 1, depth: 0 },
      { name: 'Empty', depth: 1 },
    ],
    keyring: [{ name: 'Wind Rune Azia', count: 2 }],
  })
  assert.equal(copies[0].tier, 5)
  assert.equal(copies[1].name, 'Wind Rune Azia')
})

test('requirements pane shows the path and granted classes stay labeled', () => {
  const html = renderToStaticMarkup(React.createElement(RequirementsPanel, {
    pane: 'upgrades',
    onPane() {},
    onProgress() {},
    onTier() {},
    sortByScore: false,
    onSortByScore() {},
    plan: {
      holdings_note: 'Held motes and Void-Touched Potential are the Currencies totals (bags + storage).',
      rules: 'Void-Touched Potential is reserved for the highest remaining tier gap',
      damage_note: 'eqlwiki says weapon damage grows 5% per tier',
      totals: {
        xp_needed: 15,
        motes: [{ name: 'Mote of Potential', count: 2 }],
        missing: [],
        void_touched_used: 0,
        void_touched_held: 1,
      },
      items: [{
        id: 'BACK',
        slot: 'BACK',
        name: 'Cloak of Flames',
        owned: true,
        start_tier: 0,
        target_tier: 4,
        xp_needed: 15,
        progress: 0,
        path_ready: true,
        tier_source: 'inventory',
        motes: [{ name: 'Mote of Potential', count: 2 }],
        held_motes: [],
        missing: [{ name: 'Mote of Potential', count: 2, hint: 'Farm Mote of Potential × 2.' }],
        void_touched_planned: [],
        progress_note: 'Intra-tier progress is not in the inventory export. It is 0 until you set it.',
      }],
    },
  }))
  assert.match(html, /data-testid="requirements-panel"/)
  assert.match(html, /15 XP/)
  assert.match(html, /Mote of Potential × 2/)
  assert.match(html, /highest remaining tier gap/)
  assert.match(html, /5% per tier/)
  assert.match(html, /not in the inventory export/)

  const pos = renderToStaticMarkup(React.createElement(RequirementsPanel, {
    pane: 'pos',
    onPane() {},
    onProgress() {},
    onTier() {},
    plan: null,
    pos: {
      attribution: 'https://eqlwiki.com/Plane_of_Sky',
      granted_note: 'Whether a Primary Class Unlock Token is what completes the bypass line is UNVERIFIED.',
      locked_note: 'A status letter other than I or C is UNVERIFIED',
      classes: [{
        class: 'Bard', done: 1, remaining: 5, granted: false, goal: true, token_unverified: false,
      }, {
        class: 'Shadowknight', done: 0, remaining: 7, granted: true, goal: false, token_unverified: true,
        granted_reason: 'bypass',
      }],
      tests: [{
        class: 'Bard',
        quest: 'Bard Test of Tone',
        done: true,
        source: 'achievement',
        ignored: false,
        runes: [{ name: 'Wind Rune Meda', have: 1, need: 1, met: true }],
        items: [{ name: 'Light Woolen Mask', have: 0, need: 1, met: false }],
        linked_bis: [],
      }],
      unmatched_achievements: [{
        text: 'Obtain Windhowl and Spirit Render',
        reason: 'This Obtain line does not match a Plane of Sky reward name.',
      }],
    },
  }))
  assert.match(pos, /Bard Test of Tone/)
  assert.match(pos, /Wind Rune Meda 1\/1/)
  assert.match(pos, /token UNVERIFIED/)
  assert.match(pos, /does not match a Plane of Sky reward name/)
})

test('wish list shows owned status and the mote path', () => {
  const html = renderToStaticMarkup(React.createElement(WishListPanel, {
    names: ['Mask of Song'],
    ownedNames: [],
    onUnpin() {},
    plan: {
      items: [{
        name: 'Mask of Song',
        target_tier: 10,
        xp_needed: 1023,
        motes: [{ name: 'Mote of Infinite Potential', count: 1 }],
        missing: [],
        tier_note: 'You do not hold this item. The path is the cost from +0 once you have it.',
      }],
    },
  }))
  assert.match(html, /data-testid="wish-list-panel"/)
  assert.match(html, /not owned/)
  assert.match(html, /1023 XP/)
  assert.match(html, /from \+0/)
})
