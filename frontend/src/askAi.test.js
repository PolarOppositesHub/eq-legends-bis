import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { AskAiControl, AskAiDialog } from './askAi.jsx'
import {
  CLI_STATE_TEXT,
  GROK_HOME,
  URL_MAX_LENGTH,
  askPlace,
  buildAskPrompt,
  buildContextPack,
  deliverAsk,
  grokLink,
  grokUrl,
  isGrokUrl,
  knownDeltas,
  prepareAsk,
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

test('a short prompt is prefilled on grok.com and the full pack is copied', async () => {
  const short = grokLink('What is a cloak?')
  assert.equal(short.prefilled, true)
  assert.equal(short.copy, true)
  assert.equal(isGrokUrl(short.url), true)
  assert.match(short.url, /^https:\/\/grok\.com\/\?q=/)
  assert.equal(short.url.includes('What%20is%20a%20cloak'), true)
  const joined = grokLink('a & b\nline')
  assert.match(decodeURIComponent(joined.url.split('?q=')[1]), /a & b line/)
  assert.equal(joined.url.includes('%0A'), false)

  const long = grokLink('x'.repeat(2000))
  assert.equal(long.prefilled, true)
  assert.equal(long.copy, true)
  assert.ok(long.url.startsWith('https://grok.com/?q='))
  assert.ok(long.url.length <= 1800)
  assert.equal(long.url.includes('x'.repeat(200)), false)

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
  assert.match(browser.toast, /clipboard/)
  assert.ok(opened[0].startsWith('https://grok.com/'))
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
  assert.match(html, /data-testid="ask-ai-open"/)
})

const GEAR = 'Cloak of Flames unique-token-9912'
const CHAT = [
  "Jenann told you, 'Attacking a rat Master.'",
  "Jaber says, 'Following you, Master.'",
  "You told Mote, 'hello there'",
  "Bard tells the guild, 'raid tonight'",
  "Healer tells the group, 'pull north'",
].join('\n')

function packSnapshot() {
  return {
    view: 'bis',
    character: 'Zasariz',
    classes: ['Wizard', 'Enchanter'],
    level: 29,
    equipment: { BACK: GEAR },
    wornUpgrades: { BACK: 4 },
    bisSlots: [{ slot: 'BACK', name: GEAR }],
    bisUpgrade: 10,
    currencies: null,
    parse: {
      id: 7,
      zone: 'Befallen',
      targets: ['a rat'],
      duration_seconds: 30,
      totals: { damage: 120, dps: 4 },
      sources: [{ name: 'Zasariz', kind: 'self', damage: 100, dps: 3.333 }],
    },
  }
}

test('context pack excludes chat and keeps the loadout', () => {
  const pack = buildContextPack(packSnapshot(), `Should I upgrade?\n${CHAT}`)
  assert.match(pack, /Wizard \/ Enchanter @ 29/)
  assert.match(pack, /this loadout only/)
  assert.match(pack, new RegExp(GEAR))
  assert.match(pack, /Befallen/)
  assert.equal(pack.includes('told you'), false)
  assert.equal(pack.includes('says,'), false)
  assert.equal(pack.includes('You told'), false)
  assert.equal(pack.includes('tells the guild'), false)
  assert.equal(pack.includes('tells the group'), false)
  assert.match(pack, /Should I upgrade\?/)
})

test('a chat-only question is left out of the pack', () => {
  const pack = buildContextPack(packSnapshot(), "Jenann told you, 'Attacking a rat Master.'")
  assert.match(pack, /left out because it was a chat line/)
  assert.equal(pack.includes('told you'), false)
})

test('long context stays off the URL and the URL stays under the cap', () => {
  const question = `${'upgrade the cloak '.repeat(400)}\n${CHAT}`
  const prepared = prepareAsk(packSnapshot(), question)
  assert.ok(prepared.pack.length > 500)
  assert.ok(prepared.url.startsWith('https://grok.com/?q='))
  assert.ok(prepared.url.length <= URL_MAX_LENGTH)
  assert.equal(prepared.url.includes(GEAR), false)
  assert.equal(prepared.url.includes('Befallen'), false)
  assert.equal(prepared.url.includes('told you'), false)
  assert.equal(decodeURIComponent(prepared.url).includes(GEAR), false)
  const huge = grokUrl('Q'.repeat(5000))
  assert.ok(huge.length <= URL_MAX_LENGTH)
  assert.ok(huge.startsWith('https://grok.com/'))
})

test('missing gear and parse stay unknown', () => {
  const pack = buildContextPack({ view: 'maps', classes: [], level: null }, '')
  assert.match(pack, /unknown classes @ unknown/)
  assert.match(pack, /Worn gear[\s\S]*unknown/)
  assert.match(pack, /Parse:[\s\S]*unknown/)
  assert.match(pack, /Question:[\s\S]*none yet/)
})

test('dialog shows the CLI states, beta label, and copy fallback', () => {
  const ready = renderToStaticMarkup(React.createElement(AskAiDialog, {
    snapshot: packSnapshot(),
    onClose: () => {},
    status: { state: 'ready', detail: 'Signed in.' },
  }))
  assert.match(ready, /data-testid="ask-ai-dialog"/)
  assert.match(ready, /Beta/)
  assert.match(ready, /Copy context/)
  assert.match(ready, /Ask in the app/)
  assert.match(ready, new RegExp(CLI_STATE_TEXT.ready))

  const missing = renderToStaticMarkup(React.createElement(AskAiDialog, {
    snapshot: packSnapshot(),
    onClose: () => {},
    status: { state: 'not_installed', detail: '' },
  }))
  assert.match(missing, new RegExp(CLI_STATE_TEXT.not_installed))
  assert.match(missing, /Install Grok Build/)
  assert.equal(missing.includes('Ask in the app'), false)

  const signedOut = renderToStaticMarkup(React.createElement(AskAiDialog, {
    snapshot: packSnapshot(),
    onClose: () => {},
    status: { state: 'not_signed_in', detail: '' },
    desktop: { grokLogin: () => {} },
  }))
  assert.match(signedOut, new RegExp(CLI_STATE_TEXT.not_signed_in))
  assert.match(signedOut, /Sign in with your Grok account/)

  const failed = renderToStaticMarkup(React.createElement(AskAiDialog, {
    snapshot: packSnapshot(),
    onClose: () => {},
    status: { state: 'ready', detail: '' },
    runError: {
      kind: 'quota',
      friendly: 'Grok said this account is out of quota.',
      fallbackCopy: true,
    },
  }))
  assert.match(failed, /data-testid="ask-ai-error"/)
  assert.match(failed, /out of quota/)
  assert.match(failed, /data-testid="ask-ai-fallback"/)
  assert.match(failed, /data-testid="ask-ai-copy"/)
})
