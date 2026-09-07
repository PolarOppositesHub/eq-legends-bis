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
  const dataRoot = decodedCandidates.find((p) => {
    try {
      return fs.existsSync(p) && fs.readdirSync(p).some((f) => f.endsWith('.json'));
    } catch (_) {
      return false;
    }
  }) || decodedCandidates[0];
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
