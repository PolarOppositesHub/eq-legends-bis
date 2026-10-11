const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('eqDesktop', {
  isDesktop: true,
  platform: process.platform,
  checkForUpdates: () => ipcRenderer.invoke('eq:check-updates'),
  appInfo: () => ipcRenderer.invoke('eq:app-info'),
  quit: () => ipcRenderer.invoke('eq:quit'),
  getSettings: () => ipcRenderer.invoke('eq:settings-get'),
  setSettings: (patch) => ipcRenderer.invoke('eq:settings-set', patch),
  getWorkspace: () => ipcRenderer.invoke('eq:workspace-get'),
  setWorkspace: (session) => ipcRenderer.invoke('eq:workspace-set', session),
  clearWorkspace: () => ipcRenderer.invoke('eq:workspace-clear'),
  pickEqInstallFolder: () => ipcRenderer.invoke('eq:pick-eq-install-folder'),
  findLatestInventory: (folder) => ipcRenderer.invoke('eq:find-latest-inventory', folder),
  listInventoryFiles: (folder) => ipcRenderer.invoke('eq:list-inventory-files', folder),
  readInventoryFile: (filePath) => ipcRenderer.invoke('eq:read-inventory-file', filePath),
  watchInventory: (args) => ipcRenderer.invoke('eq:watch-inventory', args),
  onInventoryReady: (cb) => {
    const listener = (_event, info) => {
      try { cb(info); } catch (_) { /* ignore */ }
    };
    ipcRenderer.on('eq:inventory-ready', listener);
    return () => ipcRenderer.removeListener('eq:inventory-ready', listener);
  },
  openOverlay: (args) => ipcRenderer.invoke('eq:overlay-open', args),
  closeOverlay: (args) => ipcRenderer.invoke('eq:overlay-close', args),
  setOverlayLock: (args) => ipcRenderer.invoke('eq:overlay-lock', args),
  setOverlayOpacity: (args) => ipcRenderer.invoke('eq:overlay-opacity', args),
  setOverlayAppearance: (args) => ipcRenderer.invoke('eq:overlay-appearance', args),
  getOverlayState: () => ipcRenderer.invoke('eq:overlay-state'),
  getVideoMode: (args) => ipcRenderer.invoke('eq:video-mode', args),
  onOverlayState: (cb) => {
    const listener = (_event, state) => {
      try { cb(state); } catch (_) { /* ignore */ }
    };
    ipcRenderer.on('eq:overlay-state', listener);
    return () => ipcRenderer.removeListener('eq:overlay-state', listener);
  },
  pickSoundFile: () => ipcRenderer.invoke('eq:pick-sound-file'),
  readSoundFile: (filePath) => ipcRenderer.invoke('eq:read-sound-file', filePath),
  onOverlayConfig: (cb) => {
    const listener = (_event, config) => {
      try { cb(config); } catch (_) { /* ignore */ }
    };
    ipcRenderer.on('eq:overlay-config', listener);
    return () => ipcRenderer.removeListener('eq:overlay-config', listener);
  },
  splashFinished: () => ipcRenderer.send('eq:splash-finished'),
  onSplashStop: (cb) => {
    ipcRenderer.on('eq:splash-stop', () => {
      try { cb(); } catch (_) { /* ignore */ }
    });
  },
});
