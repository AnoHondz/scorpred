'use strict';

const { app, BrowserWindow, shell, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const fs = require('fs');

// ── Config ────────────────────────────────────────────────────────────────────
const FLASK_PORT = parseInt(process.env.SCORPRED_PORT || '5001', 10);
const FLASK_URL  = `http://127.0.0.1:${FLASK_PORT}`;
const HEALTH_URL = `${FLASK_URL}/health`;
const WAIT_MS    = 60_000; // max seconds to wait for Flask

// ── Paths ─────────────────────────────────────────────────────────────────────
// When packaged by electron-builder, extraResources lands in process.resourcesPath/scorpred.
// In dev (npm start from desktop/), the repo root is two levels up.
const REPO_ROOT = app.isPackaged
  ? path.join(process.resourcesPath, 'scorpred')
  : path.join(__dirname, '..', '..');

// ── State ─────────────────────────────────────────────────────────────────────
let mainWindow = null;
let flaskProc  = null;

// ── Helpers ───────────────────────────────────────────────────────────────────
function findPython() {
  // On Windows try 'python', on Unix try 'python3' first
  const candidates = process.platform === 'win32'
    ? ['python', 'python3', 'py']
    : ['python3', 'python'];
  return candidates[0]; // spawn will raise if none found
}

function startFlask() {
  const python = findPython();
  const appPy  = path.join(REPO_ROOT, 'app.py');

  if (!fs.existsSync(appPy)) {
    dialog.showErrorBox('ScorPred', `Could not find app.py at:\n${appPy}`);
    app.quit();
    return;
  }

  const env = {
    ...process.env,
    PORT:              String(FLASK_PORT),
    FLASK_DEBUG:       '0',
    FLASK_USE_RELOADER:'0',
    PYTHONUNBUFFERED:  '1',
  };

  flaskProc = spawn(python, [appPy], {
    cwd: REPO_ROOT,
    env,
    windowsHide: true,
  });

  flaskProc.stdout.on('data', d => process.stdout.write(`[flask] ${d}`));
  flaskProc.stderr.on('data', d => process.stderr.write(`[flask] ${d}`));
  flaskProc.on('exit', code => {
    if (code !== 0 && code !== null) {
      console.error(`[flask] exited with code ${code}`);
    }
  });
}

function waitForFlask(timeout = WAIT_MS) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeout;
    function attempt() {
      http.get(HEALTH_URL, res => {
        res.resume();
        resolve();
      }).on('error', () => {
        if (Date.now() >= deadline) {
          reject(new Error(`Flask did not respond within ${timeout / 1000}s`));
        } else {
          setTimeout(attempt, 400);
        }
      });
    }
    attempt();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width:   1400,
    height:  900,
    minWidth:  900,
    minHeight: 600,
    title:   'ScorPred',
    backgroundColor: '#0f172a',
    webPreferences: {
      nodeIntegration:  false,
      contextIsolation: true,
      sandbox:          true,
    },
  });

  mainWindow.loadURL(FLASK_URL);

  // Open external links in the system browser, not in the app
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  startFlask();

  try {
    await waitForFlask();
  } catch (err) {
    dialog.showErrorBox(
      'ScorPred — startup failed',
      `The backend server did not start.\n\n${err.message}\n\nMake sure Python and all requirements are installed.`
    );
    app.quit();
    return;
  }

  createWindow();

  app.on('activate', () => {
    if (mainWindow === null) createWindow();
  });
});

app.on('window-all-closed', () => {
  killFlask();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', killFlask);

function killFlask() {
  if (flaskProc) {
    flaskProc.kill();
    flaskProc = null;
  }
}
