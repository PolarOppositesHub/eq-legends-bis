import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { TitleBar } from './TitleBar.jsx'

test('the title bar matches the theme and does not double-toggle maximize', () => {
  const html = renderToStaticMarkup(React.createElement(TitleBar))
  assert.match(html, /data-testid="app-titlebar"/)
  assert.match(html, /data-testid="titlebar-minimize"/)
  assert.match(html, /aria-label="Minimize"/)
  assert.match(html, /data-testid="titlebar-maximize"/)
  assert.match(html, /aria-label="Maximize"/)
  assert.match(html, /data-testid="titlebar-close"/)
  assert.match(html, /aria-label="Close"/)
  assert.match(html, /EQ Legends BiS/)
  assert.equal(html.includes('<img'), false)
  const source = fs.readFileSync(new URL('./TitleBar.jsx', import.meta.url), 'utf8')
  assert.equal(source.includes('onDoubleClick'), false)
  const css = fs.readFileSync(new URL('./styles.css', import.meta.url), 'utf8')
  assert.match(css, /\.app-titlebar\s*\{[^}]*-webkit-app-region:\s*drag/s)
  assert.match(css, /\.app-titlebar-btn\s*\{[^}]*-webkit-app-region:\s*no-drag/s)
  assert.match(css, /html, body, #root \{[^}]*border:\s*0/)
  assert.match(css, /\.app \{[^}]*border:\s*0/)
})
