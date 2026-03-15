const { app, BrowserWindow, Tray, Menu, shell, dialog, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const Store = require('electron-store');

const store = new Store();
const isDev = process.env.NODE_ENV === 'development';

let mainWindow = null;
let tray = null;
let backendProcess = null;
let isQuitting = false;

const BACKEND_PORT = 8000;
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;

// ─── Backend Management ────────────────────────────────────────────────

function getBackendPath() {
  if (isDev) {
    return null; // Run backend separately in dev mode
  }
  
  const resourcesPath = process.resourcesPath;
  const backendPath = path.join(resourcesPath, 'backend', 'bracket-bot-server.exe');
  return backendPath;
}

async function startBackend() {
  const backendPath = getBackendPath();
  
  if (!backendPath) {
    console.log('Dev mode: Backend should be started separately');
    return true;
  }

  return new Promise((resolve) => {
    console.log('Starting backend:', backendPath);
    
    backendProcess = spawn(backendPath, [], {
      detached: false,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        ALPACA_KEY: store.get('alpacaKey', ''),
        ALPACA_SECRET: store.get('alpacaSecret', ''),
      }
    });

    backendProcess.stdout.on('data', (data) => {
      console.log(`Backend: ${data}`);
    });

    backendProcess.stderr.on('data', (data) => {
      console.error(`Backend Error: ${data}`);
    });

    backendProcess.on('error', (err) => {
      console.error('Failed to start backend:', err);
      dialog.showErrorBox('Backend Error', `Failed to start trading server: ${err.message}`);
      resolve(false);
    });

    backendProcess.on('exit', (code) => {
      console.log(`Backend exited with code ${code}`);
      if (!isQuitting) {
        // Unexpected exit - try to restart
        setTimeout(() => startBackend(), 2000);
      }
    });

    // Wait for backend to be ready
    waitForBackend(30).then(resolve);
  });
}

function waitForBackend(maxAttempts = 30) {
  return new Promise((resolve) => {
    let attempts = 0;
    
    const check = () => {
      http.get(`${BACKEND_URL}/health`, (res) => {
        if (res.statusCode === 200) {
          console.log('Backend is ready');
          resolve(true);
        } else {
          retry();
        }
      }).on('error', () => {
        retry();
      });
    };

    const retry = () => {
      attempts++;
      if (attempts < maxAttempts) {
        setTimeout(check, 500);
      } else {
        console.error('Backend failed to start');
        resolve(false);
      }
    };

    check();
  });
}

function stopBackend() {
  if (backendProcess) {
    console.log('Stopping backend...');
    backendProcess.kill();
    backendProcess = null;
  }
}

// ─── Window Management ─────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 768,
    backgroundColor: '#0a0a0f',
    icon: path.join(__dirname, '../assets/icon.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    titleBarStyle: 'default',
    show: false,
  });

  // Load the app
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    const frontendPath = path.join(process.resourcesPath, 'frontend', 'index.html');
    mainWindow.loadFile(frontendPath);
  }

  // Show window when ready
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.focus();
  });

  // Handle external links
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // Minimize to tray instead of closing
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
      
      if (process.platform === 'darwin') {
        app.dock.hide();
      }
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createTray() {
  const iconPath = path.join(__dirname, '../assets/tray-icon.png');
  tray = new Tray(iconPath);
  
  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show Bracket Bot',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      }
    },
    {
      label: 'Settings',
      click: () => {
        showSettingsDialog();
      }
    },
    { type: 'separator' },
    {
      label: 'Place All Brackets',
      click: async () => {
        try {
          await fetch(`${BACKEND_URL}/actions/place-all`, { method: 'POST' });
        } catch (e) {
          console.error('Failed to place brackets:', e);
        }
      }
    },
    {
      label: 'Cancel All Orders',
      click: async () => {
        try {
          await fetch(`${BACKEND_URL}/actions/cancel-all`, { method: 'POST' });
        } catch (e) {
          console.error('Failed to cancel orders:', e);
        }
      }
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        isQuitting = true;
        app.quit();
      }
    }
  ]);

  tray.setToolTip('Bracket Bot');
  tray.setContextMenu(contextMenu);
  
  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

function showSettingsDialog() {
  const settingsWindow = new BrowserWindow({
    width: 500,
    height: 400,
    parent: mainWindow,
    modal: true,
    resizable: false,
    minimizable: false,
    maximizable: false,
    backgroundColor: '#0a0a0f',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    }
  });

  settingsWindow.loadFile(path.join(__dirname, 'settings.html'));
}

// ─── IPC Handlers ──────────────────────────────────────────────────────

ipcMain.handle('get-settings', () => {
  return {
    alpacaKey: store.get('alpacaKey', ''),
    alpacaSecret: store.get('alpacaSecret', ''),
  };
});

ipcMain.handle('save-settings', (event, settings) => {
  store.set('alpacaKey', settings.alpacaKey || '');
  store.set('alpacaSecret', settings.alpacaSecret || '');
  
  // Restart backend with new settings
  stopBackend();
  setTimeout(() => startBackend(), 1000);
  
  return true;
});

ipcMain.handle('get-backend-url', () => {
  return BACKEND_URL;
});

// ─── App Lifecycle ─────────────────────────────────────────────────────

app.whenReady().then(async () => {
  // Start backend first
  const backendReady = await startBackend();
  
  if (!backendReady && !isDev) {
    dialog.showErrorBox(
      'Startup Error',
      'Failed to start the trading server. Please check your installation.'
    );
    app.quit();
    return;
  }

  createWindow();
  createTray();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    } else if (mainWindow) {
      mainWindow.show();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    // Don't quit - keep running in tray
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  stopBackend();
});

app.on('quit', () => {
  stopBackend();
});

// Single instance lock
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
}
