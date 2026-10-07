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

test('round-trip restores trio, search slider, and inventory import', async () => {
  const storage = memoryStorage()
  const env = { getDesktop: () => null, storage: () => storage }
  const snap = buildWorkspaceSnapshot({
    tab: 'search',
    classes: ['Monk', 'Wizard', 'Cleric'],
    race: 'Dark Elf',
    characterLevel: 42,
    mode: 'ai',
    upgrade: 6,
    equipment: { CHEST: 'Flowing Black Robe', PRIMARY: 'Jade Mace' },
    wornUpgrades: { PRIMARY: 4 },
    bisOverrides: { CHEST: 'Flowing Black Robe' },
    searchQ: 'cloak of flames',
    searchSlot: 'PRIMARY',
    searchSelectedName: 'Cloak of Flames',
    searchItemUpgrade: 10,
    importMeta: {
      source: 'Synth-Inventory.txt',
      all_items: [{ name: 'Cloak of Flames', location: 'Back', upgrade_from_name: 0 }],
      equipment: { CHEST: 'Flowing Black Robe' },
    },
  }, catalog)
  const saved = await saveWorkspaceSession(snap, env)
  assert.equal(saved.ok, true)
  const loaded = await loadWorkspaceSession(env)
  assert.deepEqual(loaded, snap)
  const again = sanitizeWorkspace(loaded, catalog)
  assert.equal(again.restored, true)
  assert.deepEqual(again.state.classes, ['Monk', 'Wizard', 'Cleric'])
  assert.equal(again.state.tab, 'search')
  assert.equal(again.state.race, 'Dark Elf')
  assert.equal(again.state.characterLevel, 42)
  assert.equal(again.state.searchQ, 'cloak of flames')
  assert.equal(again.state.searchSelectedName, 'Cloak of Flames')
  assert.equal(again.state.searchItemUpgrade, 10)
  assert.deepEqual(again.state.equipment, { CHEST: 'Flowing Black Robe', PRIMARY: 'Jade Mace' })
  assert.equal(again.state.importMeta.source, 'Synth-Inventory.txt')
  assert.equal(again.state.importMeta.all_items[0].name, 'Cloak of Flames')
  assert.equal(again.state.bisOverrides.CHEST, 'Flowing Black Robe')
})

test('future keys do not break loading the current session', () => {
  const future = {
    v: 1,
    tab: 'sim',
    classes: ['Monk', 'Wizard', 'Cleric'],
    race: 'Dark Elf',
    characterLevel: 42,
    searchQ: 'cloak of flames',
    searchSlot: 'PRIMARY',
    searchSelectedName: 'Cloak of Flames',
    searchItemUpgrade: 5,
    equipment: { PRIMARY: 'Jade Mace' },
    parserSettings: { live: true, idleSeconds: 30, zones: ['plane of sky'] },
    currencies: { motes: { 'Mote of Potential': 4 }, windRunes: { Azia: 1 } },
    overlay: null,
    extraNumber: 1,
  }
  const { restored, state } = sanitizeWorkspace(future, catalog)
  assert.equal(restored, true)
  assert.equal(state.tab, 'sim')
  assert.deepEqual(state.classes, ['Monk', 'Wizard', 'Cleric'])
  assert.equal(state.race, 'Dark Elf')
  assert.equal(state.characterLevel, 42)
  assert.equal(state.searchQ, 'cloak of flames')
  assert.equal(state.searchSelectedName, 'Cloak of Flames')
  assert.equal(state.searchItemUpgrade, 5)
  assert.deepEqual(state.equipment, { PRIMARY: 'Jade Mace' })
  assert.equal(state.parserSettings, undefined)
  assert.equal(state.currencies, undefined)
  assert.equal(state.overlay, undefined)
  assert.equal(state.parserLogPath, '')
  assert.equal(state.parserMergePets, true)
  assert.equal(state.parserFightId, null)
  assert.equal(state.whatsNewSeen, '')
})

test('parser tab stays active across a session restore', async () => {
  const storage = memoryStorage()
  const env = { getDesktop: () => null, storage: () => storage }
  const snap = buildWorkspaceSnapshot({
    tab: 'parser',
    classes: ['Monk', 'Wizard', 'Cleric'],
    race: 'Dark Elf',
    characterLevel: 42,
    parserLogPath: 'C:\\Users\\Public\\Daybreak Game Company\\Installed Games\\EverQuest Legends\\Logs\\eqlog_Zasariz_qeynos.txt',
    parserMergePets: false,
    parserFightId: 12,
    whatsNewSeen: '1.1.0',
    parserSettings: { live: true },
    currencies: { motes: 4 },
  }, catalog)
  assert.equal(snap.tab, 'parser')
  assert.equal(snap.parserMergePets, false)
  assert.equal(snap.parserFightId, 12)
  assert.equal(snap.whatsNewSeen, '1.1.0')
  assert.match(snap.parserLogPath, /eqlog_Zasariz_qeynos\.txt$/)
  assert.equal(snap.parserSettings, undefined)
  assert.equal(snap.currencies, undefined)
  const saved = await saveWorkspaceSession(snap, env)
  assert.equal(saved.ok, true)
  const loaded = await loadWorkspaceSession(env)
  const again = sanitizeWorkspace(loaded, catalog)
  assert.equal(again.restored, true)
  assert.equal(again.state.tab, 'parser')
  assert.deepEqual(again.state.classes, ['Monk', 'Wizard', 'Cleric'])
  assert.equal(again.state.race, 'Dark Elf')
  assert.equal(again.state.characterLevel, 42)
  assert.equal(again.state.parserMergePets, false)
  assert.equal(again.state.parserFightId, 12)
  assert.equal(again.state.parserLogPath, snap.parserLogPath)
  assert.equal(again.state.whatsNewSeen, '1.1.0')
  assert.equal(again.state.parserSettings, undefined)
  assert.equal(again.state.currencies, undefined)
  const junk = sanitizeWorkspace({ v: 1, tab: 'parser', whatsNewSeen: 'nope' }, catalog)
  assert.equal(junk.state.tab, 'parser')
  assert.equal(junk.state.whatsNewSeen, '')
})

test('session restore keeps the last inventory import', () => {
  const raw = {
    tab: 'character',
    classes: ['Monk'],
    ownedOnly: true,
    importMeta: {
      source: 'Hero-Inventory.txt',
      rows: [
        {
          location_raw: 'Ear',
          container_kind: 'worn',
          parent_idx: null,
          depth: 0,
          socket_index: null,
          name: 'Left Ear',
          name_raw: 'Left Ear +2',
          tier: 2,
          id: '1',
          count: 1,
          slots: 10,
          line: 2,
        },
        {
          location_raw: 'Ear-Slot7',
          container_kind: 'worn',
          parent_idx: 0,
          depth: 1,
          socket_index: 7,
          socket_label: 'Slot7 (Focus?)',
          name: 'Focus Stone',
          name_raw: 'Focus Stone',
          tier: null,
          id: '2',
          count: 1,
          slots: 10,
          line: 3,
        },
        {
          location_raw: 'Chest',
          container_kind: 'worn',
          name_raw: 'Empty',
          name: 'Empty',
          parent_idx: null,
          depth: 0,
        },
      ],
      keyring: [{ ring: 'Equipment', name: 'Spare Cap', id: '9', count: 2 }],
      unknown_rows: [{
        line: 20,
        header: 'Dragon Hoard\tName\tID',
        header_line: 18,
        raw: 'Hoard\tMystery\t1',
      }],
      all_items: [{ name: 'Left Ear +2', base_name: 'Left Ear', location: 'Ear', in_catalog: false }],
      equipment: { PRIMARY: 'Left Ear' },
    },
  }
  const { restored, state } = sanitizeWorkspace(raw, catalog)
  assert.equal(restored, true)
  assert.equal(state.tab, 'character')
  assert.equal(state.ownedOnly, true)
  assert.equal(state.importMeta.rows.length, 3)
  assert.equal(state.importMeta.rows[0].tier, 2)
  assert.equal(state.importMeta.rows[1].parent_idx, 0)
  assert.equal(state.importMeta.rows[1].socket_label, 'Slot7 (Focus?)')
  assert.equal(state.importMeta.rows[2].name, 'Empty')
  assert.equal(state.importMeta.keyring[0].count, 2)
  assert.equal(state.importMeta.unknown_rows[0].raw, 'Hoard\tMystery\t1')
  assert.equal(state.importMeta.unknown_rows[0].header, 'Dragon Hoard\tName\tID')
  const snap = buildWorkspaceSnapshot(state, catalog)
  const again = sanitizeWorkspace(snap, catalog)
  assert.equal(again.restored, true)
  assert.equal(again.state.tab, 'character')
  assert.equal(again.state.importMeta.source, 'Hero-Inventory.txt')
  assert.equal(again.state.importMeta.rows[1].socket_label, 'Slot7 (Focus?)')
  assert.equal(again.state.importMeta.unknown_rows[0].raw, 'Hoard\tMystery\t1')
  assert.equal(again.state.ownedOnly, true)
})

test('dragon hoard rows, storage flags, search filters, and collapse flags survive a session', () => {
  const { state } = sanitizeWorkspace({
    v: 1,
    tab: 'character',
    searchType: '1H Slashing',
    searchClass: 'wizard',
    searchStat: 'INT',
    searchStatMin: '4',
    searchSort1: 'DMG',
    searchSort1Dir: 'desc',
    searchSort2: 'INT',
    searchSort2Dir: 'asc',
    searchSort3: '',
    characterCollapsed: { worn: true, 'section:dragonhorde': true, nope: false, '': true },
    importMeta: {
      source: 'Hoard.txt',
      rows: [{
        location_raw: 'Hoard 1',
        container_kind: 'dragonhorde',
        name_raw: 'Dark Plate Leggings +4',
        name: 'Dark Plate Leggings',
        tier: 4,
        wearable: true,
        container_item: false,
      }],
      keyring: [{ ring: 'Equipment', name: 'Stored Blade', id: '1', wearable: true, container_item: false }],
    },
  }, catalog)
  assert.equal(state.searchClass, 'Wizard')
  assert.equal(state.searchType, '1H Slashing')
  assert.equal(state.searchStat, 'INT')
  assert.equal(state.searchStatMin, '4')
  assert.equal(state.searchSort1, 'DMG')
  assert.equal(state.searchSort1Dir, 'desc')
  assert.equal(state.searchSort2Dir, 'asc')
  assert.deepEqual(state.characterCollapsed, { worn: true, 'section:dragonhorde': true })
  assert.equal(state.importMeta.rows[0].container_kind, 'dragonhorde')
  assert.equal(state.importMeta.rows[0].wearable, true)
  assert.equal(state.importMeta.keyring[0].wearable, true)
  const snap = buildWorkspaceSnapshot(state, catalog)
  const again = sanitizeWorkspace(snap, catalog)
  assert.equal(again.state.importMeta.rows[0].container_kind, 'dragonhorde')
  assert.equal(again.state.searchSort1, 'DMG')
})

test('old sessions with no import still load', () => {
  const { restored, state } = sanitizeWorkspace({
    v: 1,
    tab: 'bis',
    classes: ['Wizard'],
    race: 'Dark Elf',
    characterLevel: 42,
  }, catalog)
  assert.equal(restored, true)
  assert.equal(state.tab, 'bis')
  assert.equal(state.importMeta, null)
  assert.equal(state.ownedOnly, false)
  assert.deepEqual(state.classes, ['Wizard'])
  assert.equal(state.race, 'Dark Elf')
  assert.equal(state.characterLevel, 42)
})

test('an older import without a slot tree still loads', () => {
  const { restored, state } = sanitizeWorkspace({
    v: 1,
    tab: 'bags',
    importMeta: {
      source: 'Old-Inventory.txt',
      all_items: [{ name: 'Jade Mace', location: 'Primary', in_catalog: true }],
      equipment: { PRIMARY: 'Jade Mace' },
    },
  }, catalog)
  assert.equal(restored, true)
  assert.equal(state.tab, 'character')
  assert.equal(state.importMeta.source, 'Old-Inventory.txt')
  assert.equal(state.importMeta.all_items[0].name, 'Jade Mace')
  assert.deepEqual(state.importMeta.rows, [])
  assert.deepEqual(state.importMeta.keyring, [])
  assert.deepEqual(state.importMeta.unknown_rows, [])
  assert.deepEqual(state.importMeta.equipment, { PRIMARY: 'Jade Mace' })
})
