const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const test = require('node:test');
const {
  DEFAULT_SETTLE_MS,
  InventoryFolderWatcher,
  isInventoryFileName,
} = require('./inventoryWatcher');

function waitFor(predicate, timeoutMs) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      let value;
      try {
        value = predicate();
      } catch (err) {
        reject(err);
        return;
      }
      if (value) {
        resolve(value);
        return;
      }
      if (Date.now() - start > timeoutMs) {
        reject(new Error('timed out waiting for the inventory watcher'));
        return;
      }
      setTimeout(tick, 20);
    };
    tick();
  });
}

function fakeClock() {
  const timers = [];
  return {
    timers,
    setTimeout(fn, ms, now) {
      const timer = { fn, at: now() + ms, cleared: false, fired: false };
      timers.push(timer);
      return timer;
    },
    clearTimeout(timer) {
      if (timer) timer.cleared = true;
    },
    runDue(now) {
      let progressed = true;
      while (progressed) {
        progressed = false;
        for (const timer of timers) {
          if (timer.cleared || timer.fired || timer.at > now) continue;
          timer.fired = true;
          progressed = true;
          timer.fn();
        }
      }
    },
  };
}

test('inventory file names are the EQ dump, not inventory.exe', () => {
  assert.equal(isInventoryFileName('Dranak_freeport-Inventory.txt'), true);
  assert.equal(isInventoryFileName('Inventory.txt'), true);
  assert.equal(isInventoryFileName('notes.txt'), false);
  assert.equal(isInventoryFileName('inventory.exe'), false);
  assert.equal(DEFAULT_SETTLE_MS, 400);
});

test('two chunks 200ms apart are read once, and the half-written file is never read', () => {
  const clock = fakeClock();
  let now = 0;
  const filePath = path.join('eq-root', 'Dranak_freeport-Inventory.txt');
  const sizes = new Map([[filePath, 10]]);
  const reads = [];
  const delivered = [];
  let onEvent = null;
  const watcher = new InventoryFolderWatcher({
    folder: 'eq-root',
    settleMs: 400,
    fsWatch(_folder, _opts, cb) {
      onEvent = cb;
      return { close() {}, on() {} };
    },
    exists: (target) => sizes.has(target),
    stat: (target) => {
      if (!sizes.has(target)) {
        const err = new Error('ENOENT');
        err.code = 'ENOENT';
        throw err;
      }
      return { isFile: () => true, size: sizes.get(target), mtimeMs: now };
    },
    readFile: (target) => {
      const size = sizes.get(target);
      reads.push(size);
      return 'x'.repeat(size);
    },
    setTimeout: (fn, ms) => clock.setTimeout(fn, ms, () => now),
    clearTimeout: clock.clearTimeout,
    onReady: (info) => delivered.push(info),
  });
  watcher.start();

  onEvent('change', 'Dranak_freeport-Inventory.txt');
  now = 200;
  sizes.set(filePath, 25);
  onEvent('change', 'Dranak_freeport-Inventory.txt');

  clock.runDue(200);
  clock.runDue(599);
  assert.deepEqual(reads, []);
  assert.deepEqual(delivered, []);

  clock.runDue(600);
  assert.deepEqual(reads, [25]);
  assert.equal(delivered.length, 1);
  assert.equal(delivered[0].size, 25);
  assert.equal(delivered[0].name, 'Dranak_freeport-Inventory.txt');
  watcher.stop();
});

test('a size change with no second event still does not read the partial file', () => {
  const clock = fakeClock();
  let now = 0;
  const filePath = path.join('eq-root', 'Hero-Inventory.txt');
  const sizes = new Map([[filePath, 12]]);
  const reads = [];
  let onEvent = null;
  const watcher = new InventoryFolderWatcher({
    folder: 'eq-root',
    settleMs: 400,
    fsWatch(_folder, _opts, cb) {
      onEvent = cb;
      return { close() {}, on() {} };
    },
    exists: (target) => sizes.has(target),
    stat: (target) => ({ isFile: () => true, size: sizes.get(target), mtimeMs: now }),
    readFile: () => {
      const size = sizes.get(filePath);
      reads.push(size);
      return 'y'.repeat(size);
    },
    setTimeout: (fn, ms) => clock.setTimeout(fn, ms, () => now),
    clearTimeout: clock.clearTimeout,
    onReady: () => {},
  });
  watcher.start();
  onEvent('change', 'Hero-Inventory.txt');
  now = 200;
  sizes.set(filePath, 40);
  clock.runDue(400);
  assert.deepEqual(reads, []);
  clock.runDue(800);
  assert.deepEqual(reads, [40]);
  watcher.stop();
});

test('delete-and-recreate re-imports once and re-arms the watch', () => {
  const clock = fakeClock();
  let now = 0;
  const filePath = path.join('eq-root', 'Dranak_freeport-Inventory.txt');
  const sizes = new Map([[filePath, 20]]);
  const delivered = [];
  const watches = [];
  let onEvent = null;
  const watcher = new InventoryFolderWatcher({
    folder: 'eq-root',
    settleMs: 400,
    fsWatch(_folder, _opts, cb) {
      const handle = {
        closed: false,
        close() { this.closed = true; },
        on() {},
      };
      watches.push(handle);
      onEvent = cb;
      return handle;
    },
    exists: (target) => sizes.has(target),
    stat: (target) => {
      if (!sizes.has(target)) {
        const err = new Error('ENOENT');
        throw err;
      }
      return { isFile: () => true, size: sizes.get(target), mtimeMs: now };
    },
    readFile: (target) => 'x'.repeat(sizes.get(target) || 0),
    setTimeout: (fn, ms) => clock.setTimeout(fn, ms, () => now),
    clearTimeout: clock.clearTimeout,
    onReady: (info) => delivered.push(info.size),
  });
  watcher.start();
  assert.equal(watches.length, 1);

  onEvent('add', 'Dranak_freeport-Inventory.txt');
  clock.runDue(400);
  assert.deepEqual(delivered, [20]);

  now = 500;
  sizes.delete(filePath);
  onEvent('rename', 'Dranak_freeport-Inventory.txt');
  assert.equal(watches.length, 2);
  assert.equal(watches[0].closed, true);
  onEvent('rename', 'Dranak_freeport-Inventory.txt');
  assert.equal(watches.length, 2);

  now = 700;
  sizes.set(filePath, 33);
  onEvent('add', 'Dranak_freeport-Inventory.txt');
  clock.runDue(700);
  assert.deepEqual(delivered, [20]);
  clock.runDue(1100);
  assert.deepEqual(delivered, [20, 33]);
  clock.runDue(2000);
  assert.deepEqual(delivered, [20, 33]);
  watcher.stop();
});

test('an in-place rewrite fires once, and a non-inventory file is ignored', () => {
  const clock = fakeClock();
  let now = 1000;
  const filePath = path.join('eq-root', 'Dranak_freeport-Inventory.txt');
  const sizes = new Map([[filePath, 18]]);
  let body = 'a'.repeat(18);
  const delivered = [];
  let onEvent = null;
  const watcher = new InventoryFolderWatcher({
    folder: 'eq-root',
    settleMs: 400,
    fsWatch(_folder, _opts, cb) {
      onEvent = cb;
      return { close() {}, on() {} };
    },
    exists: (target) => sizes.has(target),
    stat: (target) => ({ isFile: () => true, size: sizes.get(target), mtimeMs: now }),
    readFile: () => body,
    setTimeout: (fn, ms) => clock.setTimeout(fn, ms, () => now),
    clearTimeout: clock.clearTimeout,
    onReady: () => delivered.push(body.slice(0, 1)),
  });
  watcher.start();
  onEvent('change', 'notes.txt');
  onEvent('change', 'inventory.exe');
  clock.runDue(2000);
  assert.deepEqual(delivered, []);

  onEvent('change', 'Dranak_freeport-Inventory.txt');
  clock.runDue(1400);
  assert.deepEqual(delivered, ['a']);

  now = 2000;
  sizes.set(filePath, 18);
  body = 'b'.repeat(18);
  onEvent('change', 'Dranak_freeport-Inventory.txt');
  clock.runDue(2399);
  assert.deepEqual(delivered, ['a']);
  clock.runDue(2400);
  assert.deepEqual(delivered, ['a', 'b']);
  watcher.stop();
});

test('watcher fires once per rewrite on disk, including delete+create and a 200ms partial write', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'eq-inventory-watch-'));
  const name = 'Dranak_freeport-Inventory.txt';
  const full = path.join(dir, name);
  const header = 'Location\tName\tID\tCount\tSlots\n';
  const partial = `${header}Head\tHalf Written`;
  const complete = `${partial} Cap\t10\t1\t10\n`;
  const replacement = `${header}Head\tFinished Cap\t10\t1\t10\n`;
  const reads = [];
  const delivered = [];
  const watcher = new InventoryFolderWatcher({
    folder: dir,
    settleMs: DEFAULT_SETTLE_MS,
    readFile: (target) => {
      const text = fs.readFileSync(target, 'utf8');
      reads.push(text);
      return text;
    },
    onReady: (info) => delivered.push(info),
  });
  watcher.start();
  try {
    fs.writeFileSync(full, partial);
    await new Promise((resolve) => setTimeout(resolve, 200));
    fs.appendFileSync(full, ' Cap\t10\t1\t10\n');
    await waitFor(() => delivered.length >= 1, 3000);
    await new Promise((resolve) => setTimeout(resolve, 500));
    assert.equal(delivered.length, 1);
    assert.equal(reads.includes(partial), false);
    assert.ok(reads.every((text) => text === complete));
    assert.equal(delivered[0].name, name);

    fs.unlinkSync(full);
    await new Promise((resolve) => setTimeout(resolve, 30));
    fs.writeFileSync(full, replacement);
    await waitFor(() => delivered.length >= 2, 3000);
    await new Promise((resolve) => setTimeout(resolve, 500));
    assert.equal(delivered.length, 2);
    assert.equal(delivered[1].name, name);
    assert.ok(reads.includes(replacement));
    assert.equal(reads.includes(partial), false);
  } finally {
    watcher.stop();
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('desktop shell starts the folder watcher and notifies the renderer', () => {
  const main = fs.readFileSync(path.join(__dirname, 'main.js'), 'utf8');
  const preload = fs.readFileSync(path.join(__dirname, 'preload.js'), 'utf8');
  const pkg = require('./package.json');
  assert.match(main, /InventoryFolderWatcher/);
  assert.match(main, /eq:inventory-ready/);
  assert.match(main, /eq:watch-inventory/);
  assert.match(main, /eq:list-inventory-files/);
  assert.match(preload, /watchInventory/);
  assert.match(preload, /onInventoryReady/);
  assert.match(preload, /listInventoryFiles/);
  assert.ok(pkg.build.files.includes('inventoryWatcher.js'));
});
