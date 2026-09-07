const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('eqDesktop', {
  checkForUpdates: () => ipcRenderer.invoke('eq:check-updates'),
  appInfo: () => ipcRenderer.invoke('eq:app-info'),
});
