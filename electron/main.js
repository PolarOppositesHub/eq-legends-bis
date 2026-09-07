const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const http = require('http');

const API_HOST = '127.0.0.1';
const API_PORT = Number(process.env.EQ_API_PORT || 8765);
const isDev = !app.isPackaged;

let mainWindow = null;
let apiProc = null;
let stopping = false;

function resourcesPath() {
  if (isDev) {
    return path.join(__dirname, '..', 'resources');
  }
  return process.resourcesPath;
}

function appRoot() {
  if (isDev) return path.join(__dirname, '..');
  return path.dirname(app.getPath('exe'));
}

function decodedDataPath() {
  const bundled = path.join(resourcesPath(), 'data', 'decoded');
  if (fs.existsSync(bundled)) return bundled;
  const dev = path.join(__dirname, '..', 'data', 'decoded');
  return dev;
}

function vendorPath() {
  const bundled = path.join(resourcesPath(), 'vendor');
  if (fs.existsSync(path.join(bundled, 'build_planner.py'))) return bundled;
  return path.join(__dirname, '..', 'backend', 'vendor');
}

function uiDistPath() {
  const bundled = path.join(resourcesPath(), 'ui');
  if (fs.existsSync(path.join(bundled, 'index.html'))) return bundled;
  return path.join(__dirname, '..', 'frontend', 'dist');
}

function waitForHealth(timeoutMs = 45000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(
        { host: API_HOST, port: API_PORT, path: '/api/health', timeout: 1500 },
        (res) => {
          res.resume();
          if (res.statusCode === 200) return resolve();
          if (Date.now() - started > timeoutMs) return reject(new Error('API health timeout'));
          setTimeout(tick, 400);
        }
      );
      req.on('error', () => {
        if (Date.now() - started > timeoutMs) return reject(new Error('API did not start'));
        setTimeout(tick, 400);
      });
    };
    tick();
  });
}

function resolveApiCommand() {
  const res = resourcesPath();
  const winSidecar = path.join(res, 'api', 'eq-api.exe');
  const nixSidecar = path.join(res, 'api', 'eq-api');
  if (process.platform === 'win32' && fs.existsSync(winSidecar)) {
    return { cmd: winSidecar, args: [], cwd: path.dirname(winSidecar) };
  }
  if (fs.existsSync(nixSidecar)) {
    return { cmd: nixSidecar, args: [], cwd: path.dirname(nixSidecar) };
  }

  // Dev / unpackaged: run uvicorn via python
  const root = appRoot();
  const pyCandidates = [
    process.env.EQ_PYTHON,
    path.join(root, '.venv', 'Scripts', 'python.exe'),
    path.join(root, '.venv', 'bin', 'python'),
    process.platform === 'win32' ? 'python' : 'python3',
  ].filter(Boolean);

  let python = pyCandidates.find((c) => {
    if (c === 'python' || c === 'python3') return true;
    return fs.existsSync(c);
  }) || (process.platform === 'win32' ? 'python' : 'python3');

  return {
    cmd: python,
    args: [
      '-m',
      'uvicorn',
      'backend.app.main:app',
      '--host',
      API_HOST,
      '--port',
      String(API_PORT),
    ],
    cwd: root,
  };
}

function startApi() {
  const { cmd, args, cwd } = resolveApiCommand();
  const env = {
    ...process.env,
    EQ_PACKAGED: app.isPackaged ? '1' : '0',
    EQ_APP_ROOT: appRoot(),
    EQ_LEGENDS_DATA: decodedDataPath(),
    EQ_LEGENDS_ROOT: vendorPath(),
    EQ_FRONTEND_DIST: uiDistPath(),
    EQ_XLSX_DIR: path.join(app.getPath('documents'), 'EQLegendsBiS'),
    PYTHONPATH: [
      path.join(appRoot(), 'backend'),
      path.join(__dirname, '..', 'backend'),
      vendorPath(),
      process.env.PYTHONPATH || '',
    ]
      .filter(Boolean)
      .join(path.delimiter),
  };

  try {
    fs.mkdirSync(env.EQ_XLSX_DIR, { recursive: true });
  } catch (_) {}

  console.log('[eq-legends] starting API', cmd, args.join(' '));
  apiProc = spawn(cmd, args, {
    cwd,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  apiProc.stdout.on('data', (d) => console.log('[api]', d.toString().trimEnd()));
  apiProc.stderr.on('data', (d) => console.error('[api]', d.toString().trimEnd()));
  apiProc.on('exit', (code, signal) => {
    console.log('[eq-legends] API exited', code, signal);
    apiProc = null;
    if (!stopping && mainWindow && !mainWindow.isDestroyed()) {
      dialog.showErrorBox(
        'EQ Legends API stopped',
        `The local API process exited (code=${code}). Restart the app.`
      );
    }
  });
}

function stopApi() {
  stopping = true;
  if (!apiProc) return;
  const proc = apiProc;
  apiProc = null;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(proc.pid), '/f', '/t']);
    } else {
      proc.kill('SIGTERM');
      setTimeout(() => {
        try {
          proc.kill('SIGKILL');
        } catch (_) {}
      }, 2000);
    }
  } catch (e) {
    console.error('stopApi', e);
  }
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    title: 'EQ Legends BiS + Build Sim',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const url = `http://${API_HOST}:${API_PORT}/`;
  await mainWindow.loadURL(url);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

async function checkForUpdatesStub() {
  // electron-updater wired when GH owner/repo or feed URL is configured.
  const owner = process.env.EQ_UPDATE_OWNER || process.env.GH_OWNER || '';
  const repo = process.env.EQ_UPDATE_REPO || process.env.GH_REPO || '';
  const feed = process.env.EQ_UPDATE_URL || '';
  if (!owner && !repo && !feed) {
    return {
      ok: false,
      configured: false,
      message:
        'Updates not configured. Set EQ_UPDATE_OWNER + EQ_UPDATE_REPO (GitHub) or EQ_UPDATE_URL. See README “how to enable updates”.',
    };
  }
  try {
    const { autoUpdater } = require('electron-updater');
    if (feed) {
      autoUpdater.setFeedURL({ provider: 'generic', url: feed });
    } else {
      autoUpdater.setFeedURL({ provider: 'github', owner, repo });
    }
    const result = await autoUpdater.checkForUpdates();
    return {
      ok: true,
      configured: true,
      updateInfo: result && result.updateInfo ? result.updateInfo : null,
      message: 'Checked for updates.',
    };
  } catch (e) {
    return { ok: false, configured: true, message: String(e && e.message ? e.message : e) };
  }
}

ipcMain.handle('eq:check-updates', async () => checkForUpdatesStub());
ipcMain.handle('eq:app-info', async () => ({
  version: app.getVersion(),
  packaged: app.isPackaged,
  api: `http://${API_HOST}:${API_PORT}`,
  data: decodedDataPath(),
}));

app.whenReady().then(async () => {
  try {
    startApi();
    await waitForHealth();
    await createWindow();
  } catch (e) {
    console.error(e);
    dialog.showErrorBox('EQ Legends failed to start', String(e && e.message ? e.message : e));
    app.quit();
  }
});

app.on('window-all-closed', () => {
  stopApi();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => stopApi());
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
