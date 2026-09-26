import assert from 'node:assert/strict'
import test from 'node:test'
import {
  WORKSPACE_VERSION,
  buildWorkspaceSnapshot,
  catalogFromMeta,
  defaultWorkspace,
  sanitizeWorkspace,
} from './workspaceSession.js'
import {
  WORKSPACE_STORAGE_KEY,
  clearWorkspaceSession,
  loadWorkspaceSession,
  saveWorkspaceSession,
} from './workspaceStore.js'

const catalog = catalogFromMeta({
  classes: ['Warrior', 'Cleric', 'Wizard', 'Monk'],
  races: { races: [{ name: 'Human' }, { name: 'Barbarian' }, { name: 'Dark Elf' }] },
  slots: ['HEAD', 'CHEST', 'PRIMARY', 'SECONDARY'],
  priority_stats: [{ key: 'INT' }, { key: 'STA' }, { key: 'HP' }],
  modes: [{ id: 'priority' }, { id: 'max' }, { id: 'ai' }],
  character_levels: Array.from({ length: 50 }, (_, i) => i + 1),
})

test('missing or corrupt session falls back to defaults', () => {
  for (const raw of [null, undefined, 'nope', 3, [], '{"tab":']) {
    const result = sanitizeWorkspace(raw, catalog)
    assert.equal(result.restored, false)
    assert.deepEqual(result.state.classes, [])
    assert.equal(result.state.tab, 'bis')
    assert.equal(result.state.race, 'Human')
    assert.equal(result.state.characterLevel, 50)
    assert.equal(result.state.uiSettings, null)
  }
})

test('unknown classes, race, slot, stat, mode, and item shapes fall back per field', () => {
  const { restored, state } = sanitizeWorkspace({
    v: 1,
    tab: 'retired-view',
    classes: ['NotAClass', 'wizard', 'Cleric', 'Monk', 'Warrior'],
    mode: 'obsolete',
    primaryStats: ['NOPE', 'INT', 4],
    race: 'Martian',
    characterLevel: 900,
    upgrade: 'high',
    equipment: {
      NOT_A_SLOT: 'Foo',
      HEAD: 12,
      CHEST: { name: '  Breastplate of the Hateful  ' },
      PRIMARY: '',
      SECONDARY: { id: 4 },
    },
    wornUpgrades: { CHEST: 12, HEAD: -3, GLOVES: 4 },
    bisOverrides: { CHEST: 'Gone Item', NECK: 'Nope' },
    searchSlot: 'FEET',
    searchSelectedName: { name: 'Jade Mace' },
    searchItemUpgrade: 7,
    mobKind: 'boss-dragon',
    mobEra: 'luclin',
    castBuffsMode: 'always',
    builds: [{ id: 'should-not-stick', name: 'Manual loadout' }],
  }, catalog)

  assert.equal(restored, true)
  assert.equal(state.tab, 'bis')
  assert.deepEqual(state.classes, ['Wizard', 'Cleric', 'Monk'])
  assert.equal(state.mode, 'priority')
  assert.deepEqual(state.primaryStats, ['', 'INT', ''])
  assert.equal(state.race, 'Human')
  assert.equal(state.characterLevel, 50)
  assert.equal(state.upgrade, 10)
  assert.deepEqual(state.equipment, { CHEST: 'Breastplate of the Hateful' })
  assert.deepEqual(state.wornUpgrades, { CHEST: 10, HEAD: 0 })
  assert.deepEqual(state.bisOverrides, { CHEST: 'Gone Item' })
  assert.equal(state.searchSlot, '')
  assert.equal(state.searchSelectedName, 'Jade Mace')
  assert.equal(state.searchItemUpgrade, 7)
  assert.equal(state.mobKind, 'all')
  assert.equal(state.mobEra, 'all')
  assert.equal(state.castBuffsMode, 'off')
  assert.equal(state.builds, undefined)
})

test('itemExists drops names the catalog no longer has', () => {
  const withItems = {
    ...catalog,
    itemExists: (name) => name === 'Still Here',
  }
  const { state } = sanitizeWorkspace({
    searchSelectedName: 'Removed Helm',
    searchItemUpgrade: 8,
    equipment: { HEAD: 'Removed Helm', CHEST: 'Still Here' },
    bisOverrides: { PRIMARY: 'Removed Helm' },
  }, withItems)
  assert.equal(state.searchSelectedName, '')
  assert.equal(state.searchItemUpgrade, 0)
  assert.deepEqual(state.equipment, { CHEST: 'Still Here' })
  assert.deepEqual(state.bisOverrides, {})
})

test('snapshot keeps a 3-class trio and does not embed saved loadouts', () => {
  const snap = buildWorkspaceSnapshot({
    tab: 'search',
    classes: ['Monk', 'Wizard', 'Cleric'],
    race: 'Dark Elf',
    characterLevel: 42,
    mode: 'ai',
    upgrade: 6,
    preferRanged: false,
    equipment: { PRIMARY: 'Jade Mace' },
    wornUpgrades: { PRIMARY: 4 },
    bisUpgrades: { PRIMARY: 10 },
    bisOverrides: { PRIMARY: 'Jade Mace' },
    searchQ: 'jade',
    searchSlot: 'PRIMARY',
    searchSelectedName: 'Jade Mace',
    searchItemUpgrade: 4,
    bagsQ: 'rune',
    questQ: 'bone chips',
    selectedQuestName: 'Bone Chips',
    questRewardUpgrade: 3,
    mobQ: 'phinigel',
    mobKind: 'raid',
    mobEra: 'classic',
    buildName: 'draft',
    selectedBuildId: 'abc',
    uiSettings: { theme: 'forge', funnyLoadingTips: false, compactBadges: true, reduceMotion: true, extra: true },
    builds: [{ name: 'do not copy' }],
  }, catalog)

  assert.equal(snap.v, WORKSPACE_VERSION)
  assert.deepEqual(snap.classes, ['Monk', 'Wizard', 'Cleric'])
  assert.equal(snap.tab, 'search')
  assert.equal(snap.race, 'Dark Elf')
  assert.equal(snap.characterLevel, 42)
  assert.equal(snap.searchQ, 'jade')
  assert.equal(snap.searchSelectedName, 'Jade Mace')
  assert.equal(snap.searchItemUpgrade, 4)
  assert.equal(snap.uiSettings.theme, 'forge')
  assert.equal(snap.uiSettings.extra, undefined)
  assert.equal(snap.builds, undefined)
  assert.equal(defaultWorkspace(catalog).tab, 'bis')
})

test('bad theme falls back and import rows that are not items are dropped', () => {
  const { state } = sanitizeWorkspace({
    uiSettings: { theme: 'neon', funnyLoadingTips: 'yes' },
    importMeta: {
      source: 'Hero-Inventory.txt',
      all_items: [
        null,
        { name: 'Empty', location: 'Head' },
        { name: 'Flowing Black Robe', location: 'Chest', upgrade_from_name: 2, extraBlob: { huge: true } },
        'Short Sword',
      ],
      equipment: { CHEST: 'Flowing Black Robe' },
    },
  }, catalog)
  assert.equal(state.uiSettings.theme, 'classic')
  assert.equal(state.uiSettings.funnyLoadingTips, true)
  assert.equal(state.importMeta.all_items.length, 2)
  assert.equal(state.importMeta.all_items[0].name, 'Flowing Black Robe')
  assert.equal(state.importMeta.all_items[0].extraBlob, undefined)
  assert.equal(state.importMeta.all_items[1].base_name, 'Short Sword')
  assert.deepEqual(state.importMeta.equipment, { CHEST: 'Flowing Black Robe' })
})

function memoryStorage(seed = {}) {
  const data = { ...seed }
  return {
    getItem: (k) => (Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v) },
    removeItem: (k) => { delete data[k] },
    dump: () => ({ ...data }),
  }
}

test('browser store uses a fixed key and ignores corrupt JSON', async () => {
  const storage = memoryStorage({
    [WORKSPACE_STORAGE_KEY]: '{not json',
    'eq-legends-bis-saved-builds-v1': '[{"id":"1","name":"Keep me"}]',
  })
  const env = {
    getDesktop: () => null,
    storage: () => storage,
  }
  assert.equal(await loadWorkspaceSession(env), null)
  const saved = await saveWorkspaceSession({ v: 1, tab: 'sim', classes: ['Monk'] }, env)
  assert.equal(saved.ok, true)
  const loaded = await loadWorkspaceSession(env)
  assert.equal(loaded.tab, 'sim')
  assert.equal(storage.dump()['eq-legends-bis-saved-builds-v1'], '[{"id":"1","name":"Keep me"}]')
  await clearWorkspaceSession(env)
  assert.equal(await loadWorkspaceSession(env), null)
  assert.equal(storage.dump()['eq-legends-bis-saved-builds-v1'], '[{"id":"1","name":"Keep me"}]')
})

test('desktop bridge ignores port-scoped localStorage', async () => {
  const storage = memoryStorage({
    [WORKSPACE_STORAGE_KEY]: JSON.stringify({ tab: 'bags', classes: ['From the wrong port'] }),
  })
  const disk = { value: { tab: 'mobs', classes: ['Monk', 'Cleric', 'Wizard'] } }
  const calls = []
  const env = {
    getDesktop: () => ({
      isDesktop: true,
      getWorkspace: async () => {
        calls.push('get')
        return { ok: true, workspace: disk.value }
      },
      setWorkspace: async (session) => {
        calls.push('set')
        disk.value = session
        return { ok: true }
      },
      clearWorkspace: async () => {
        calls.push('clear')
        disk.value = null
        return { ok: true }
      },
    }),
    storage: () => storage,
  }
  const loaded = await loadWorkspaceSession(env)
  assert.deepEqual(loaded.classes, ['Monk', 'Cleric', 'Wizard'])
  assert.equal(loaded.tab, 'mobs')
  await saveWorkspaceSession({ tab: 'search', searchQ: 'jade' }, env)
  assert.equal(disk.value.tab, 'search')
  assert.equal(storage.dump()[WORKSPACE_STORAGE_KEY].includes('wrong port'), true)
  await clearWorkspaceSession(env)
  assert.equal(disk.value, null)
  assert.deepEqual(calls, ['get', 'set', 'clear'])
})
