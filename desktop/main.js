/**
 * EQ Legends BiS — Electron shell.
 * Spawns the FastAPI sidecar (eq-api.exe on Windows, or python -m on Linux),
 * opens a BrowserWindow to http://127.0.0.1:<port>, kills sidecar on quit.
 *
 * Updater: electron-updater → GitHub Releases
 * PolarOppositesHub/eq-legends-bis (see PACKAGING.md).
 */
const { app, BrowserWindow, dialog, shell, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const fs = require('fs');

let mainWindow = null;
let apiProc = null;
let apiPort = 8765;
const isDev = !app.isPackaged;

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
  const candidates = [
    path.join(res, 'backend', 'packaging', 'api_entry.py'),
    path.join(rootForScripts(), 'backend', 'packaging', 'api_entry.py'),
    path.join(appRoot, 'backend', 'packaging', 'api_entry.py'),
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

  const backendRoot = fs.existsSync(path.join(root, 'backend', 'app'))
    ? root
    : appRoot;
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
    EQ_IMAGES_DIR: imagesDir,
    EQ_API_PORT: String(apiPort),
    PYTHONPATH: pyPath,
  };
}

function startApi() {
  const bundled = findApiBinary();
  const spec = bundled || findPythonSidecar();
  const env = envForApi();
  if (bundled) {
    spec.args = ['--port', String(apiPort)];
  }
  console.log('[eq] starting API:', spec.cmd, spec.args.join(' '));
  apiProc = spawn(spec.cmd, spec.args, {
    env,
    cwd: path.dirname(spec.cmd),
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  apiProc.stdout.on('data', (d) => console.log('[api]', d.toString().trimEnd()));
  apiProc.stderr.on('data', (d) => console.error('[api]', d.toString().trimEnd()));
  apiProc.on('exit', (code, signal) => {
    console.log('[eq] API exited', code, signal);
    apiProc = null;
  });
}

function waitForHealth(timeoutMs = 60000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(`http://127.0.0.1:${apiPort}/api/health`, (res) => {
        let body = '';
        res.on('data', (c) => (body += c));
        res.on('end', () => {
          if (res.statusCode === 200) return resolve(body);
          retry();
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
        return reject(new Error('API health check timed out'));
      }
      setTimeout(tick, 400);
    };
    tick();
  });
}

function stopApi() {
  if (!apiProc) return;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(apiProc.pid), '/f', '/t']);
    } else {
      apiProc.kill('SIGTERM');
    }
  } catch (e) {
    console.error('[eq] stopApi', e);
  }
  apiProc = null;
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    title: 'EQ Legends BiS',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
  await mainWindow.loadURL(`http://127.0.0.1:${apiPort}/`);
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


ipcMain.handle('eq:app-info', async () => ({
  version: app.getVersion(),
  packaged: app.isPackaged,
  apiPort,
}));

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

function isInventoryFileName(name) {
  const n = String(name || '');
  if (!/\.txt$/i.test(n)) return false;
  if (/inventory\.exe$/i.test(n)) return false;
  return /inventory\.txt$/i.test(n) || /-inventory\.txt$/i.test(n);
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

ipcMain.handle('eq:settings-get', async () => {
  const s = readSettings();
  return {
    ok: true,
    eqInstallFolder: s.eqInstallFolder || '',
    lastInventoryPath: s.lastInventoryPath || '',
    lastInventoryName: s.lastInventoryName || '',
    lastInventoryMtimeMs: s.lastInventoryMtimeMs || null,
  };
});

ipcMain.handle('eq:settings-set', async (_evt, patch) => {
  const next = writeSettings(patch || {});
  return {
    ok: true,
    eqInstallFolder: next.eqInstallFolder || '',
    lastInventoryPath: next.lastInventoryPath || '',
    lastInventoryName: next.lastInventoryName || '',
    lastInventoryMtimeMs: next.lastInventoryMtimeMs || null,
  };
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

app.whenReady().then(async () => {
  // Pick a free-ish port: default 8765; allow override
  if (process.env.EQ_API_PORT) {
    apiPort = Number(process.env.EQ_API_PORT) || apiPort;
  }
  startApi();
  try {
    await waitForHealth();
  } catch (e) {
    dialog.showErrorBox(
      'EQ Legends BiS',
      `Could not start the local API.\n\n${e.message}\n\nIf this is a Windows build, ensure eq-api.exe was produced by scripts/build-windows.ps1.`
    );
    app.quit();
    return;
  }
  await createWindow();
  setupUpdater();
});

app.on('window-all-closed', () => {
  stopApi();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  stopApi();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
