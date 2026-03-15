const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods to renderer
contextBridge.exposeInMainWorld('electronAPI', {
  getSettings: () => ipcRenderer.invoke('get-settings'),
  saveSettings: (settings) => ipcRenderer.invoke('save-settings', settings),
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
  
  // Platform info
  platform: process.platform,
  isElectron: true,
});
