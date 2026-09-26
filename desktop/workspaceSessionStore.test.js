const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const test = require('node:test');
const {
  FILE_NAME,
  clearWorkspaceSession,
  readWorkspaceSession,
  sessionFilePath,
  writeWorkspaceSession,
} = require('./workspaceSessionStore');

function tempUserData() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'eq-legends-userdata-'));
}

test('session file lives in userData and is not tied to version or port', () => {
  const userData = path.join(os.tmpdir(), 'EQ Legends BiS');
  const filePath = sessionFilePath(userData);
  assert.equal(path.basename(filePath), FILE_NAME);
  assert.equal(path.dirname(filePath), userData);
  assert.equal(filePath.includes('1.0.'), false);
  assert.equal(filePath.includes('127.0.0.1'), false);
  assert.equal(/:\d+/.test(filePath), false);
  assert.equal(filePath.includes(`${path.sep}Local Storage`), false);
});

test('round-trip, corrupt file, and settings.json stay independent', () => {
  const dir = tempUserData();
  const settingsPath = path.join(dir, 'settings.json');
  const settings = {
    eqInstallFolder: 'C:\\Games\\EverQuest Legends',
    lastInventoryName: 'Hero-Inventory.txt',
  };
  fs.writeFileSync(settingsPath, JSON.stringify(settings), 'utf8');

  assert.equal(readWorkspaceSession(dir), null);

  const session = {
    v: 1,
    tab: 'sim',
    classes: ['Monk', 'Wizard', 'Cleric'],
    race: 'Dark Elf',
    characterLevel: 42,
    equipment: { PRIMARY: 'Jade Mace' },
    searchQ: 'jade',
    searchSelectedName: 'Jade Mace',
    searchItemUpgrade: 4,
  };
  writeWorkspaceSession(dir, session);
  assert.deepEqual(readWorkspaceSession(dir), session);
  assert.deepEqual(JSON.parse(fs.readFileSync(settingsPath, 'utf8')), settings);

  fs.writeFileSync(sessionFilePath(dir), '{truncated', 'utf8');
  assert.equal(readWorkspaceSession(dir), null);
  assert.deepEqual(JSON.parse(fs.readFileSync(settingsPath, 'utf8')), settings);

  writeWorkspaceSession(dir, { tab: 'bis' });
  clearWorkspaceSession(dir);
  assert.equal(readWorkspaceSession(dir), null);
  assert.equal(fs.existsSync(settingsPath), true);
});

test('non-objects are rejected and do not replace a good file', () => {
  const dir = tempUserData();
  writeWorkspaceSession(dir, { tab: 'quests' });
  assert.throws(() => writeWorkspaceSession(dir, ['nope']));
  assert.throws(() => writeWorkspaceSession(dir, null));
  assert.equal(readWorkspaceSession(dir).tab, 'quests');
  fs.writeFileSync(sessionFilePath(dir), '[]', 'utf8');
  assert.equal(readWorkspaceSession(dir), null);
});
