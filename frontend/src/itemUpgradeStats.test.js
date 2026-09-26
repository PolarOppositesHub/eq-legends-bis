import assert from 'node:assert/strict'
import test from 'node:test'

import {
  itemStatsAtLevel,
  previewStatsPlus10,
  scaleTooltipLines,
} from './itemUpgradeStats.js'

const CLOAK_LINES = [
  'Slot: BACK',
  'AC: 10',
  'DEX: +9 AGI: +9 HP: +50',
  'SV FIRE: +15',
  'Haste: +36%',
  'WT: 0.1 Size: MEDIUM',
  'Class: ALL',
  "Drops From: Nagafen's Lair: Lord Nagafen",
]

const CLOAK = {
  stats_plus0: { AC: 10, DEX: 9, AGI: 9, HP: 50, SVF: 15, Haste: 36 },
  // Decoded +10 haste is a copy of +0. Chips must not treat that as measured +10.
  stats_plus10: { AC: 20, DEX: 19, AGI: 19, HP: 100, SVF: 30, Haste: 36 },
}

const SASH_LINES = [
  'Slot: WAIST',
  'Haste: +21%',
  'WT: 0.1 Size: SMALL',
  'Class: ALL',
  'Drops From: Lower Guk: a frenzied ghoul',
]

test('Cloak of Flames tooltip and chips are 36 haste and AC 10 at +0', () => {
  const lines = scaleTooltipLines(CLOAK_LINES, 0)
  assert.deepEqual(lines, CLOAK_LINES)
  const stats = itemStatsAtLevel(CLOAK, 0)
  assert.equal(stats.Haste, 36)
  assert.equal(stats.AC, 10)
  assert.equal(stats.HP, 50)
})

test('Cloak of Flames tooltip and chips are 46 haste and AC 20 at +10', () => {
  const lines = scaleTooltipLines(CLOAK_LINES, 10)
  assert.equal(lines[0], 'Slot: BACK')
  assert.equal(lines[1], 'AC: 20')
  assert.equal(lines[2], 'DEX: +19 AGI: +19 HP: +100')
  assert.equal(lines[3], 'SV FIRE: +30')
  assert.equal(lines[4], 'Haste: +46%')
  assert.equal(lines[5], 'WT: 0.1 Size: MEDIUM')
  assert.equal(lines[6], 'Class: ALL')
  assert.equal(lines[7], "Drops From: Nagafen's Lair: Lord Nagafen")
  const stats = itemStatsAtLevel(CLOAK, 10)
  assert.equal(stats.Haste, 46)
  assert.equal(stats.AC, 20)
  assert.equal(stats.HP, 100)
  assert.equal(stats.DEX, 19)
  assert.equal(stats.SVF, 30)
})

test('Flowing Black Silk Sash haste is 21 at +0 and 31 at +10', () => {
  assert.equal(scaleTooltipLines(SASH_LINES, 0)[1], 'Haste: +21%')
  assert.equal(scaleTooltipLines(SASH_LINES, 10)[1], 'Haste: +31%')
  assert.equal(scaleTooltipLines(SASH_LINES, 10)[0], 'Slot: WAIST')
  assert.equal(scaleTooltipLines(SASH_LINES, 10)[3], 'Class: ALL')
  const item = { stats_plus0: { Haste: 21 }, stats_plus10: { Haste: 21 } }
  assert.equal(itemStatsAtLevel(item, 0).Haste, 21)
  assert.equal(itemStatsAtLevel(item, 10).Haste, 31)
})

test('delay, effects, focus, and backstab damage stay put while DMG and regen scale', () => {
  const lines = [
    'Skill: 2H Slashing Atk Delay: 42',
    'DMG: 20',
    'Effect: Haste (Combat, Casting Time: Instant) at Level 30',
    'Focus Effect: Improved Damage I',
    'Backstab DMG: 11',
    'Fire DMG: 4',
    'HP Regen: +10 Mana Regen: 2',
  ]
  const out = scaleTooltipLines(lines, 10)
  assert.equal(out[0], lines[0])
  assert.equal(out[1], 'DMG: 40')
  assert.equal(out[2], lines[2])
  assert.equal(out[3], lines[3])
  assert.equal(out[4], 'Backstab DMG: 11')
  assert.equal(out[5], 'Fire DMG: 4')
  assert.equal(out[6], 'HP Regen: +20 Mana Regen: 12')
  const stats = itemStatsAtLevel({ stats_plus0: { DMG: 20, DLY: 42, HP_REGEN: 10, MANA_REGEN: 2, FIRE_DMG: 4 } }, 10)
  assert.equal(stats.DMG, 40)
  assert.equal(stats.DLY, 42)
  assert.equal(stats.HP_REGEN, 20)
  assert.equal(stats.MANA_REGEN, 12)
  assert.equal(stats.FIRE_DMG, 4)
})

test('collapsed +10 preview adds the haste level when stored +10 haste copies +0', () => {
  const preview = previewStatsPlus10(CLOAK)
  assert.equal(preview.Haste, 46)
  assert.equal(preview.AC, 20)
})
