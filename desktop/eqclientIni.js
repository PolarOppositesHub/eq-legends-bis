/**
 * Read-only look at eqclient.ini [VideoMode] Fullscreen.
 * This module never writes the game file.
 */

const fs = require('fs')
const path = require('path')

const DEFAULT_EQ_DIR = 'C:\\Users\\Public\\Daybreak Game Company\\Installed Games\\EverQuest Legends'

const EXCLUSIVE_FULLSCREEN_WARNING = "EQ Legends is set to exclusive fullscreen, so overlays can't show over it. Switch to windowed/borderless (Fullscreen=0, window sized to your screen) or press Alt+Enter in game."

function eqclientIniPath(folder) {
  const dir = String(folder || '').trim()
  if (!dir) return path.win32.join(DEFAULT_EQ_DIR, 'eqclient.ini')
  return path.join(dir, 'eqclient.ini')
}

function videoModeSection(text) {
  const lines = String(text || '').split(/\r?\n/)
  const out = []
  let inside = false
  for (const line of lines) {
    const header = /^\s*\[([^\]]+)\]/.exec(line)
    if (header) {
      inside = header[1].trim().toLowerCase() === 'videomode'
      continue
    }
    if (inside) out.push(line)
  }
  return out.join('\n')
}

function parseVideoMode(text) {
  const section = videoModeSection(text)
  const match = /^\s*Fullscreen\s*=\s*([^;\r\n]*)/im.exec(section)
  if (!match) return { found: false, fullscreen: null, value: '' }
  const value = match[1].trim()
  return { found: true, fullscreen: value === '1', value }
}

function readEqClientVideoMode(folder, fsImpl = fs) {
  const file = eqclientIniPath(folder)
  let text = ''
  try {
    text = fsImpl.readFileSync(file, 'utf8')
  } catch (_) {
    return { path: file, missing: true, fullscreen: null, warning: '' }
  }
  const parsed = parseVideoMode(text)
  return {
    path: file,
    missing: false,
    fullscreen: parsed.fullscreen,
    warning: parsed.fullscreen ? EXCLUSIVE_FULLSCREEN_WARNING : '',
  }
}

module.exports = {
  DEFAULT_EQ_DIR,
  EXCLUSIVE_FULLSCREEN_WARNING,
  eqclientIniPath,
  parseVideoMode,
  readEqClientVideoMode,
}
