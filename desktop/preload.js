const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('eqDesktop', {
  isDesktop: true,
  platform: process.platform,
  checkForUpdates: () => ipcRenderer.invoke('eq:check-updates'),
  appInfo: () => ipcRenderer.invoke('eq:app-info'),
  getSettings: () => ipcRenderer.invoke('eq:settings-get'),
  setSettings: (patch) => ipcRenderer.invoke('eq:settings-set', patch),
  pickEqInstallFolder: () => ipcRenderer.invoke('eq:pick-eq-install-folder'),
  findLatestInventory: (folder) => ipcRenderer.invoke('eq:find-latest-inventory', folder),
  readInventoryFile: (filePath) => ipcRenderer.invoke('eq:read-inventory-file', filePath),
});
