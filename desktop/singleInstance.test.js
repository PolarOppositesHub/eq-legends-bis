const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const test = require('node:test');

const mainJs = fs.readFileSync(path.join(__dirname, 'main.js'), 'utf8');

test('main process takes the single-instance lock before starting a sidecar', () => {
  const lockAt = mainJs.indexOf('app.requestSingleInstanceLock()');
  assert.ok(lockAt >= 0, 'main.js must call app.requestSingleInstanceLock()');
  assert.match(mainJs, /app\.on\('second-instance'/);
  const readyAt = mainJs.indexOf('app.whenReady()');
  assert.ok(lockAt < readyAt, 'lock must be taken before whenReady starts the API');
  assert.match(mainJs, /if \(!gotSingleInstanceLock\) return;/);
});

test('sidecar output is written to a log file, not only the console', () => {
  assert.match(mainJs, /logs', 'main\.log'|'main\.log'/);
  assert.match(mainJs, /mainLog\('api'/);
});

test('dev sidecar tries the repo backend before the resources snapshot', () => {
  const start = mainJs.indexOf('function findPythonSidecar');
  const end = mainJs.indexOf('function rootForScripts');
  assert.ok(start >= 0 && end > start);
  const block = mainJs.slice(start, end);
  const repoAt = block.indexOf("path.join(appRoot, 'backend', 'packaging', 'api_entry.py')");
  const mirrorAt = block.indexOf("path.join(res, 'backend', 'packaging', 'api_entry.py')");
  assert.ok(repoAt >= 0 && mirrorAt >= 0);
  assert.ok(repoAt < mirrorAt, 'repo backend must be tried before desktop/resources/backend');
});

test('API env prefers the repo root over the resources snapshot', () => {
  const start = mainJs.indexOf('function envForApi');
  const end = mainJs.indexOf('function findFreePort');
  assert.ok(start >= 0 && end > start);
  const block = mainJs.slice(start, end);
  assert.match(block, /const repoBackend = path\.join\(appRoot, 'backend', 'app'\)/);
  const repoCheck = block.indexOf('fs.existsSync(repoBackend)');
  const useRepo = block.indexOf('? appRoot');
  assert.ok(repoCheck >= 0 && useRepo > repoCheck);
});
