/**
 * EQ Legends BiS — Electron shell.
 * Spawns the FastAPI sidecar (eq-api.exe on Windows, or python -m on Linux),
 * opens a BrowserWindow to http://127.0.0.1:<port>, kills sidecar on quit.
 *
 * Updater: electron-updater → GitHub Releases
 * PolarOppositesHub/eq-legends-bis (see PACKAGING.md).
 */
const { app, BrowserWindow, dialog, shell, ipcMain, Menu, nativeTheme, Tray, nativeImage, screen, safeStorage } = require('electron');
const { spawn, spawnSync } = require('child_process');
const path = require('path');
const http = require('http');
const https = require('https');
const net = require('net');
const crypto = require('crypto');
const fs = require('fs');
const workspaceStore = require('./workspaceSessionStore');
const { InventoryFolderWatcher, isInventoryFileName } = require('./inventoryWatcher');
const overlayLib = require('./overlayWindows');
const eqclientIni = require('./eqclientIni');
const onedriveAuth = require('./onedriveAuth');
const googleDriveAuth = require('./googleDriveAuth');
const titleBar = require('./titleBar');
const { SYNC_INTERVAL_MS, planSync } = require('./syncSchedule');
const lifecycle = require('./appLifecycle');
const grokCli = require('./grokCli');

// Windows taskbar pins use this id. It must match build.appId: electron-builder
// derives the NSIS install GUID from it, and the installer stamps the same
// value onto shortcuts (WinShell::SetLnkAUMI). Do not change the id.
// Keep it a literal. electron-builder strips the "build" field from the
// package.json packed into app.asar, so reading it at startup would throw.
const APP_USER_MODEL_ID = 'com.eqlegends.bis';
if (process.platform === 'win32') {
  app.setAppUserModelId(APP_USER_MODEL_ID);
}

let mainWindow = null;
let tray = null;
let alertHost = null;
let overlayRaiseTimer = null;
let quitting = false;
const overlayWindows = new Map();

// One app per user. A second launch (double-clicked shortcut during a slow
// first start) would spawn a second sidecar on the same parser.db and start a
// second rebuild; one of them then fails with "database is locked".
const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    focusRunningInstance();
  });
}

function focusRunningInstance() {
  const plan = lifecycle.revealWindow(mainWindow);
  if (plan.action !== 'recreate') return;
  createWindow({ playIntro: false }).then(() => {
    if (apiReady && apiPort) showMainUi();
  }).catch((err) => mainLog('warn', 'second-instance', err && err.message ? err.message : err));
}

// Main-process + sidecar output also goes to <userData>/logs/main.log. Before
// 1.1.2 it only went to console, which a packaged Windows app throws away.
let mainLogStream = null;
function mainLog(level, ...parts) {
  const line = `${new Date().toISOString()} ${level} ${parts.map((p) => (typeof p === 'string' ? p : String(p))).join(' ')}\n`;
  try {
    if (!mainLogStream) {
      const dir = path.join(app.getPath('userData'), 'logs');
      fs.mkdirSync(dir, { recursive: true });
      const file = path.join(dir, 'main.log');
      try {
        if (fs.existsSync(file) && fs.statSync(file).size > 2_000_000) fs.renameSync(file, `${file}.1`);
      } catch (_) { /* rotation is best effort */ }
      mainLogStream = fs.createWriteStream(file, { flags: 'a' });
    }
    mainLogStream.write(line);
  } catch (_) { /* logging must never break the app */ }
}
let apiProc = null;
let apiPort = 0;
let instanceNonce = '';
const isDev = !app.isPackaged;
const SPLASH_FILE = 'polar-opposites-intro.mp4';
let splashDone = true;
let splashFadeTimer = null;
let apiReady = false;
let appUiShown = false;
let updaterStarted = false;
let syncDebounce = null;
let syncInterval = null;
let syncWatch = null;
let syncWatchPath = '';
let syncing = false;
let ignoreWatchUntil = 0;
let quitSyncStarted = false;

function resourcesRoot() {
  if (isDev) {
    // desktop/resources during local electron .
    return path.join(__dirname, 'resources');
  }
  return process.resourcesPath;
}

function findApiBinary() {
  const root = resourcesRoot();
  const winExe = path.join(root, 'eq-api', 'eq-api.exe');
  const winExeFlat = path.join(root, 'eq-api.exe');
  const nixBin = path.join(root, 'eq-api', 'eq-api');
  if (process.platform === 'win32') {
    if (fs.existsSync(winExe)) return { cmd: winExe, args: [] };
    if (fs.existsSync(winExeFlat)) return { cmd: winExeFlat, args: [] };
  }
  if (fs.existsSync(nixBin)) return { cmd: nixBin, args: [] };
  return null;
}

function findPythonSidecar() {
  // Dev / Linux smoke / packaged fallback without eq-api.exe
  const appRoot = path.resolve(__dirname, '..');
  const res = resourcesRoot();
  const venvPy = process.platform === 'win32'
    ? path.join(appRoot, '.venv', 'Scripts', 'python.exe')
    : path.join(appRoot, '.venv', 'bin', 'python');
  const py = fs.existsSync(venvPy) ? venvPy : (process.platform === 'win32' ? 'python' : 'python3');
  // Prefer the repo backend. desktop/resources/backend is a git snapshot
  // that can lag (the build copies backend/ in at pack time). A packaged app
  // has no repo tree, so this falls through to resources/backend.
  const candidates = [
    path.join(appRoot, 'backend', 'packaging', 'api_entry.py'),
    path.join(rootForScripts(), 'backend', 'packaging', 'api_entry.py'),
    path.join(res, 'backend', 'packaging', 'api_entry.py'),
  ];
  const script = candidates.find((c) => fs.existsSync(c)) || candidates[candidates.length - 1];
  return { cmd: py, args: [script, '--port', String(apiPort)] };
}

function rootForScripts() {
  return isDev ? path.resolve(__dirname, '..') : resourcesRoot();
}

function envForApi() {
  const root = resourcesRoot();
  const appRoot = isDev ? path.resolve(__dirname, '..') : root;
  // Prefer a decoded tree that actually exists (packaged / repo / nested).
  // Wrong EQ_DATA_ROOT → empty catalog → Item Search / inventory import look broken.
  const decodedCandidates = [
    path.join(root, 'data', 'decoded'),
    path.join(appRoot, 'data', 'decoded'),
    path.join(appRoot, 'desktop', 'resources', 'data', 'decoded'),
    path.join(root, 'desktop', 'resources', 'data', 'decoded'),
  ];
  // Prefer a decoded tree that includes the full mob index when present.
  const scoreDecoded = (p) => {
    try {
      if (!fs.existsSync(p)) return -1;
      const files = fs.readdirSync(p);
      if (!files.some((f) => f.endsWith('.json'))) return -1;
      let score = files.length;
      if (files.includes('eqlwiki_mob_names.json')) score += 10000;
      if (files.includes('eqlwiki_item_names.json')) score += 1000;
      if (files.includes('catalog.json')) score += 100;
      return score;
    } catch (_) {
      return -1;
    }
  };
  const ranked = decodedCandidates
    .map((p) => ({ p, score: scoreDecoded(p) }))
    .filter((x) => x.score >= 0)
    .sort((a, b) => b.score - a.score);
  const dataRoot = (ranked[0] && ranked[0].p) || decodedCandidates[0];
  const frontendDist = path.join(root, 'frontend', 'dist');
  const frontendDistDev = path.join(appRoot, 'frontend', 'dist');
  const ui = fs.existsSync(frontendDist) ? frontendDist : frontendDistDev;
  const legends = path.join(root, 'eq-legends');
  const legendsDev = path.resolve(appRoot, '..', 'eq-legends');
  const legendsRoot = fs.existsSync(path.join(legends, 'build_planner.py'))
    ? legends
    : (fs.existsSync(path.join(legendsDev, 'build_planner.py')) ? legendsDev : legends);

  // Dev has both the repo and a git snapshot under resources. The snapshot
  // can lag (older vendor, missing timeline.py). Prefer the repo. A packaged
  // app's appRoot is the resources tree the build just copied.
  const repoBackend = path.join(appRoot, 'backend', 'app');
  const mirrorBackend = path.join(root, 'backend', 'app');
  const backendRoot = fs.existsSync(repoBackend)
    ? appRoot
    : (fs.existsSync(mirrorBackend) ? root : appRoot);
  const pyPath = [
    backendRoot,
    path.join(backendRoot, 'backend'),
    legendsRoot,
    process.env.PYTHONPATH || '',
  ].filter(Boolean).join(path.delimiter);
  // Writable icon cache under userData (ASAR / Program Files are often read-only).
  const imagesDir = path.join(app.getPath('userData'), 'item-images');
  try {
    fs.mkdirSync(imagesDir, { recursive: true });
  } catch (_) {
    /* best-effort */
  }
  return {
    ...process.env,
    EQ_PACKAGED: '1',
    EQ_APP_ROOT: backendRoot,
    EQ_DATA_ROOT: dataRoot,
    EQ_LEGENDS_DATA: dataRoot,
    EQ_FRONTEND_DIST: ui,
    EQ_LEGENDS_ROOT: legendsRoot,
    EQ_XLSX_DIR: app.getPath('userData'),
    EQ_USER_DATA: app.getPath('userData'),
    EQ_IMAGES_DIR: imagesDir,
    EQ_API_PORT: String(apiPort),
    EQ_INSTANCE_NONCE: instanceNonce,
    PYTHONPATH: pyPath,
  };
}

function findFreePort() {
  // Always ask the OS for a free 127.0.0.1 port. Never assume 8765 is ours —
  // Cursor (or anything else) may already be answering on 8765/8000/5173.
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const addr = srv.address();
      const port = addr && addr.port;
      srv.close((err) => {
        if (err) reject(err);
        else resolve(port);
      });
    });
  });
}

function startApi() {
  const bundled = findApiBinary();
  const spec = bundled || findPythonSidecar();
  const env = envForApi();
  if (bundled) {
    spec.args = ['--port', String(apiPort)];
  }
  console.log('[eq] starting API:', spec.cmd, spec.args.join(' '));
  mainLog('info', '[eq] starting API:', spec.cmd, spec.args.join(' '), 'argv:', process.argv.slice(1).join(' '));
  apiProc = spawn(spec.cmd, spec.args, {
    env,
    cwd: path.dirname(spec.cmd),
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  apiProc.stdout.on('data', (d) => { const t = d.toString().trimEnd(); console.log('[api]', t); mainLog('api', t); });
  apiProc.stderr.on('data', (d) => { const t = d.toString().trimEnd(); console.error('[api]', t); mainLog('api', t); });
  if (apiProc.pid) writeSidecarRecord(apiProc.pid, apiPort);
  apiProc.on('exit', (code, signal) => {
    console.log('[eq] API exited', code, signal);
    mainLog('info', '[eq] API exited', code, signal);
    apiProc = null;
    if (!quitting) clearSidecarRecord();
  });
}

function sidecarPidPath() {
  return path.join(app.getPath('userData'), 'sidecar.pid');
}

function readSidecarRecord() {
  try {
    const raw = JSON.parse(fs.readFileSync(sidecarPidPath(), 'utf8'));
    return raw && typeof raw === 'object' ? raw : null;
  } catch (_) {
    return null;
  }
}

function writeSidecarRecord(pid, port) {
  try {
    const file = sidecarPidPath();
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify({ pid, port }), 'utf8');
  } catch (err) {
    mainLog('warn', 'sidecar pid', err && err.message ? err.message : err);
  }
}

function clearSidecarRecord() {
  try { fs.unlinkSync(sidecarPidPath()); } catch (_) { /* already gone */ }
}

function probeHealth(port) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/api/health`, (res) => {
      let body = '';
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(body || '{}');
          resolve(res.statusCode === 200 ? parsed : null);
        } catch (_) {
          resolve(null);
        }
      });
    });
    req.on('error', () => resolve(null));
    req.setTimeout(800, () => {
      req.destroy();
      resolve(null);
    });
  });
}

function killProcessTree(pid) {
  if (!pid || Number(pid) === process.pid) return;
  if (process.platform === 'win32') {
    try {
      spawnSync('taskkill', lifecycle.taskkillArgs(pid), { windowsHide: true, timeout: 8000 });
    } catch (err) {
      mainLog('warn', 'taskkill', err && err.message ? err.message : err);
    }
    return;
  }
  try {
    process.kill(Number(pid), 'SIGTERM');
  } catch (err) {
    mainLog('warn', 'kill', err && err.message ? err.message : err);
  }
}

function listenerPid(port) {
  const spec = process.platform === 'win32'
    ? { cmd: 'netstat', args: ['-ano', '-p', 'tcp'] }
    : { cmd: 'ss', args: ['-ltnp'] };
  try {
    const out = spawnSync(spec.cmd, spec.args, { encoding: 'utf8', timeout: 4000, windowsHide: true });
    return lifecycle.listenerPidFromListing(`${out.stdout || ''}\n${out.stderr || ''}`, port);
  } catch (_) {
    return null;
  }
}

async function reclaimRecord(recorded) {
  if (!recorded || !recorded.port) return false;
  const health = await probeHealth(recorded.port);
  if (!lifecycle.shouldReclaimSidecar(recorded, health)) return false;
  mainLog('info', 'stopping orphaned sidecar', recorded.pid, recorded.port);
  killProcessTree(recorded.pid);
  clearSidecarRecord();
  await new Promise((resolve) => setTimeout(resolve, 300));
  return true;
}

async function reclaimOrphanedSidecar() {
  const recorded = readSidecarRecord();
  if (!recorded) return;
  const killed = await reclaimRecord(recorded);
  if (!killed) clearSidecarRecord();
}

async function reclaimPort(port) {
  const health = await probeHealth(port);
  if (!health || health.ok !== true || typeof health.version !== 'string' || !health.version) return false;
  const recorded = readSidecarRecord();
  let pid = recorded && Number(recorded.port) === Number(port) ? recorded.pid : null;
  if (!pid) pid = listenerPid(port);
  return reclaimRecord({ pid, port });
}

function waitForHealth(timeoutMs = 60000) {
  const started = Date.now();
  const want = String(instanceNonce || '');
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(`http://127.0.0.1:${apiPort}/api/health`, (res) => {
        let body = '';
        res.on('data', (c) => (body += c));
        res.on('end', () => {
          if (res.statusCode !== 200) return retry();
          try {
            const j = JSON.parse(body || '{}');
            // Reject foreign listeners (e.g. Cursor port-forward of an old box API on 8765).
            if (want && j.instance !== want) {
              console.warn('[eq] health ok but instance mismatch — not our sidecar', j.instance);
              return retry();
            }
            if (!j.ok && j.ok !== undefined) return retry();
            return resolve(body);
          } catch (_) {
            // Non-JSON health from a foreign process — ignore
            return retry();
          }
        });
      });
      req.on('error', retry);
      req.setTimeout(2000, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        return reject(new Error('API health check timed out (our sidecar did not answer with matching instance nonce)'));
      }
      setTimeout(tick, 400);
    };
    tick();
  });
}

function stopApi() {
  const proc = apiProc;
  const pid = proc && proc.pid;
  apiProc = null;
  if (proc) {
    try { proc.kill('SIGTERM'); } catch (_) { /* Windows falls through to taskkill */ }
  }
  if (process.platform === 'win32' && pid) killProcessTree(pid);
  clearSidecarRecord();
}

function resolveSplashVideo() {
  // Packaged: extraResources → process.resourcesPath/splash/
  // Unpackaged: packaging/splash source, or a copy under desktop/resources/splash/
  const candidates = [
    path.join(resourcesRoot(), 'splash', SPLASH_FILE),
    path.join(__dirname, 'resources', 'splash', SPLASH_FILE),
    path.join(__dirname, '..', 'packaging', 'splash', SPLASH_FILE),
  ];
  return candidates.find((p) => fs.existsSync(p)) || null;
}

function showMainUi() {
  if (appUiShown || !splashDone || !apiReady) return;
  if (!mainWindow || mainWindow.isDestroyed()) return;
  appUiShown = true;
  // Origin is http://127.0.0.1:<port>/ and the port changes every launch, so
  // localStorage does not survive relaunch. Working session is userData instead.
  mainWindow.loadURL(`http://127.0.0.1:${apiPort}/`).catch((e) => {
    console.error('[eq] load UI', e);
  });
  setupUpdater();
  ensureTray();
  restoreOverlays();
  ensureAlertHost();
  ensureOverlayRaiseLoop();
  watchOverlayDisplays();
}

function requestSplashFade() {
  if (splashDone || splashFadeTimer) return;
  if (mainWindow && !mainWindow.isDestroyed()) {
    try {
      mainWindow.webContents.send('eq:splash-stop');
    } catch (_) {
      /* ignore */
    }
  }
  // HTML fades ~500ms then splashFinished; keep a fallback if the page never answers.
  splashFadeTimer = setTimeout(() => {
    splashFadeTimer = null;
    if (!splashDone) finishSplash();
  }, 900);
}

function finishSplash() {
  if (splashFadeTimer) {
    clearTimeout(splashFadeTimer);
    splashFadeTimer = null;
  }
  if (splashDone) {
    showMainUi();
    return;
  }
  splashDone = true;
  showMainUi();
}

function resolveAppIcon() {
  // Dragon-eye seal (Josh D). Packaged builds also embed this ICO in the exe;
  // BrowserWindow uses the file so the window/taskbar match in unpackaged/dev.
  const candidates = [
    path.join(__dirname, 'build', 'icon.ico'),
    path.join(__dirname, 'build', 'icon.png'),
    path.join(__dirname, '..', 'packaging', 'icons', 'eq-legends-bis.ico'),
    path.join(__dirname, '..', 'packaging', 'icons', 'eq-legends-bis.png'),
  ];
  return candidates.find((p) => fs.existsSync(p));
}

function broadcastWindowState() {
  if (!mainWindow || mainWindow.isDestroyed()) return { maximized: false };
  const payload = { maximized: !!mainWindow.isMaximized() };
  try { mainWindow.webContents.send('eq:window-state', payload); } catch (_) { /* ignore */ }
  return payload;
}

async function createWindow({ playIntro = false } = {}) {
  // Frameless window. The page draws the title bar in the app theme.
  // thickFrame stays on so Windows can snap and resize, without a second caption.
  try {
    nativeTheme.themeSource = 'dark';
  } catch (_) {
    /* older Electron */
  }
  const icon = resolveAppIcon();
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    ...(icon ? { icon } : {}),
    ...titleBar.mainWindowChrome(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      autoplayPolicy: 'no-user-gesture-required',
    },
  });
  mainWindow.setMenuBarVisibility(false);
  mainWindow.on('maximize', () => broadcastWindowState());
  mainWindow.on('unmaximize', () => broadcastWindowState());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
  // A file dropped on the window would otherwise navigate to file://.
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (String(url || '').startsWith('file:')) event.preventDefault();
  });
  const splashHtml = path.join(__dirname, 'splash.html');
  const videoPath = playIntro ? resolveSplashVideo() : null;
  if (videoPath) {
    splashDone = false;
    appUiShown = false;
    console.log('[eq] startup splash', videoPath);
    // Load HTML from the same directory as the MP4 so file:// can play it.
    const splashBesideVideo = path.join(path.dirname(videoPath), 'splash.html');
    const htmlPath = fs.existsSync(splashBesideVideo) ? splashBesideVideo : splashHtml;
    await mainWindow.loadFile(htmlPath);
    // Hard requirement: any key skips, even if the <video> element has focus.
    // Ask splash.html to fade out; do not load the planner until splashFinished.
    mainWindow.webContents.on('before-input-event', (event, input) => {
      if (splashDone) return;
      if (input.type === 'keyDown') {
        event.preventDefault();
        requestSplashFade();
      }
    });
  } else if (apiReady && apiPort) {
    splashDone = true;
    await mainWindow.loadURL(`http://127.0.0.1:${apiPort}/`);
    appUiShown = true;
  } else {
    splashDone = true;
    await mainWindow.loadFile(splashHtml, { query: { src: 'skip' } });
  }
  mainWindow.on('close', (event) => {
    if (quitting) return;
    // Default is quit. Hiding here used to leave the tray and the alert host
    // alive, so the process stayed in Task Manager and a second launch did nothing.
    if (lifecycle.shouldMinimizeToTray(readSettings())) {
      event.preventDefault();
      hideMainWindowToTray();
      return;
    }
    event.preventDefault();
    quitting = true;
    app.quit();
  });
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function isPortableBuild() {
  // electron-builder portable sets PORTABLE_EXECUTABLE_DIR; also detect exe name.
  if (process.env.PORTABLE_EXECUTABLE_DIR) return true;
  try {
    const exe = app.getPath('exe') || process.execPath || '';
    return /portable/i.test(path.basename(exe));
  } catch (_) {
    return false;
  }
}

function setupUpdater() {
  if (updaterStarted) return;
  updaterStarted = true;
  try {
    const { autoUpdater } = require('electron-updater');
    const owner = process.env.EQ_UPDATE_OWNER || process.env.GH_OWNER || 'PolarOppositesHub';
    const repo = process.env.EQ_UPDATE_REPO || process.env.GH_REPO || 'eq-legends-bis';
    // Download only after user clicks Update (then quitAndInstall).
    autoUpdater.autoDownload = false;
    autoUpdater.autoInstallOnAppQuit = true;
    autoUpdater.setFeedURL({ provider: 'github', owner, repo });

    autoUpdater.on('error', (err) => {
      console.log('[updater] error:', err && err.message);
      mainLog('warn', '[updater] error:', err && err.message);
    });

    autoUpdater.on('update-available', async (info) => {
      const portable = isPortableBuild();
      let detail = `Version ${info.version} is available from GitHub (PolarOppositesHub/eq-legends-bis).`;
      if (portable) {
        detail += '\n\nNote: Portable builds often cannot seamless-install via electron-updater. Prefer the NSIS/win-x64 installer for one-click updates, or re-download the new portable exe from the release.';
      }
      const { response } = await dialog.showMessageBox(mainWindow || undefined, {
        type: 'info',
        title: 'Update available',
        message: `Version ${info.version} is available.`,
        detail,
        buttons: ['Update', 'Later'],
        defaultId: 0,
        cancelId: 1,
        noLink: true,
      });
      if (response !== 0) return;
      try {
        autoUpdater.autoDownload = true;
        await autoUpdater.downloadUpdate();
      } catch (e) {
        const extra = portable
          ? '\n\nPortable builds may need a manual re-download of EQ-Legends-BiS-*-portable.exe from the GitHub release.'
          : '';
        dialog.showErrorBox('Update download failed', String(e && e.message ? e.message : e) + extra);
      }
    });

    autoUpdater.on('update-downloaded', async (info) => {
      const { response } = await dialog.showMessageBox(mainWindow || undefined, {
        type: 'info',
        title: 'Update ready',
        message: `Version ${(info && info.version) || ''} downloaded.`,
        detail: 'Restart now to install the update?',
        buttons: ['Restart & Install', 'Later'],
        defaultId: 0,
        cancelId: 1,
        noLink: true,
      });
      if (response === 0) {
        setImmediate(() => autoUpdater.quitAndInstall(false, true));
      }
    });

    if (app.isPackaged) {
      autoUpdater.checkForUpdates().catch((err) => {
        console.log('[updater] check failed:', err && err.message);
      });
    } else {
      console.log('[updater] skipped in unpackaged/dev mode');
    }
  } catch (e) {
    console.log('[updater] not available:', e && e.message);
  }
}


function saveOverlay(id, patch) {
  const current = readSettings();
  const overlays = { ...(current.overlays || {}) };
  overlays[id] = { ...(overlays[id] || {}), ...patch };
  writeSettings({ overlays });
}

function overlayDisplays() {
  try { return screen.getAllDisplays(); } catch (_) { return []; }
}

function overlayConfig(id, saved) {
  const appearance = overlayLib.appearanceFromRow(saved);
  return {
    id,
    open: saved.open !== false,
    locked: !!saved.locked,
    scope: saved.scope === 'zone' ? 'zone' : 'fight',
    character: saved.character || '',
    loadout: saved.loadout || '',
    ...appearance,
  };
}

function broadcastOverlayState() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const map = overlayLib.readOverlayMap(readSettings());
  const state = {};
  for (const id of overlayLib.OVERLAY_IDS) {
    const row = map[id] || {};
    const win = overlayWindows.get(id);
    state[id] = {
      ...overlayConfig(id, row),
      open: !!(win && !win.isDestroyed()),
    };
  }
  try { mainWindow.webContents.send('eq:overlay-state', state); } catch (_) { /* ignore */ }
}

function sendOverlayConfig(win, id, saved) {
  if (!win || win.isDestroyed()) return;
  try { win.webContents.send('eq:overlay-config', overlayConfig(id, saved)); } catch (_) { /* ignore */ }
}

function lockedFor(id) {
  return !!((overlayLib.readOverlayMap(readSettings())[id] || {}).locked);
}

function focusedWindowId() {
  try {
    const focused = BrowserWindow.getFocusedWindow();
    if (!focused || focused.isDestroyed()) return '';
    return String(focused.id);
  } catch (_) {
    return '';
  }
}

function windowById(id) {
  if (!id) return null;
  try {
    return BrowserWindow.getAllWindows().find((candidate) => String(candidate.id) === String(id)) || null;
  } catch (_) {
    return null;
  }
}

let restoringOverlayFocus = false;

function raiseOverlay(win, locked, reason) {
  if (!win || win.isDestroyed() || restoringOverlayFocus) return;
  const plan = overlayLib.overlayRaisePlan(reason || 'raise', !!locked);
  if (plan.hide || plan.close) return;
  const beforeId = focusedWindowId();
  if (plan.unfocusableDuringRaise) {
    try { win.setFocusable(false); } catch (_) { /* ignore */ }
  }
  try {
    win.setAlwaysOnTop(true, plan.level);
  } catch (_) {
    try { win.setAlwaysOnTop(true, plan.fallbackLevel); } catch (_) { /* ignore */ }
  }
  try {
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: !!plan.visibleOnFullScreen });
  } catch (_) { /* ignore */ }
  if (plan.setFocusable || plan.unfocusableDuringRaise) {
    try { win.setFocusable(plan.focusable); } catch (_) { /* ignore */ }
  }
  try { win.setSkipTaskbar(true); } catch (_) { /* ignore */ }
  // Never focus, show, or moveTop the overlay from a raise. The timer used to
  // steal the text box in the main window about once a second.
  if (plan.focus) {
    try { win.focus(); } catch (_) { /* ignore */ }
  }
  if (plan.show) {
    try { win.show(); } catch (_) { /* ignore */ }
  }
  const decision = overlayLib.focusAfterRaise({
    beforeId,
    afterId: focusedWindowId(),
    overlayId: String(win.id),
  });
  if (!decision.restoreFocusId) return;
  const target = windowById(decision.restoreFocusId);
  if (!target || target.isDestroyed() || target === win) return;
  restoringOverlayFocus = true;
  try { target.focus(); } catch (_) { /* ignore */ }
  restoringOverlayFocus = false;
}

function raiseAllOverlays() {
  for (const [id, win] of overlayWindows) raiseOverlay(win, lockedFor(id), 'interval');
}

function ensureOverlayRaiseLoop() {
  if (overlayRaiseTimer) return;
  overlayRaiseTimer = setInterval(raiseAllOverlays, overlayLib.RAISE_INTERVAL_MS);
}

function watchOverlayDisplays() {
  if (watchOverlayDisplays.done) return;
  watchOverlayDisplays.done = true;
  try {
    screen.on('display-added', raiseAllOverlays);
    screen.on('display-removed', raiseAllOverlays);
    screen.on('display-metrics-changed', raiseAllOverlays);
  } catch (_) { /* ignore */ }
}

function applyOverlayLock(win, locked) {
  const call = overlayLib.lockWindowCalls(locked);
  try {
    if (call.ignoreMouse.forward) win.setIgnoreMouseEvents(true, { forward: true });
    else win.setIgnoreMouseEvents(false);
  } catch (_) { /* ignore */ }
  try { win.setMovable(call.movable); } catch (_) { /* ignore */ }
  try { win.setResizable(call.resizable); } catch (_) { /* ignore */ }
  raiseOverlay(win, locked);
}

function setOverlayLocked(id, locked) {
  const saved = { ...(overlayLib.readOverlayMap(readSettings())[id] || {}), locked: !!locked };
  saveOverlay(id, { locked: !!locked });
  const win = overlayWindows.get(id);
  if (win && !win.isDestroyed()) {
    applyOverlayLock(win, !!locked);
    sendOverlayConfig(win, id, saved);
  }
}

function openOverlayWindow(id, patch = {}) {
  if (!overlayLib.OVERLAY_IDS.includes(id) || !apiPort) return null;
  const saved = { ...(overlayLib.readOverlayMap(readSettings())[id] || {}), ...patch, open: true };
  const appearance = overlayLib.appearanceFromRow(saved);
  const size = overlayLib.defaultSize(id);
  const placed = overlayLib.keepOnScreen({
    x: saved.x,
    y: saved.y,
    width: saved.width || size.width,
    height: saved.height || size.height,
  }, overlayDisplays());
  const record = {
    open: true,
    locked: !!saved.locked,
    x: saved.x == null ? placed.x : placed.x,
    y: saved.y == null ? placed.y : placed.y,
    width: placed.width,
    height: placed.height,
    opacity: appearance.backgroundOpacity,
    scope: saved.scope === 'zone' ? 'zone' : 'fight',
    character: saved.character || '',
    loadout: saved.loadout || '',
    ...appearance,
  };
  if (saved.x == null) delete record.x;
  if (saved.y == null) delete record.y;
  saveOverlay(id, record);
  const stored = { ...saved, ...record };
  let win = overlayWindows.get(id);
  if (win && !win.isDestroyed()) {
    applyOverlayLock(win, !!stored.locked);
    win.show();
    raiseOverlay(win, !!stored.locked);
    sendOverlayConfig(win, id, stored);
    broadcastOverlayState();
    return win;
  }
  const options = overlayLib.overlayBrowserOptions(id, stored, overlayDisplays());
  win = new BrowserWindow({
    ...options,
    title: 'EQ Legends BiS',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  overlayWindows.set(id, win);
  applyOverlayLock(win, !!stored.locked);
  const keepUp = (reason) => {
    if (restoringOverlayFocus || !win || win.isDestroyed()) return;
    const plan = overlayLib.overlayRaisePlan(reason, lockedFor(id));
    if (plan.hide || plan.close || plan.focus || plan.show) return;
    raiseOverlay(win, lockedFor(id), reason);
  };
  win.on('blur', () => keepUp('blur'));
  win.on('show', () => keepUp('show'));
  if (stored.x != null && stored.y != null && (options.x !== stored.x || options.y !== stored.y || options.width !== stored.width || options.height !== stored.height)) {
    saveOverlay(id, { x: options.x, y: options.y, width: options.width, height: options.height });
  }
  const route = overlayLib.overlayRoute(id, stored.character, stored.scope, stored.loadout);
  win.loadURL(`http://127.0.0.1:${apiPort}${route}`).catch(() => {});
  win.webContents.on('did-finish-load', () => {
    const latest = overlayLib.readOverlayMap(readSettings())[id] || stored;
    sendOverlayConfig(win, id, latest);
  });
  const persist = () => {
    if (!win || win.isDestroyed()) return;
    const current = overlayLib.readOverlayMap(readSettings())[id] || {};
    if (current.locked) return;
    const bounds = win.getBounds();
    let area = null;
    try { area = screen.getDisplayMatching(bounds).workArea; } catch (_) { /* ignore */ }
    const snapped = overlayLib.snapBounds(bounds, area);
    if (snapped && (snapped.x !== bounds.x || snapped.y !== bounds.y)) win.setBounds(snapped);
    saveOverlay(id, {
      x: snapped.x,
      y: snapped.y,
      width: snapped.width,
      height: snapped.height,
      open: true,
    });
    broadcastOverlayState();
  };
  win.on('moved', persist);
  win.on('resized', persist);
  win.on('closed', () => {
    overlayWindows.delete(id);
    if (!quitting) saveOverlay(id, overlayLib.closedOverlayPatch());
    broadcastOverlayState();
  });
  broadcastOverlayState();
  return win;
}

function closeOverlayWindow(id) {
  const win = overlayWindows.get(id);
  if (win && !win.isDestroyed()) {
    win.close();
    return;
  }
  saveOverlay(id, overlayLib.closedOverlayPatch());
  broadcastOverlayState();
}

function restoreOverlays() {
  const map = overlayLib.readOverlayMap(readSettings());
  for (const id of overlayLib.OVERLAY_IDS) {
    if (map[id] && map[id].open) openOverlayWindow(id);
  }
}

function ensureAlertHost() {
  if (!apiPort) return null;
  if (alertHost && !alertHost.isDestroyed()) return alertHost;
  alertHost = new BrowserWindow({
    show: false,
    skipTaskbar: true,
    focusable: false,
    frame: false,
    width: 320,
    height: 180,
    title: 'EQ Legends BiS alerts',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  alertHost.loadURL(`http://127.0.0.1:${apiPort}/?alertHost=1`).catch(() => {});
  alertHost.on('blur', () => { /* sound host stays open when the game is focused */ });
  return alertHost;
}

function openFromTray() {
  const plan = lifecycle.revealWindow(mainWindow);
  if (plan.action !== 'recreate') return;
  createWindow({ playIntro: false }).then(() => {
    if (apiReady && apiPort) showMainUi();
  }).catch((err) => mainLog('warn', 'tray open', err && err.message ? err.message : err));
}

function hideMainWindowToTray() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.hide();
  ensureTray();
  showTrayNoticeOnce();
}

function showTrayNoticeOnce() {
  if (!lifecycle.shouldShowTrayNotice(readSettings())) return;
  const title = lifecycle.TRAY_NOTICE_TITLE;
  const content = lifecycle.TRAY_NOTICE;
  let shown = false;
  try {
    if (tray && typeof tray.displayBalloon === 'function') {
      tray.displayBalloon({ title, content, iconType: 'info' });
      shown = true;
    }
  } catch (err) {
    mainLog('warn', 'tray notice', err && err.message ? err.message : err);
  }
  if (!shown) {
    try {
      const { Notification } = require('electron');
      if (Notification.isSupported()) {
        new Notification({ title, body: content }).show();
        shown = true;
      }
    } catch (err) {
      mainLog('warn', 'tray notice', err && err.message ? err.message : err);
    }
  }
  if (shown) writeSettings({ trayNoticeShown: true });
}

function destroyTray() {
  if (!tray) return;
  try { tray.destroy(); } catch (_) { /* already gone */ }
  tray = null;
}

function closeAuxiliaryWindows() {
  for (const win of [...overlayWindows.values()]) {
    if (win && !win.isDestroyed()) {
      try { win.destroy(); } catch (_) { /* already gone */ }
    }
  }
  overlayWindows.clear();
  if (alertHost && !alertHost.isDestroyed()) {
    try { alertHost.destroy(); } catch (_) { /* already gone */ }
  }
  alertHost = null;
}

function quitCleanup() {
  if (overlayRaiseTimer) {
    clearInterval(overlayRaiseTimer);
    overlayRaiseTimer = null;
  }
  try { grokCli.stopAll(spawn); } catch (_) { /* cli helpers stay optional */ }
  stopInventoryWatcher();
  stopSyncSchedule();
  closeAuxiliaryWindows();
  destroyTray();
}

function ensureTray() {
  if (tray) return;
  try {
    const iconPath = resolveAppIcon();
    let image = iconPath ? nativeImage.createFromPath(iconPath) : null;
    if (!image || image.isEmpty()) {
      image = nativeImage.createFromDataURL('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==');
    }
    tray = new Tray(image);
    tray.setToolTip('EQ Legends BiS');
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: 'Open EQ Legends BiS', click: () => openFromTray() },
      { label: 'DPS meter', click: () => openOverlayWindow('dps') },
      { label: 'Heal meter', click: () => openOverlayWindow('heal') },
      { label: 'Alert banner', click: () => openOverlayWindow('alert') },
      {
        label: 'Unlock meters',
        click: () => {
          for (const id of overlayLib.OVERLAY_IDS) setOverlayLocked(id, false);
          broadcastOverlayState();
        },
      },
      { label: 'Quit', click: () => { quitting = true; app.quit(); } },
    ]));
    tray.on('double-click', () => openFromTray());
  } catch (err) {
    console.log('[eq] tray unavailable', err && err.message);
    tray = null;
  }
}

ipcMain.handle('eq:overlay-open', async (_evt, args) => {
  const id = args && args.id;
  ensureTray();
  const patch = {};
  if (args && typeof args.character === 'string') patch.character = args.character;
  if (args && typeof args.loadout === 'string') patch.loadout = args.loadout;
  if (args && (args.scope === 'zone' || args.scope === 'fight')) patch.scope = args.scope;
  if (args && typeof args.locked === 'boolean') patch.locked = args.locked;
  if (args && args.opacity != null) patch.backgroundOpacity = args.opacity;
  openOverlayWindow(id, patch);
  return { ok: true };
});

ipcMain.handle('eq:overlay-close', async (_evt, args) => {
  const id = args && args.id;
  if (overlayLib.OVERLAY_IDS.includes(id)) closeOverlayWindow(id);
  return { ok: true };
});

ipcMain.handle('eq:overlay-lock', async (_evt, args) => {
  const locked = !!(args && args.locked);
  const only = args && args.id;
  const ids = overlayLib.OVERLAY_IDS.includes(only) ? [only] : overlayLib.OVERLAY_IDS;
  for (const id of ids) setOverlayLocked(id, locked);
  broadcastOverlayState();
  return { ok: true };
});

ipcMain.handle('eq:overlay-opacity', async (_evt, args) => {
  const opacity = args && args.opacity;
  const only = args && args.id;
  const ids = overlayLib.OVERLAY_IDS.includes(only) ? [only] : overlayLib.OVERLAY_IDS;
  for (const id of ids) {
    const saved = overlayLib.readOverlayMap(readSettings())[id] || {};
    const appearance = overlayLib.appearanceFromRow({ ...saved, backgroundOpacity: opacity, opacity });
    saveOverlay(id, { ...appearance, opacity: appearance.backgroundOpacity });
    const win = overlayWindows.get(id);
    sendOverlayConfig(win, id, { ...saved, ...appearance });
  }
  broadcastOverlayState();
  return { ok: true };
});

ipcMain.handle('eq:overlay-appearance', async (_evt, args) => {
  const id = args && args.id;
  if (!overlayLib.OVERLAY_IDS.includes(id)) return { ok: false };
  const saved = overlayLib.readOverlayMap(readSettings())[id] || {};
  const appearance = args && args.reset
    ? { ...overlayLib.APPEARANCE_DEFAULTS }
    : overlayLib.appearanceFromRow({ ...saved, ...args });
  saveOverlay(id, { ...appearance, opacity: appearance.backgroundOpacity });
  const win = overlayWindows.get(id);
  sendOverlayConfig(win, id, { ...saved, ...appearance });
  broadcastOverlayState();
  return { ok: true, appearance };
});

ipcMain.handle('eq:video-mode', async (_evt, args) => {
  const settings = readSettings();
  const folder = (args && args.folder) || settings.eqInstallFolder || '';
  return eqclientIni.readEqClientVideoMode(folder);
});

ipcMain.handle('eq:overlay-state', async () => {
  const map = overlayLib.readOverlayMap(readSettings());
  const state = {};
  for (const id of overlayLib.OVERLAY_IDS) {
    const row = map[id] || overlayLib.appearanceFromRow({});
    const win = overlayWindows.get(id);
    state[id] = {
      ...overlayConfig(id, row),
      open: !!(win && !win.isDestroyed()),
    };
  }
  return state;
});

ipcMain.handle('eq:pick-sound-file', async () => {
  const result = await dialog.showOpenDialog({
    title: 'Choose a .wav or .mp3',
    properties: ['openFile'],
    filters: [{ name: 'Sound', extensions: ['wav', 'mp3'] }],
  });
  if (result.canceled || !result.filePaths || !result.filePaths[0]) return { ok: false, canceled: true };
  return { ok: true, path: result.filePaths[0] };
});

ipcMain.handle('eq:read-sound-file', async (_evt, filePath) => {
  const target = String(filePath || '');
  if (!/\.(wav|mp3)$/i.test(target)) return null;
  try {
    const st = fs.statSync(target);
    if (!st.isFile() || st.size > 8 * 1024 * 1024) return null;
    const mime = /\.mp3$/i.test(target) ? 'audio/mpeg' : 'audio/wav';
    return `data:${mime};base64,${fs.readFileSync(target).toString('base64')}`;
  } catch (_) {
    return null;
  }
});

ipcMain.on('eq:splash-finished', () => {
  finishSplash();
});

ipcMain.handle('eq:app-info', async () => ({
  version: app.getVersion(),
  packaged: app.isPackaged,
  apiPort,
}));

ipcMain.handle('eq:ask-grok', async (_evt, args) => {
  const prompt = String(args && args.prompt || '').slice(0, 24000);
  try {
    return await grokCli.askWithLocalGrok(prompt);
  } catch (_) {
    return { mode: 'browser', reason: 'failed' };
  }
});

ipcMain.handle('eq:grok-status', async () => {
  try {
    return await grokCli.detectGrok({ spawn, env: process.env });
  } catch (_) {
    return { state: 'unknown', detail: 'Sign-in check failed. The copy button still works.' };
  }
});

ipcMain.handle('eq:grok-install', async (_evt, args) => {
  const started = grokCli.startInstall({
    spawn,
    confirmed: !!(args && args.confirmed === true),
    platform: process.platform,
    env: process.env,
  });
  if (!started || !started.started || !started.child) {
    return {
      ok: false,
      started: false,
      command: started && started.command,
      detail: (started && started.detail) || 'Installer was not run. Confirm it first.',
    };
  }
  const child = started.child;
  const outcome = await new Promise((resolve) => {
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };
    const timer = setTimeout(() => {
      grokCli.killChild(child, spawn);
      finish({ ok: false, detail: 'Installer was stopped after 120 seconds.' });
    }, grokCli.INSTALL_TIMEOUT_MS || 120000);
    child.on('close', (code) => {
      finish({
        ok: code === 0,
        detail: code === 0 ? 'Installer finished. Check again.' : `Installer exited ${code}.`,
      });
    });
    child.on('error', () => {
      finish({ ok: false, detail: 'The installer could not be started.' });
    });
  });
  return { ok: outcome.ok, started: true, command: started.command, detail: outcome.detail };
});

ipcMain.handle('eq:grok-login', async () => {
  try {
    const started = grokCli.startLogin({ spawn, env: process.env });
    return { ok: true, detail: started.detail };
  } catch (_) {
    return { ok: false, detail: 'Grok sign-in could not be started.' };
  }
});

const grokRuns = new Map();

ipcMain.handle('eq:grok-ask', async (evt, args) => {
  const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const handle = grokCli.startHeadless({
    spawn,
    env: process.env,
    prompt: String((args && args.prompt) || '').slice(0, 24000),
    timeoutMs: args && args.timeoutMs,
  });
  grokRuns.set(id, handle);
  handle.done.then((result) => {
    grokRuns.delete(id);
    try {
      if (evt.sender && !evt.sender.isDestroyed()) evt.sender.send('eq:grok-result', { id, ...(result || {}) });
    } catch (_) { /* window gone */ }
  });
  return { id, started: true };
});

ipcMain.handle('eq:grok-cancel', async (_evt, id) => {
  const handle = grokRuns.get(String(id || ''));
  if (handle && typeof handle.cancel === 'function') handle.cancel();
  return { ok: true };
});

ipcMain.handle('eq:quit', async () => {
  quitting = true;
  app.quit();
  return { ok: true };
});

function settingsPath() {
  return path.join(app.getPath('userData'), 'settings.json');
}

function readSettings() {
  try {
    const p = settingsPath();
    if (!fs.existsSync(p)) return {};
    const raw = JSON.parse(fs.readFileSync(p, 'utf8'));
    return raw && typeof raw === 'object' ? raw : {};
  } catch (_) {
    return {};
  }
}

function writeSettings(patch) {
  const cur = readSettings();
  const next = { ...cur, ...(patch || {}) };
  if (patch && Object.prototype.hasOwnProperty.call(patch, 'xButton')) {
    next.xButton = patch.xButton === 'tray' ? 'tray' : 'quit';
    next.closeToTray = next.xButton === 'tray';
  } else if (patch && Object.prototype.hasOwnProperty.call(patch, 'closeToTray')) {
    next.closeToTray = patch.closeToTray === true;
    next.xButton = next.closeToTray ? 'tray' : 'quit';
  }
  const p = settingsPath();
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(next, null, 2), 'utf8');
  return next;
}

function defaultEqInstallCandidates() {
  if (process.platform !== 'win32') return [];
  const pub = process.env.PUBLIC || 'C:\\Users\\Public';
  return [
    path.join(pub, 'Daybreak Game Company', 'Installed Games', 'EverQuest Legends'),
    path.join(pub, 'Daybreak Game Company', 'Installed Games', 'EverQuest'),
  ];
}

function listInventoryCandidates(folder) {
  const root = path.resolve(folder || '');
  if (!root || !fs.existsSync(root) || !fs.statSync(root).isDirectory()) {
    return [];
  }
  const out = [];
  let entries = [];
  try {
    entries = fs.readdirSync(root, { withFileTypes: true });
  } catch (_) {
    return [];
  }
  for (const ent of entries) {
    if (!ent.isFile()) continue;
    if (!isInventoryFileName(ent.name)) continue;
    const full = path.join(root, ent.name);
    try {
      const st = fs.statSync(full);
      // Skip tiny/empty and huge binary-looking dumps
      if (st.size < 32 || st.size > 25 * 1024 * 1024) continue;
      out.push({
        path: full,
        name: ent.name,
        mtimeMs: st.mtimeMs,
        size: st.size,
      });
    } catch (_) {
      /* skip unreadable */
    }
  }
  out.sort((a, b) => b.mtimeMs - a.mtimeMs);
  return out;
}

function pathIsInside(parent, child) {
  const p = path.resolve(parent);
  const c = path.resolve(child);
  const rel = path.relative(p, c);
  return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel));
}

function settingsView(s) {
  const src = s || {};
  const xButton = lifecycle.xButtonAction(src);
  return {
    ok: true,
    closeToTray: xButton === 'tray',
    xButton,
    eqInstallFolder: src.eqInstallFolder || '',
    lastInventoryPath: src.lastInventoryPath || '',
    lastInventoryName: src.lastInventoryName || '',
    lastInventoryMtimeMs: src.lastInventoryMtimeMs || null,
    lastInventoryImportedAt: src.lastInventoryImportedAt || null,
    autoImportInventory: src.autoImportInventory !== false,
    inventoryCharacterName: src.inventoryCharacterName || '',
  };
}

ipcMain.handle('eq:settings-get', async () => settingsView(readSettings()));

ipcMain.handle('eq:settings-set', async (_evt, patch) => settingsView(writeSettings(patch || {})));

function userDataDir() {
  return app.getPath('userData');
}

ipcMain.handle('eq:workspace-get', async () => {
  try {
    return { ok: true, workspace: workspaceStore.readWorkspaceSession(userDataDir()) };
  } catch (e) {
    return { ok: false, workspace: null, message: String(e && e.message ? e.message : e) };
  }
});

ipcMain.handle('eq:workspace-set', async (_evt, session) => {
  try {
    workspaceStore.writeWorkspaceSession(userDataDir(), session);
    return { ok: true };
  } catch (e) {
    return { ok: false, message: String(e && e.message ? e.message : e) };
  }
});

ipcMain.handle('eq:workspace-clear', async () => {
  try {
    workspaceStore.clearWorkspaceSession(userDataDir());
    return { ok: true };
  } catch (e) {
    return { ok: false, message: String(e && e.message ? e.message : e) };
  }
});

ipcMain.handle('eq:pick-eq-install-folder', async () => {
  const settings = readSettings();
  const candidates = defaultEqInstallCandidates().filter((p) => {
    try { return fs.existsSync(p); } catch (_) { return false; }
  });
  const defaultPath = settings.eqInstallFolder || candidates[0] || undefined;
  const result = await dialog.showOpenDialog(mainWindow || undefined, {
    title: 'Select EverQuest Legends install folder',
    message: 'Choose the game install root (where *-Inventory.txt is written).',
    properties: ['openDirectory'],
    defaultPath,
  });
  if (result.canceled || !result.filePaths || !result.filePaths[0]) {
    return { ok: false, canceled: true, message: 'Folder selection canceled.' };
  }
  const folder = result.filePaths[0];
  writeSettings({ eqInstallFolder: folder });
  return { ok: true, path: folder, eqInstallFolder: folder };
});

ipcMain.handle('eq:find-latest-inventory', async (_evt, folderArg) => {
  const settings = readSettings();
  const folder = (folderArg || settings.eqInstallFolder || '').trim();
  if (!folder) {
    return { ok: false, message: 'Set the EQ install folder first.' };
  }
  if (!fs.existsSync(folder) || !fs.statSync(folder).isDirectory()) {
    return { ok: false, message: `EQ install folder not found:\n${folder}` };
  }
  const hits = listInventoryCandidates(folder);
  if (!hits.length) {
    return {
      ok: false,
      folder,
      message: (
        `No *-Inventory.txt found in:\n${folder}\n\n` +
        'In game, type /outputfile inventory — the file appears in the install root (not Logs\\).'
      ),
    };
  }
  const best = hits[0];
  writeSettings({
    eqInstallFolder: folder,
    lastInventoryPath: best.path,
    lastInventoryName: best.name,
    lastInventoryMtimeMs: best.mtimeMs,
  });
  return {
    ok: true,
    folder,
    path: best.path,
    name: best.name,
    mtimeMs: best.mtimeMs,
    size: best.size,
    count: hits.length,
  };
});

let inventoryWatcher = null;

function stopInventoryWatcher() {
  if (!inventoryWatcher) return;
  try {
    inventoryWatcher.stop();
  } catch (err) {
    mainLog('inventory', 'stop failed', err && err.message ? err.message : err);
  }
  inventoryWatcher = null;
}

function startInventoryWatcher(folder) {
  stopInventoryWatcher();
  const root = path.resolve(String(folder || ''));
  if (!root || !fs.existsSync(root) || !fs.statSync(root).isDirectory()) {
    return { ok: false, watching: false, message: 'Set the EQ install folder first.' };
  }
  inventoryWatcher = new InventoryFolderWatcher({
    folder: root,
    onReady(info) {
      const win = mainWindow;
      if (!win || win.isDestroyed()) return;
      mainLog('inventory', 'stable', info.name, String(info.size));
      win.webContents.send('eq:inventory-ready', {
        path: info.path,
        name: info.name,
        size: info.size,
        mtimeMs: info.mtimeMs,
      });
    },
  });
  inventoryWatcher.start();
  mainLog('inventory', 'watching', root);
  return { ok: true, watching: true, folder: root };
}

ipcMain.handle('eq:list-inventory-files', async (_evt, folderArg) => {
  const settings = readSettings();
  const folder = String((folderArg || settings.eqInstallFolder || '')).trim();
  if (!folder) return { ok: false, files: [], message: 'Set the EQ install folder first.' };
  if (!fs.existsSync(folder) || !fs.statSync(folder).isDirectory()) {
    return { ok: false, files: [], folder, message: `EQ install folder not found:\n${folder}` };
  }
  return { ok: true, folder, files: listInventoryCandidates(folder) };
});

ipcMain.handle('eq:watch-inventory', async (_evt, args) => {
  const enabled = !args || args.enabled !== false;
  const settings = readSettings();
  const folder = String((args && args.folder) || settings.eqInstallFolder || '').trim();
  if (!enabled) {
    stopInventoryWatcher();
    return { ok: true, watching: false };
  }
  return startInventoryWatcher(folder);
});

ipcMain.handle('eq:read-inventory-file', async (_evt, filePath) => {
  const settings = readSettings();
  const folder = (settings.eqInstallFolder || '').trim();
  const target = path.resolve(String(filePath || ''));
  if (!target || !fs.existsSync(target) || !fs.statSync(target).isFile()) {
    return { ok: false, message: 'Inventory file not found.' };
  }
  if (!isInventoryFileName(path.basename(target))) {
    return { ok: false, message: 'That file does not look like an Inventory.txt dump.' };
  }
  if (folder && !pathIsInside(folder, target)) {
    return { ok: false, message: 'Refusing to read a file outside the configured EQ install folder.' };
  }
  // Extra guard when folder not set yet: only allow known last path
  if (!folder && settings.lastInventoryPath && path.resolve(settings.lastInventoryPath) !== target) {
    return { ok: false, message: 'Set the EQ install folder before reading inventory files.' };
  }
  try {
    const buf = fs.readFileSync(target);
    // Reject obvious binaries
    if (buf.length >= 2 && buf[0] === 0x4d && buf[1] === 0x5a) {
      return { ok: false, message: 'That looks like a binary (.exe), not Inventory.txt.' };
    }
    const text = buf.toString('utf8');
    if (!/Location\tName/i.test(text) && !/\t/.test(text.split(/\r?\n/, 5).join('\n'))) {
      return {
        ok: false,
        message: 'File does not look like an Inventory.txt TSV (missing Location/Name header).',
      };
    }
    return {
      ok: true,
      path: target,
      name: path.basename(target),
      text,
    };
  } catch (e) {
    return { ok: false, message: String(e && e.message ? e.message : e) };
  }
});

ipcMain.handle('eq:check-updates', async () => {
  const owner = process.env.EQ_UPDATE_OWNER || process.env.GH_OWNER || 'PolarOppositesHub';
  const repo = process.env.EQ_UPDATE_REPO || process.env.GH_REPO || 'eq-legends-bis';
  const feed = process.env.EQ_UPDATE_URL || '';
  try {
    const { autoUpdater } = require('electron-updater');
    autoUpdater.autoDownload = false;
    if (feed) autoUpdater.setFeedURL({ provider: 'generic', url: feed });
    else autoUpdater.setFeedURL({ provider: 'github', owner, repo });
    const result = await autoUpdater.checkForUpdates();
    return {
      ok: true,
      configured: true,
      portable: isPortableBuild(),
      updateInfo: result && result.updateInfo,
      message: 'Checked for updates (Update/Later dialog handles download + quitAndInstall).',
    };
  } catch (e) {
    return { ok: false, configured: true, portable: isPortableBuild(), message: String(e && e.message ? e.message : e) };
  }
});

function requestJson(url, options = {}) {
  return new Promise((resolve, reject) => {
    const lib = String(url).startsWith('https:') ? https : http;
    const req = lib.request(url, {
      method: options.method || 'GET',
      headers: options.headers || {},
    }, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => {
        const raw = Buffer.concat(chunks).toString('utf8');
        try {
          resolve(raw ? JSON.parse(raw) : {});
        } catch (err) {
          reject(err);
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(30000, () => req.destroy(new Error('OneDrive request timed out')));
    if (options.body) req.write(options.body);
    req.end();
  });
}

function postJson(pathname, body, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    if (!apiPort) {
      reject(new Error('API is not running'));
      return;
    }
    const data = Buffer.from(JSON.stringify(body || {}));
    const req = http.request({
      hostname: '127.0.0.1',
      port: apiPort,
      path: pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': data.length,
      },
    }, (res) => {
      let raw = '';
      res.on('data', (chunk) => { raw += chunk; });
      res.on('end', () => {
        let parsed = {};
        try {
          parsed = raw ? JSON.parse(raw) : {};
        } catch (_) {
          if (res.statusCode >= 400) {
            reject(new Error(raw || `Sync failed (${res.statusCode}).`));
            return;
          }
          resolve({});
          return;
        }
        if (res.statusCode >= 400) {
          const detail = parsed && (parsed.detail || parsed.error);
          reject(new Error(typeof detail === 'string' ? detail : `Sync failed (${res.statusCode}).`));
          return;
        }
        resolve(parsed);
      });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('sync request timed out')));
    req.write(data);
    req.end();
  });
}

function getJson(pathname, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    if (!apiPort) {
      reject(new Error('API is not running'));
      return;
    }
    const req = http.get(`http://127.0.0.1:${apiPort}${pathname}`, (res) => {
      let raw = '';
      res.on('data', (chunk) => { raw += chunk; });
      res.on('end', () => {
        try { resolve(JSON.parse(raw || '{}')); } catch (_) { resolve({}); }
      });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('sync status timed out')));
  });
}

function googleDriveDeps() {
  const tokenPath = path.join(app.getPath('userData'), 'sync', 'google-drive-refresh.bin');
  return {
    openExternal: (url) => shell.openExternal(url),
    request: requestJson,
    http,
    randomBytes: (n) => crypto.randomBytes(n),
    timeoutMs: 180000,
    tokenPath,
    isEncryptionAvailable: () => {
      try { return safeStorage.isEncryptionAvailable(); } catch (_) { return false; }
    },
    encryptString: (value) => safeStorage.encryptString(value),
    decryptString: (buf) => safeStorage.decryptString(buf),
    writeFile: (file, buf) => {
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, buf);
    },
    readFile: (file) => fs.readFileSync(file),
    exists: (file) => fs.existsSync(file),
    removeFile: (file) => {
      try { fs.unlinkSync(file); } catch (_) { /* already gone */ }
    },
    log: (message) => mainLog('warn', 'google-drive', message),
  };
}

function oneDriveDeps() {
  const tokenPath = path.join(app.getPath('userData'), 'sync', 'onedrive-refresh.bin');
  return {
    openExternal: (url) => shell.openExternal(url),
    request: requestJson,
    http,
    randomBytes: (n) => crypto.randomBytes(n),
    timeoutMs: 180000,
    tokenPath,
    isEncryptionAvailable: () => {
      try { return safeStorage.isEncryptionAvailable(); } catch (_) { return false; }
    },
    encryptString: (value) => safeStorage.encryptString(value),
    decryptString: (buf) => safeStorage.decryptString(buf),
    writeFile: (file, buf) => {
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, buf);
    },
    readFile: (file) => fs.readFileSync(file),
    exists: (file) => fs.existsSync(file),
    removeFile: (file) => {
      try { fs.unlinkSync(file); } catch (_) { /* already gone */ }
    },
    log: (message) => mainLog('warn', 'onedrive', message),
  };
}

function stopSyncWatch() {
  if (syncWatch) {
    try { syncWatch.close(); } catch (_) { /* ignore */ }
    syncWatch = null;
  }
  syncWatchPath = '';
}

function startSyncWatch(folder, force = false) {
  const root = path.join(String(folder || ''), 'EQLegendsBiS-sync');
  const target = folder && fs.existsSync(root) ? root : String(folder || '');
  if (!target || !fs.existsSync(target)) return;
  if (!force && target === syncWatchPath && syncWatch) return;
  stopSyncWatch();
  const watchers = [];
  const onEvent = () => {
    if (syncing || Date.now() < ignoreWatchUntil) return;
    scheduleSync('watch');
  };
  const arm = (dir, recursive) => {
    try {
      const watcher = fs.watch(dir, { persistent: false, recursive }, onEvent);
      watcher.on('error', () => {});
      watchers.push(watcher);
      return true;
    } catch (_) {
      return false;
    }
  };
  if (!arm(target, true)) {
    const walk = (dir) => {
      if (!arm(dir, false)) return;
      let entries = [];
      try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch (_) { return; }
      for (const entry of entries) {
        if (entry.isDirectory()) walk(path.join(dir, entry.name));
      }
    };
    walk(target);
  }
  if (!watchers.length) return;
  syncWatch = {
    close() {
      for (const watcher of watchers) {
        try { watcher.close(); } catch (_) { /* ignore */ }
      }
    },
  };
  syncWatchPath = target;
}

async function refreshSyncWatch() {
  try {
    const status = await getJson('/api/sync/status');
    if (status && status.provider === 'folder' && status.folder) startSyncWatch(status.folder, true);
    else stopSyncWatch();
  } catch (_) { /* sidecar may be stopping */ }
}

function stopSyncSchedule() {
  if (syncDebounce) {
    clearTimeout(syncDebounce);
    syncDebounce = null;
  }
  if (syncInterval) {
    clearInterval(syncInterval);
    syncInterval = null;
  }
  stopSyncWatch();
}

async function cloudAuth(provider) {
  if (provider === 'google') {
    return {
      refresh: () => googleDriveAuth.refreshAccessToken(googleDriveDeps()),
      postToken: (body) => postJson('/api/sync/google', body),
      expired: googleDriveAuth.AUTH_EXPIRED_TEXT,
    };
  }
  return {
    refresh: () => onedriveAuth.refreshAccessToken(oneDriveDeps()),
    postToken: (body) => postJson('/api/sync/onedrive', body),
    expired: lifecycle.AUTH_EXPIRED_TEXT,
  };
}

async function runSync(reason) {
  if (!apiPort || !apiReady) return { ok: false, status: 'error', error: 'Sync is not ready.' };
  syncing = true;
  try {
    let provider = '';
    try {
      const current = await getJson('/api/sync/status');
      provider = current && current.provider ? current.provider : '';
    } catch (_) { /* the sync call reports its own error */ }
    const auth = await cloudAuth(provider);
    const status = await lifecycle.syncWithAuthRefresh({
      sync: () => postJson('/api/sync/now', {}, reason === 'quit' ? 4000 : 30000),
      refresh: auth.refresh,
      postToken: auth.postToken,
    });
    ignoreWatchUntil = Date.now() + 2500;
    if (reason !== 'quit') await refreshSyncWatch();
    if (status && status.auth_expired === true && status.ok !== true && status.status !== 'ok') {
      return {
        ok: false,
        status: 'error',
        error: status.error || auth.expired,
        auth_expired: true,
      };
    }
    return status && typeof status === 'object' ? status : { ok: false, status: 'error', error: 'Sync did not return a status.' };
  } catch (err) {
    const message = String(err && err.message ? err.message : err);
    mainLog('warn', 'sync', reason, message);
    return { ok: false, status: 'error', error: message };
  } finally {
    syncing = false;
  }
}

function scheduleSync(reason) {
  const plan = planSync(reason);
  if (!plan.run || reason === 'interval') return;
  if (syncDebounce) clearTimeout(syncDebounce);
  syncDebounce = setTimeout(() => {
    syncDebounce = null;
    runSync(reason);
  }, plan.delayMs);
}

async function restoreGoogleSession() {
  const deps = googleDriveDeps();
  if (!deps.exists(deps.tokenPath)) return;
  const refreshed = await googleDriveAuth.refreshAccessToken(deps);
  const outcome = lifecycle.classifyRefresh(refreshed);
  if (outcome.action === 'post') {
    await postJson('/api/sync/google', {
      access_token: refreshed.access_token,
      account: refreshed.account || '',
    });
  } else if (outcome.error) {
    await postJson('/api/sync/google/notice', {
      error: outcome.error,
      auth_expired: outcome.auth_expired,
      reauth: outcome.reauth,
    });
  }
}

async function restoreOneDriveSession(provider) {
  const deps = oneDriveDeps();
  if (!deps.exists(deps.tokenPath)) return;
  const refreshed = await onedriveAuth.refreshAccessToken(deps);
  const outcome = lifecycle.classifyRefresh(refreshed);
  if (outcome.action === 'post') {
    await postJson('/api/sync/onedrive', {
      access_token: refreshed.access_token,
      account: refreshed.account || '',
    });
  } else if (outcome.error && provider !== 'folder') {
    await postJson('/api/sync/onedrive/notice', {
      error: outcome.error,
      auth_expired: outcome.auth_expired,
      reauth: outcome.reauth,
    });
  }
}

async function startSyncSchedule() {
  try {
    let provider = '';
    try {
      const status = await getJson('/api/sync/status');
      provider = status && status.provider ? status.provider : '';
    } catch (_) { /* sidecar may still be starting */ }
    if (provider === 'google') await restoreGoogleSession();
    else await restoreOneDriveSession(provider);
  } catch (err) {
    mainLog('warn', 'cloud refresh', err && err.message ? err.message : err);
  }
  scheduleSync('launch');
  syncInterval = setInterval(() => {
    runSync('interval');
  }, SYNC_INTERVAL_MS);
  refreshSyncWatch();
}

ipcMain.handle('eq:sync-touch', async () => {
  scheduleSync('change');
  return { ok: true };
});

ipcMain.handle('eq:sync-now', async () => runSync('now'));

ipcMain.handle('eq:pick-sync-folder', async () => {
  const result = await dialog.showOpenDialog({
    title: 'Choose a sync folder',
    properties: ['openDirectory', 'createDirectory'],
  });
  if (result.canceled || !result.filePaths || !result.filePaths[0]) return { ok: false, canceled: true };
  const folder = result.filePaths[0];
  startSyncWatch(folder);
  return { ok: true, folder };
});

ipcMain.handle('eq:onedrive-sign-in', async () => {
  const result = await onedriveAuth.signInOneDrive(oneDriveDeps());
  if (!result.ok) return { ok: false, error: result.error || 'OneDrive sign-in failed.' };
  try {
    await postJson('/api/sync/onedrive', {
      access_token: result.access_token,
      account: result.account || '',
    });
    scheduleSync('now');
  } catch (err) {
    return { ok: false, error: String(err && err.message ? err.message : err) };
  }
  return { ok: true, account: result.account || '' };
});

ipcMain.handle('eq:onedrive-sign-out', async () => {
  onedriveAuth.forgetRefreshToken(oneDriveDeps());
  try {
    await postJson('/api/sync/onedrive/sign-out', {});
  } catch (_) { /* the settings page posts sign-out as well */ }
  return { ok: true };
});

ipcMain.handle('eq:google-drive-sign-in', async () => {
  const result = await googleDriveAuth.signInGoogleDrive(googleDriveDeps());
  if (!result.ok) return { ok: false, error: result.error || 'Google Drive sign-in failed.' };
  try {
    await postJson('/api/sync/google', {
      access_token: result.access_token,
      account: result.account || '',
    });
    scheduleSync('now');
  } catch (err) {
    return { ok: false, error: String(err && err.message ? err.message : err) };
  }
  return { ok: true, account: result.account || '' };
});

ipcMain.handle('eq:google-drive-sign-out', async () => {
  googleDriveAuth.forgetRefreshToken(googleDriveDeps());
  try {
    await postJson('/api/sync/google/sign-out', {});
  } catch (_) { /* the settings page posts sign-out as well */ }
  return { ok: true };
});

ipcMain.handle('eq:window-state', () => {
  if (!mainWindow || mainWindow.isDestroyed()) return { maximized: false };
  return { maximized: !!mainWindow.isMaximized() };
});

ipcMain.handle('eq:window-minimize', () => {
  if (titleBar.windowControlCall('minimize', false) === 'minimize' && mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.minimize();
  }
  return { ok: true };
});

ipcMain.handle('eq:window-toggle-maximize', () => {
  if (!mainWindow || mainWindow.isDestroyed()) return { ok: false, maximized: false };
  const call = titleBar.windowControlCall('toggle-maximize', mainWindow.isMaximized());
  if (call === 'unmaximize') mainWindow.unmaximize();
  else if (call === 'maximize') mainWindow.maximize();
  return { ok: true, ...broadcastWindowState() };
});

ipcMain.handle('eq:window-close', () => {
  // Same path as the caption X: quit, or minimize to tray when that setting is on.
  if (titleBar.windowControlCall('close', false) === 'close' && mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.close();
  }
  return { ok: true };
});

app.whenReady().then(async () => {
  if (!gotSingleInstanceLock) return;
  // Drop the stock File/Edit/View menu — in-app Quit + window chrome still exit.
  Menu.setApplicationMenu(null);
  instanceNonce = crypto.randomBytes(16).toString('hex');
  try {
    await reclaimOrphanedSidecar();
  } catch (err) {
    mainLog('warn', 'orphan sidecar', err && err.message ? err.message : err);
  }
  if (process.env.EQ_API_PORT) {
    apiPort = Number(process.env.EQ_API_PORT) || 0;
  }
  if (apiPort) {
    try {
      await reclaimPort(apiPort);
    } catch (err) {
      mainLog('warn', 'orphan port', err && err.message ? err.message : err);
    }
  }
  if (!apiPort) {
    try {
      apiPort = await findFreePort();
    } catch (e) {
      dialog.showErrorBox('EQ Legends BiS', `Could not reserve a local API port.\n\n${e.message || e}`);
      app.quit();
      return;
    }
  }
  console.log('[eq] API port', apiPort, 'instance', instanceNonce.slice(0, 8) + '…');
  startApi();
  // Show the intro immediately so skip/end can overlap sidecar startup.
  try {
    await createWindow({ playIntro: true });
  } catch (e) {
    dialog.showErrorBox('EQ Legends BiS', `Could not open the app window.\n\n${e.message || e}`);
    app.quit();
    return;
  }
  try {
    await waitForHealth();
    apiReady = true;
    showMainUi();
    startSyncSchedule().catch((err) => mainLog('warn', 'sync schedule', err && err.message ? err.message : err));
  } catch (e) {
    dialog.showErrorBox(
      'EQ Legends BiS',
      `Could not start the local API on port ${apiPort}.\n\n${e.message}\n\nIf this is a Windows build, ensure eq-api.exe was produced by scripts/build-windows.ps1.`
    );
    app.quit();
    return;
  }
});

app.on('window-all-closed', () => {
  stopInventoryWatcher();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', (event) => {
  quitting = true;
  quitCleanup();
  if (quitSyncStarted || !apiReady || !apiPort) {
    stopApi();
    return;
  }
  event.preventDefault();
  quitSyncStarted = true;
  runSync('quit').finally(() => {
    stopApi();
    app.quit();
  });
});

app.on('will-quit', () => {
  quitting = true;
  quitCleanup();
  stopApi();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow({ playIntro: false });
});
