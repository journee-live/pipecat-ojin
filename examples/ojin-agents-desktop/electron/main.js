const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let tray;
let botProcess = null;

const isDev = process.env.NODE_ENV !== 'production';
const isMac = process.platform === 'darwin';

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 300,
    height: 600,
    minWidth: 300,
    minHeight: 300,
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
    show: false,
    icon: path.join(__dirname, '../build/icon.png'),
  });

  // Load the app
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    const indexPath = path.join(__dirname, '../dist/index.html');
    console.log('Loading production app from:', indexPath);
    mainWindow.loadFile(indexPath);
    
    // Open DevTools to see errors in production if needed
    if (process.env.DEBUG === '1') {
      mainWindow.webContents.openDevTools();
    }
  }

  // Log any load failures
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
    console.error('Failed to load:', errorCode, errorDescription);
  });

  mainWindow.once('ready-to-show', () => {
    // Ensure the menu bar is hidden when the window shows
    mainWindow.setMenuBarVisibility(false);
    mainWindow.show();
  });

  // Minimize to tray instead of closing
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
    return false;
  });
}

function createTray() {
  // Create tray icon
  const iconPath = path.join(__dirname, '../build/tray-icon.png');
  let trayIcon;
  
  try {
    trayIcon = nativeImage.createFromPath(iconPath);
    if (trayIcon.isEmpty()) {
      // Fallback: Create a simple icon programmatically
      // Create a 16x16 data URL with a simple "O" icon
      const canvas = `<svg width="16" height="16" xmlns="http://www.w3.org/2000/svg">
        <circle cx="8" cy="8" r="7" fill="none" stroke="white" stroke-width="2"/>
      </svg>`;
      trayIcon = nativeImage.createFromDataURL(`data:image/svg+xml;base64,${Buffer.from(canvas).toString('base64')}`);
    }
  } catch (error) {
    // Last resort: Create a simple visible icon
    const canvas = `<svg width="16" height="16" xmlns="http://www.w3.org/2000/svg">
      <circle cx="8" cy="8" r="7" fill="none" stroke="white" stroke-width="2"/>
    </svg>`;
    trayIcon = nativeImage.createFromDataURL(`data:image/svg+xml;base64,${Buffer.from(canvas).toString('base64')}`);
  }

  tray = new Tray(trayIcon);
  
  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show App',
      click: () => {
        mainWindow.show();
      },
    },
    {
      label: 'Quit',
      click: () => {
        app.isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setToolTip('Ojin Agents Desktop');
  tray.setContextMenu(contextMenu);

  // Show window on tray icon click
  tray.on('click', () => {
    mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
  });
}

// Bot session management
function startBotSession(personaId, humeConfigId, environment) {
  console.log('[startBotSession] Called with:', { personaId, humeConfigId, environment });
  console.log('[startBotSession] botProcess state:', {
    exists: !!botProcess,
    killed: botProcess?.killed,
    exitCode: botProcess?.exitCode,
    pid: botProcess?.pid
  });
  
  // Check if process exists AND is still running
  if (botProcess && !botProcess.killed && botProcess.exitCode === null) {
    console.log('[startBotSession] Bot session already running, stopping first...');
    stopBotSession();
    
    // Wait a bit for process to terminate before starting new one
    setTimeout(() => {
      console.log('[startBotSession] Timeout elapsed, starting new process after stop');
      startNewBotProcess(personaId, humeConfigId, environment);
    }, 1000);
    return;
  }

  // If process exists but is dead, reset it
  if (botProcess) {
    console.log('[startBotSession] Clearing dead bot process reference');
    botProcess = null;
  }

  console.log('[startBotSession] Starting new bot process immediately');
  startNewBotProcess(personaId, humeConfigId, environment);
}

function startNewBotProcess(personaId, humeConfigId, environment) {
  console.log(`Starting bot session: persona=${personaId}, hume=${humeConfigId}, environment=${environment}`);

  // Use venv Python if available, fallback to system Python
  const venvPythonPath = process.platform === 'win32' 
    ? path.join(__dirname, '..', 'venv', 'Scripts', 'python.exe')
    : path.join(__dirname, '..', 'venv', 'bin', 'python');
  
  const fs = require('fs');
  const pythonPath = fs.existsSync(venvPythonPath) 
    ? venvPythonPath 
    : (process.platform === 'win32' ? 'python' : 'python3');
  
  console.log('Using Python:', pythonPath);
  
  const botScriptPath = path.join(__dirname, '..', 'bot.py');

  botProcess = spawn(pythonPath, [botScriptPath, personaId, humeConfigId, environment], {
    cwd: path.join(__dirname, '..'),
  });

  botProcess.stdout.on('data', (data) => {
    const lines = data.toString().split('\n').filter(line => line.trim());
    
    lines.forEach(line => {
      try {
        const message = JSON.parse(line);
        
        // Only log non-video-frame messages to avoid console spam
        if (message.type !== 'video_frame') {
          console.log('Bot message:', message.type);
        }
        
        // Forward messages to renderer
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('bot-message', message);
        }
      } catch (e) {
        console.log('Bot stdout:', line);
      }
    });
  });

  botProcess.stderr.on('data', (data) => {
    console.error('Bot stderr:', data.toString());
  });

  botProcess.on('error', (error) => {
    console.error('Bot process error:', error);
    botProcess = null; // Reset on error
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('bot-message', {
        type: 'error',
        message: `Failed to start bot: ${error.message}`
      });
    }
  });

  botProcess.on('close', (code) => {
    console.log(`[botProcess.close] Bot process exited with code ${code}, PID was: ${botProcess?.pid}`);
    console.log('[botProcess.close] Setting botProcess to null');
    botProcess = null;
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('bot-message', {
        type: 'ended',
        code: code
      });
    }
  });
}

function stopBotSession() {
  if (botProcess) {
    console.log('Stopping bot session...');
    
    // Try graceful shutdown first
    try {
      if (process.platform === 'win32') {
        // Windows: Use taskkill to force terminate the process tree
        const { exec } = require('child_process');
        exec(`taskkill /pid ${botProcess.pid} /T /F`, (error) => {
          if (error) {
            console.error('Error killing bot process:', error);
          }
        });
      } else {
        // Unix: Send SIGTERM then SIGKILL if needed
        botProcess.kill('SIGTERM');
        setTimeout(() => {
          if (botProcess && !botProcess.killed) {
            botProcess.kill('SIGKILL');
          }
        }, 2000);
      }
    } catch (error) {
      console.error('Error stopping bot:', error);
    }
    
    botProcess = null;
  }
}

// IPC handlers
ipcMain.handle('start-bot-session', async (event, { personaId, humeConfigId, environment }) => {
  console.log('[IPC] Received start-bot-session request:', { personaId, humeConfigId, environment });
  console.log('[IPC] Current botProcess state:', {
    exists: !!botProcess,
    killed: botProcess?.killed,
    exitCode: botProcess?.exitCode,
    pid: botProcess?.pid
  });
  
  try {
    startBotSession(personaId, humeConfigId, environment);
    return { success: true };
  } catch (error) {
    console.error('Failed to start bot session:', error);
    return { success: false, error: error.message };
  }
});

ipcMain.handle('stop-bot-session', async () => {
  try {
    stopBotSession();
    return { success: true };
  } catch (error) {
    console.error('Failed to stop bot session:', error);
    return { success: false, error: error.message };
  }
});

app.whenReady().then(() => {
  createWindow();
  createTray();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (!isMac) {
    app.quit();
  }
});

app.on('before-quit', () => {
  app.isQuitting = true;
  stopBotSession();
});

// Prevent multiple instances
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
