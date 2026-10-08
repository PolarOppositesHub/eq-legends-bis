import assert from 'node:assert/strict'
import test from 'node:test'
import { simulatorRecalcDecision } from './simulatorClasses.js'

test('removing one of 3 classes does not recalc or show the overlay', () => {
  const full = simulatorRecalcDecision(['Wizard', 'Cleric', 'Warrior'], 50)
  assert.equal(full.recalc, true)
  assert.equal(full.overlay, true)
  assert.equal(full.hint, '')
  const dropped = simulatorRecalcDecision(['Wizard', 'Cleric'], 50)
  assert.equal(dropped.recalc, false)
  assert.equal(dropped.overlay, false)
  assert.equal(dropped.hint, 'Pick 1 more class')
})

test('choosing the 3rd class triggers a recalc and the overlay', () => {
  const two = simulatorRecalcDecision(['Wizard', 'Cleric'], 20)
  assert.equal(two.recalc, false)
  assert.equal(two.overlay, false)
  const three = simulatorRecalcDecision(['Wizard', 'Cleric', 'Warrior'], 20)
  assert.equal(three.recalc, true)
  assert.equal(three.overlay, true)
})

test('below level 10, 2 classes trigger a recalc and the overlay', () => {
  const one = simulatorRecalcDecision(['Wizard'], 9)
  assert.equal(one.recalc, false)
  assert.equal(one.overlay, false)
  assert.equal(one.hint, 'Pick 1 more class')
  const two = simulatorRecalcDecision(['Wizard', 'Cleric'], 9)
  assert.equal(two.recalc, true)
  assert.equal(two.overlay, true)
  assert.equal(two.hint, '')
  const atTen = simulatorRecalcDecision(['Wizard', 'Cleric'], 10)
  assert.equal(atTen.recalc, false)
  assert.equal(atTen.overlay, false)
  assert.equal(atTen.hint, 'Pick 1 more class')
})
