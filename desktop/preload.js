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
  splashFinished: () => ipcRenderer.send('eq:splash-finished'),
  onSplashStop: (cb) => {
    ipcRenderer.on('eq:splash-stop', () => {
      try { cb(); } catch (_) { /* ignore */ }
    });
  },
});
