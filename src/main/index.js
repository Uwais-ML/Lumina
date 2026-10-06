/**
 * src/main/index.js - Electron Main Process for Lumina Desktop.
 * 
 * Manages window lifecycle, secure IPC communication, and the Python backend runtime.
 */

const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const readline = require('readline');

let mainWindow = null;
let pythonBridge = null;
let bridgeReadline = null;
const pendingRequests = new Map();

const PROJECT_ROOT = path.resolve(__dirname, '..', '..');

/**
 * Resolves the appropriate Python interpreter (mirrors Lumina.py OS detection).
 */
function resolvePythonBinary() {
  const platform = process.platform;
  let bundledBin = null;

  if (platform === 'darwin') {
    bundledBin = path.join(PROJECT_ROOT, 'python-dependencies', 'macos-intel', 'bin', 'python3');
  } else if (platform === 'win32') {
    bundledBin = path.join(PROJECT_ROOT, 'python-dependencies', 'windows', 'python.exe');
  } else {
    bundledBin = path.join(PROJECT_ROOT, 'python-dependencies', 'linux-intel', 'bin', 'python3');
  }

  if (fs.existsSync(bundledBin)) {
    return bundledBin;
  }

  // Check packaged app resources path
  const resourcesPython = path.join(process.resourcesPath || '', 'python-runtime', platform === 'win32' ? 'python.exe' : 'bin/python3');
  if (fs.existsSync(resourcesPython)) {
    return resourcesPython;
  }

  // Fallback to system python3
  return 'python3';
}

/**
 * Resolves the PYTHONPATH with bundled site-packages and scripts.
 */
function getPythonEnv() {
  const env = { ...process.env, PYTHONUNBUFFERED: '1' };
  const platform = process.platform;
  let sitePkgs = null;

  if (platform === 'darwin') {
    sitePkgs = path.join(PROJECT_ROOT, 'python-dependencies', 'macos-intel', 'lib', 'python3.12', 'site-packages');
  } else if (platform === 'win32') {
    sitePkgs = path.join(PROJECT_ROOT, 'python-dependencies', 'windows', 'Lib', 'site-packages');
  } else {
    sitePkgs = path.join(PROJECT_ROOT, 'python-dependencies', 'linux-intel', 'lib', 'python3.12', 'site-packages');
  }

  const scriptsDir = path.join(PROJECT_ROOT, 'scripts');
  const backendDir = path.join(PROJECT_ROOT, 'app', 'backend');
  const toolsDir = path.join(PROJECT_ROOT, 'Tools');

  const paths = [sitePkgs, backendDir, scriptsDir, toolsDir, PROJECT_ROOT].filter(p => p && fs.existsSync(p));
  const delimiter = platform === 'win32' ? ';' : ':';
  env.PYTHONPATH = paths.join(delimiter) + (env.PYTHONPATH ? delimiter + env.PYTHONPATH : '');
  return env;
}

/**
 * Starts the Python backend bridge via stdio IPC.
 */
function startPythonBridge() {
  const pythonBin = resolvePythonBinary();
  const bridgeScript = path.join(PROJECT_ROOT, 'app', 'backend', 'bridge.py');
  const env = getPythonEnv();

  console.log(`[Lumina Main] Spawning Python bridge: ${pythonBin} ${bridgeScript}`);

  try {
    pythonBridge = spawn(pythonBin, [bridgeScript], {
      cwd: PROJECT_ROOT,
      env: env,
      stdio: ['pipe', 'pipe', 'pipe']
    });

    bridgeReadline = readline.createInterface({
      input: pythonBridge.stdout,
      terminal: false
    });

    bridgeReadline.on('line', (line) => {
      line = line.trim();
      if (!line) return;

      try {
        const event = JSON.parse(line);

        // Handle initial ready signal
        if (event.type === 'bridge:ready') {
          console.log('[Lumina Main] Python bridge is ready.');
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('lumina:backend:ready', event);
          }
          return;
        }

        const reqId = event.req_id;
        if (!reqId) return;

        // Check if this is a response to a one-shot request
        if (event.type === 'response' || event.type === 'error') {
          const handler = pendingRequests.get(reqId);
          if (handler && typeof handler.resolve === 'function') {
            if (event.type === 'error') {
              handler.reject(new Error(event.error || 'Unknown backend error'));
            } else {
              handler.resolve(event.data);
            }
            pendingRequests.delete(reqId);
          }
        }

        // Stream event forwarding to renderer
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send(`lumina:stream:event:${reqId}`, event);
        }

      } catch (err) {
        console.error('[Lumina Main] Failed to parse bridge JSON:', line, err);
      }
    });

    pythonBridge.stderr.on('data', (data) => {
      console.warn(`[Lumina Python Stderr] ${data.toString().trim()}`);
    });

    pythonBridge.on('close', (code) => {
      console.log(`[Lumina Main] Python bridge exited with code ${code}`);
      pythonBridge = null;
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('lumina:backend:status', { status: 'stopped', code });
      }
    });

    pythonBridge.on('error', (err) => {
      console.error('[Lumina Main] Python bridge error:', err);
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('lumina:backend:error', { error: err.message });
      }
    });

  } catch (err) {
    console.error('[Lumina Main] Failed to start Python bridge:', err);
  }
}

/**
 * Sends a command to the Python bridge.
 */
function sendBridgeCommand(action, payload = {}) {
  return new Promise((resolve, reject) => {
    if (!pythonBridge || !pythonBridge.stdin) {
      return reject(new Error('Python backend bridge is not running'));
    }

    const reqId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
    const message = { id: reqId, action, ...payload };

    pendingRequests.set(reqId, { resolve, reject });

    try {
      pythonBridge.stdin.write(JSON.stringify(message) + '\n');
    } catch (err) {
      pendingRequests.delete(reqId);
      reject(err);
    }

    // Timeout after 60s for standard requests (excluding streams)
    if (action !== 'chat_stream') {
      setTimeout(() => {
        if (pendingRequests.has(reqId)) {
          pendingRequests.delete(reqId);
          reject(new Error(`Request ${action} timed out`));
        }
      }, 60000);
    }
  });
}

/**
 * Creates the primary application window.
 */
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1240,
    height: 820,
    minWidth: 920,
    minHeight: 600,
    backgroundColor: '#ffffff',
    title: 'Lumina',
    titleBarStyle: 'hiddenInset', // Native traffic lights on macOS
    frame: process.platform === 'darwin' ? false : false, // Frameless design with custom titlebar
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload', 'index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true
    },
    show: false
  });

  mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── IPC Handlers ─────────────────────────────────────────────────────────────

ipcMain.handle('lumina:chat:stream', async (event, payload) => {
  const reqId = `stream_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
  if (!pythonBridge || !pythonBridge.stdin) {
    throw new Error('Python bridge not running');
  }

  const message = {
    id: reqId,
    action: 'chat_stream',
    ...payload
  };

  pythonBridge.stdin.write(JSON.stringify(message) + '\n');
  return reqId;
});

ipcMain.handle('lumina:conversations:list', () => sendBridgeCommand('list_conversations'));
ipcMain.handle('lumina:conversations:get', (e, id) => sendBridgeCommand('get_conversation', { conversation_id: id }));
ipcMain.handle('lumina:conversations:delete', (e, id) => sendBridgeCommand('delete_conversation', { conversation_id: id }));
ipcMain.handle('lumina:models:list', () => sendBridgeCommand('list_models'));
ipcMain.handle('lumina:models:launch', (e, model) => sendBridgeCommand('launch_model', { model }));
ipcMain.handle('lumina:models:kill', (e, payload) => sendBridgeCommand('kill_model', payload || {}));
ipcMain.handle('lumina:models:smartswitch', (e, payload) => sendBridgeCommand('trigger_smartswitch', payload || {}));
ipcMain.handle('lumina:models:assess', () => sendBridgeCommand('system_assess'));
ipcMain.handle('lumina:models:download', (e, payload) => sendBridgeCommand('download_model', payload || {}));
ipcMain.handle('lumina:status:get', () => sendBridgeCommand('get_status'));
ipcMain.handle('lumina:tools:list', () => sendBridgeCommand('list_tools'));
ipcMain.handle('lumina:tools:create', (e, payload) => sendBridgeCommand('create_tool', payload || {}));
ipcMain.handle('lumina:tools:delete', (e, name) => sendBridgeCommand('delete_tool', { name }));
ipcMain.handle('lumina:rag:ingest', (e, text, filename) => sendBridgeCommand('rag_ingest', { text, filename }));
ipcMain.handle('lumina:ide:execute', (e, code) => sendBridgeCommand('execute_code', { code }));
ipcMain.handle('lumina:ide:complete', (e, prefix, max_tokens) => sendBridgeCommand('complete_code', { prefix, max_tokens }));

ipcMain.on('lumina:window:minimize', () => mainWindow && mainWindow.minimize());
ipcMain.on('lumina:window:maximize', () => {
  if (mainWindow) {
    mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
  }
});
ipcMain.on('lumina:window:close', () => mainWindow && mainWindow.close());

// ── Application Lifecycle ───────────────────────────────────────────────────

app.whenReady().then(() => {
  createWindow();
  startPythonBridge();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('will-quit', () => {
  if (pythonBridge) {
    console.log('[Lumina Main] Terminating Python bridge process...');
    try {
      pythonBridge.kill('SIGTERM');
    } catch (e) {
      // Ignore
    }
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
