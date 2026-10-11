import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { CloseActionSetting, xButtonValue } from './CloseActionSetting.jsx'

test('X button defaults to Quit and can show Minimize to tray', () => {
  assert.equal(xButtonValue(undefined), 'quit')
  assert.equal(xButtonValue({}), 'quit')
  assert.equal(xButtonValue({ closeToTray: true }), 'tray')
  assert.equal(xButtonValue({ xButton: 'quit', closeToTray: true }), 'quit')
  const quit = renderToStaticMarkup(React.createElement(CloseActionSetting, { value: 'quit' }))
  assert.match(quit, /data-testid="x-button-setting"/)
  assert.match(quit, /<option value="quit"/)
  assert.match(quit, /Minimize to tray/)
  assert.match(quit, /selected/)
  const tray = renderToStaticMarkup(React.createElement(CloseActionSetting, {
    value: 'tray',
    error: 'Could not save the X button setting.',
  }))
  assert.match(tray, /value="tray"/)
  assert.match(tray, /data-testid="x-button-error"/)
  assert.match(tray, /Could not save the X button setting/)
})
