import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { AskAiControl } from './askAi.jsx'
import {
  GROK_HOME,
  askPlace,
  buildAskPrompt,
  deliverAsk,
  grokLink,
  isGrokUrl,
  knownDeltas,
} from './askAi.js'

const cloak = {
  name: 'Cloak of Flames',
  stats_plus0: { AC: 12, HP: 20, Haste: 36, DMG: 0 },
}

test('the open page picks the context and missing numbers stay unknown', () => {
  assert.equal(askPlace('bis'), 'bis')
  assert.equal(askPlace('sim'), 'sim')
  assert.equal(askPlace('parser'), 'parser')
  assert.equal(askPlace('character'), 'gear')
  assert.equal(askPlace('overview'), 'gear')

  const gear = buildAskPrompt('character', 'What should I replace?', {
    character: '',
    classes: [],
    level: 50,
    race: 'Human',
    slots: ['CHEST', 'BACK'],
    equipment: { BACK: 'Cloak of Flames' },
    wornUpgrades: {},
    slotItems: { BACK: [cloak] },
  })
  assert.equal(gear.ok, true)
  assert.match(gear.prompt, /Question: What should I replace\?/)
  assert.match(gear.prompt, /Character: unknown/)
  assert.match(gear.prompt, /Classes: unknown/)
  assert.match(gear.prompt, /Cloak of Flames/)
  assert.match(gear.prompt, /upgrade unknown/)
  assert.match(gear.prompt, /\+0 catalog AC 12, HP 20, Haste 36/)
  assert.equal(gear.prompt.includes('DMG'), false)
  assert.equal(gear.prompt.includes('CHEST'), false)

  const recorded = buildAskPrompt('character', 'Check the cloak', {
    character: 'Zasariz',
    classes: ['Wizard'],
    level: 29,
    slots: ['BACK'],
    equipment: { BACK: 'Cloak of Flames' },
    wornUpgrades: { BACK: 10 },
    slotItems: { BACK: [cloak] },
  })
  assert.match(recorded.prompt, /recorded \+10/)
  assert.match(recorded.prompt, /Haste 46/)
  assert.equal(recorded.prompt.includes('Haste 36'), false)

  const empty = buildAskPrompt('bis', '   ', {})
  assert.equal(empty.ok, false)
})

test('Best in Slot and Simulator context do not invent a missing stat', () => {
  const bis = buildAskPrompt('bis', 'Is the chest pick real?', {
    character: 'Zasariz',
    classes: ['Warrior', 'Paladin'],
    bis: {
      mode: 'priority',
      upgrade: 5,
      character_level: 50,
      primary_stats: ['STA'],
      slots: [
        {
          slot: 'CHEST',
          name: 'Breastplate of the Hateful',
          zone: '',
          haste: null,
          stats_plus0: { AC: 40, HP: 80 },
          alts: [{ name: 'Spare Plate' }, { name: 'Other Plate' }, { name: 'Third' }],
        },
        { slot: 'HEAD', name: '' },
      ],
    },
  })
  assert.match(bis.prompt, /Context: Best in Slot picks/)
  assert.match(bis.prompt, /zone unknown/)
  assert.match(bis.prompt, /stats at \+5 unknown/)
  assert.match(bis.prompt, /\+0 catalog AC 40, HP 80/)
  assert.match(bis.prompt, /alternates Spare Plate, Other Plate and 1 more/)
  assert.match(bis.prompt, /HEAD: empty/)
  assert.equal(bis.prompt.includes('STA 0'), false)
  assert.equal(bis.prompt.includes('refresh_token'), false)

  const sim = buildAskPrompt('sim', 'Compare the back slot', {
    character: 'Zasariz',
    classes: ['Wizard'],
    level: 50,
    race: '',
    upgrade: 0,
    slots: ['BACK'],
    equipment: { BACK: 'Cloak of Flames' },
    wornUpgrades: { BACK: 0 },
    bisOverrides: { BACK: 'Cloak of Flames' },
    bisUpgrades: { BACK: 10 },
    slotItems: { BACK: [cloak] },
    buildName: 'Fire',
  })
  assert.match(sim.prompt, /Race: unknown/)
  assert.match(sim.prompt, /Build name: Fire/)
  assert.match(sim.prompt, /worn Cloak of Flames/)
  assert.match(sim.prompt, /recorded \+0/)
  assert.match(sim.prompt, /recorded \+10/)
  assert.match(sim.prompt, /Haste \+10/)
  assert.equal(knownDeltas({ AC: 1 }, null), null)
  assert.deepEqual(knownDeltas({ AC: 1 }, { HP: 2 }), [])
  assert.deepEqual(knownDeltas({ AC: 10, HP: 5 }, { AC: 12, HP: 5 }), ['AC +2'])
})

test('a parser fight with no damage number is unknown, not zero', () => {
  const none = buildAskPrompt('parser', 'How did this fight go?', {
    parser: { status: 'idle', fight: null, detail: null, character: '' },
  })
  assert.match(none.prompt, /No fight is selected/)
  assert.match(none.prompt, /unknown/)
  assert.equal(none.prompt.includes('0.0'), false)
  assert.equal(none.prompt.includes('Total damage: 0'), false)

  const fight = buildAskPrompt('parser', 'Summarize this fight', {
    parser: {
      status: 'ready',
      character: 'Zasariz',
      fight: {
        start_ts: '2026-08-04T22:00:01',
        zone: 'Befallen',
        targets: ['a rat'],
        duration_seconds: 30,
        damage: 20,
      },
      detail: {
        sources: [
          { source: 'Zasariz', damage: 20, dps: 0.6, nested: false },
          { source: 'a warder', damage: 5, nested: true },
        ],
      },
    },
  })
  assert.match(fight.prompt, /Befallen/)
  assert.match(fight.prompt, /Total damage: 20/)
  assert.match(fight.prompt, /Your DPS: unknown/)
  assert.match(fight.prompt, /Source Zasariz: damage 20, DPS 0\.6/)
  assert.equal(fight.prompt.includes('a warder'), false)
})

test('a short prompt is prefilled on grok.com and a long one is copied instead', async () => {
  const short = grokLink('What is a cloak?')
  assert.equal(short.prefilled, true)
  assert.equal(short.copy, false)
  assert.equal(isGrokUrl(short.url), true)
  assert.match(short.url, /^https:\/\/grok\.com\/\?q=/)
  const joined = grokLink('a & b\nline')
  assert.match(joined.url, /a%20%26%20b%0Aline/)

  const long = grokLink('x'.repeat(2000))
  assert.equal(long.prefilled, false)
  assert.equal(long.copy, true)
  assert.equal(long.url, GROK_HOME)

  const opened = []
  const copied = []
  const local = await deliverAsk({
    prompt: 'hello',
    askLocal: async () => ({ mode: 'answer', text: 'Bearer secret-token\nUse the cloak.' }),
    openUrl: (url) => opened.push(url),
    copyText: async (text) => copied.push(text),
  })
  assert.equal(local.mode, 'answer')
  assert.match(local.text, /Use the cloak/)
  assert.equal(local.text.includes('secret-token'), false)
  assert.equal(opened.length, 0)

  const browser = await deliverAsk({
    prompt: 'x'.repeat(2000),
    askLocal: async () => { throw new Error('missing') },
    openUrl: (url) => opened.push(url),
    copyText: async (text) => {
      copied.push(text)
      return true
    },
  })
  assert.equal(browser.mode, 'browser')
  assert.equal(browser.toast, 'Prompt copied. Paste it into Grok.')
  assert.equal(opened[0], GROK_HOME)
  assert.equal(copied[0].length, 2000)

  const refused = []
  await deliverAsk({
    prompt: 'hi',
    askLocal: async () => ({ mode: 'browser', reason: 'not-signed-in' }),
    openUrl: (url) => refused.push(url),
    copyText: async () => true,
  })
  assert.equal(isGrokUrl(refused[0]), true)
  assert.equal(refused[0].includes('not-signed-in'), false)
})

test('the header has one Ask AI button', () => {
  const html = renderToStaticMarkup(React.createElement(AskAiControl, {
    tab: 'bis',
    snapshot: {},
  }))
  assert.match(html, /data-testid="ask-ai-button"/)
  assert.match(html, /Ask about these Best in Slot picks/)
  assert.equal(html.split('data-testid="ask-ai-button"').length - 1, 1)
  assert.equal(html.includes('data-testid="ask-ai-dialog"'), false)
})
