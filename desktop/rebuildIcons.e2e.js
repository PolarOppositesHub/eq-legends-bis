/**
 * Electron check for the 1.1.1 first-launch freeze (1.1.2).
 *
 * A parser database that still needs a rebuild is opened with the replay
 * paused on db.lock (EQ_PARSER_REBUILD_GATE). The Parser tab is restored, so
 * it does what it did on 2026-09-26: subscribe to fight events and refetch.
 * On 1.1.1 those refetches wait on the lock and fill Chromium's six
 * connections, and Best in Slot icons never arrive. On 1.1.2 the reads
 * return immediately and the icons load while the rebuild is still paused.
 *
 * Run: npm run test:e2e   (from desktop/; needs a built frontend/dist)
 */
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { _electron: electron } = require('playwright-core');

const ROOT = path.resolve(__dirname, '..');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function pythonBin() {
  return process.platform === 'win32' ? 'python' : 'python3';
}

function seedFixture(userData, eqRoot) {
  const script = path.join(__dirname, 'e2e_seed_parser_db.py');
  const run = spawnSync(pythonBin(), [script, userData, eqRoot], {
    cwd: ROOT,
    encoding: 'utf8',
    timeout: 120000,
  });
  if (run.status !== 0) {
    throw new Error(`seed failed (${run.status}): ${run.stderr || run.stdout}`);
  }
  return JSON.parse(run.stdout.trim().split('\n').pop());
}

async function iconState(page) {
  return page.evaluate(() => {
    const imgs = Array.from(document.images).filter((img) => /\/api\/item-image/.test(img.src));
    const pending = imgs
      .filter((img) => !(img.complete && img.naturalWidth > 0))
      .slice(0, 5)
      .map((img) => img.src);
    return {
      count: imgs.length,
      ok: imgs.filter((img) => img.complete && img.naturalWidth > 0).length,
      pending,
      tab: document.querySelector('[data-active-tab]')?.getAttribute('data-active-tab') || '',
    };
  });
}

async function dismissWhatsNew(page) {
  const open = await page.locator('[data-testid="whats-new-dialog"]').count();
  if (!open) return;
  await page.locator('[data-testid="whats-new-dialog"] button', { hasText: 'Got it' }).click();
}

async function clickTab(page, label) {
  await page.evaluate((name) => {
    const button = Array.from(document.querySelectorAll('nav button, button')).find(
      (node) => node.textContent.trim() === name,
    );
    if (!button) throw new Error(`no tab button: ${name}`);
    button.click();
  }, label);
}

async function readConfig(page) {
  const base = new URL(page.url()).origin;
  const res = await fetch(`${base}/api/parser/config`);
  if (!res.ok) throw new Error(`config ${res.status}`);
  return res.json();
}

async function main() {
  const dist = path.join(ROOT, 'frontend', 'dist', 'index.html');
  assert.ok(fs.existsSync(dist), 'frontend/dist is missing; run npm run build in frontend/ first');

  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'eq-rebuild-e2e-'));
  const eqRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'eq-rebuild-logs-'));
  const gate = path.join(userData, 'rebuild.gate');
  fs.writeFileSync(gate, 'hold\n');
  const seeded = seedFixture(userData, eqRoot);
  console.log('seeded', JSON.stringify(seeded));

  const electronPath = require('electron');
  let app;
  const hardStop = setTimeout(() => {
    console.error('electron e2e exceeded 3 minutes');
    process.exit(1);
  }, 180000);
  try {
    app = await electron.launch({
      executablePath: electronPath,
      cwd: __dirname,
      timeout: 90000,
      args: [`--user-data-dir=${userData}`, '--no-sandbox', path.join(__dirname, 'main.js')],
      env: {
        ...process.env,
        EQ_PARSER_REBUILD_GATE: gate,
        ELECTRON_DISABLE_SANDBOX: '1',
      },
    });
    const page = await app.firstWindow();
    await page.waitForSelector('[data-active-tab="parser"]', { timeout: 90000 });
    await dismissWhatsNew(page);
    await page.waitForSelector('[data-testid="parser-upgrade"]', { timeout: 30000 });

    // Give a 1.1.1 Parser tab time to refetch on fight events and fill the
    // six connections. 1.1.2 drops those events, so this wait is idle there.
    await sleep(3000);
    const before = await readConfig(page);
    assert.equal(before.upgrading, true, 'rebuild should still be paused before icons are checked');

    const iconDeadline = Date.now() + 5000;
    await clickTab(page, 'Best in Slot');
    let icons = { count: 0, ok: 0, pending: [], tab: '' };
    while (Date.now() < iconDeadline) {
      icons = await iconState(page);
      if (icons.tab === 'bis' && icons.count >= 8 && icons.ok === icons.count) break;
      await sleep(100);
    }
    console.log('icons', JSON.stringify(icons));
    assert.equal(icons.tab, 'bis', 'Best in Slot tab did not open');
    assert.ok(
      icons.count >= 8 && icons.ok === icons.count,
      `item icons did not all load within 5s while the rebuild was paused `
      + `(${icons.ok}/${icons.count} ready, sample ${icons.pending.join(' ')})`,
    );
    const during = await readConfig(page);
    assert.equal(during.upgrading, true, 'rebuild finished before the icon check');
    assert.equal(during.schema_version, null);

    fs.writeFileSync(gate, 'release\n');
    let after = null;
    const rebuildDeadline = Date.now() + 45000;
    while (Date.now() < rebuildDeadline) {
      after = await readConfig(page);
      if (after.upgrading === false && after.schema_version != null) break;
      await sleep(250);
    }
    assert.equal(after && after.upgrading, false, `rebuild did not finish: ${JSON.stringify(after)}`);
    assert.ok(after.schema_version != null, 'schema version was not stored');

    await clickTab(page, 'Parser');
    await page.waitForSelector('[data-testid="parser-fights"] tbody tr', { timeout: 20000 });
    const fights = await page.locator('[data-testid="parser-fights"] tbody tr').count();
    assert.ok(fights >= 1, 'Parser tab did not list the rebuilt fights');
    console.log(`rebuild finished, parser rows ${fights}`);
  } finally {
    clearTimeout(hardStop);
    try {
      fs.writeFileSync(gate, 'release\n');
    } catch (_) { /* temp dir may already be gone */ }
    if (app) await app.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
