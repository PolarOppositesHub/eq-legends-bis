import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { AskAiDialog } from './askAi.jsx'
import {
  CLI_STATE_TEXT,
  URL_MAX_LENGTH,
  buildContextPack,
  grokUrl,
  prepareAsk,
} from './askAi.js'

const GEAR = 'Cloak of Flames unique-token-9912'
const CHAT = [
  "Jenann told you, 'Attacking a rat Master.'",
  "Jaber says, 'Following you, Master.'",
  "You told Mote, 'hello there'",
  "Bard tells the guild, 'raid tonight'",
  "Healer tells the group, 'pull north'",
].join('\n')

function snapshot() {
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
  const pack = buildContextPack(snapshot(), `Should I upgrade?\n${CHAT}`)
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
  const pack = buildContextPack(snapshot(), "Jenann told you, 'Attacking a rat Master.'")
  assert.match(pack, /left out because it was a chat line/)
  assert.equal(pack.includes('told you'), false)
})

test('long context stays off the URL and the URL stays under the cap', () => {
  const question = `${'upgrade the cloak '.repeat(400)}\n${CHAT}`
  const prepared = prepareAsk(snapshot(), question)
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
    snapshot: snapshot(),
    onClose: () => {},
    status: { state: 'ready', detail: 'Signed in.' },
  }))
  assert.match(ready, /data-testid="ask-ai-dialog"/)
  assert.match(ready, /Beta/)
  assert.match(ready, /Copy context/)
  assert.match(ready, /Ask in the app/)
  assert.match(ready, new RegExp(CLI_STATE_TEXT.ready))

  const missing = renderToStaticMarkup(React.createElement(AskAiDialog, {
    snapshot: snapshot(),
    onClose: () => {},
    status: { state: 'not_installed', detail: '' },
  }))
  assert.match(missing, new RegExp(CLI_STATE_TEXT.not_installed))
  assert.match(missing, /Install Grok Build/)
  assert.equal(missing.includes('Ask in the app'), false)

  const signedOut = renderToStaticMarkup(React.createElement(AskAiDialog, {
    snapshot: snapshot(),
    onClose: () => {},
    status: { state: 'not_signed_in', detail: '' },
    desktop: { grokLogin: () => {} },
  }))
  assert.match(signedOut, new RegExp(CLI_STATE_TEXT.not_signed_in))
  assert.match(signedOut, /Sign in with your Grok account/)

  const failed = renderToStaticMarkup(React.createElement(AskAiDialog, {
    snapshot: snapshot(),
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
