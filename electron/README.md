# RCH Desktop (Electron)

This folder contains a minimal Electron wrapper for the Reticulum Community Hub UI.
The desktop shell bundles the UI assets but expects the RCH backend to run locally.

## Prerequisites

- Node.js 18+
- RCH backend running locally (default `rch start --data-dir ./RCH_Store --port 8000`)

## Development

1. Install dependencies:

   ```bash
   cd electron
   npm install
   ```

2. Start the UI + Electron shell:

   ```bash
   npm run dev
   ```

By default, the dev shell loads `http://127.0.0.1:5173`. Override the host or port
with `RCH_UI_HOST` and `RCH_UI_PORT` if needed.

## Package for distribution

Build the UI + Electron bundle and create installers:

```bash
cd electron
npm run dist
```

`npm run dist` runs the backend build step, so ensure PyInstaller is available
before packaging.

### Backend packaging (single executable)

The Electron build expects a bundled backend executable built with PyInstaller.

1. Install backend build tooling:

   ```bash
   python -m pip install -e .
   python -m pip install pyinstaller
   ```

2. Build the backend executable:

   ```bash
   cd electron
   npm run build:backend
   ```

Use `RCH_PYTHON` to point at a specific Python interpreter if needed.

### Windows (NSIS)

```bash
npm run dist -- --win
```

### Windows installer + portable

```bash
npm run dist -- --win
```

Windows artifact names:

- Installer: `RCH_win Install_<version>.exe`
- Portable: `RCH_win Portable_<version>.exe`

### Raspberry Pi OS (Linux)

Electron Builder supports `armv7l` and `arm64` targets. Build on a Linux host for
best results.

```bash
npm run dist -- --linux --armv7l
npm run dist -- --linux --arm64
```

## Backend note

The dev shell does not start the RCH backend automatically. Start the backend
separately (for example, `rch start --data-dir ./RCH_Store --port 8000`).

Packaged builds start the bundled backend automatically (defaults to
`http://127.0.0.1:8000`). Override with `RCH_DATA_DIR`, `RCH_BACKEND_PORT`, or
`RCH_LOG_LEVEL` if needed. Set `RCH_BACKEND_MANAGED=false` to disable autostart.

Before each desktop build, Electron version metadata is synchronized from
`pyproject.toml` automatically.

If the UI cannot connect in a packaged build, check the backend log at:
`%APPDATA%/RCH Desktop/backend.log` (Windows) or the platform-specific userData
directory for details.

When the UI loads from `file://`, it defaults to `http://127.0.0.1:8000` for the
API and `ws://127.0.0.1:8000` for WebSockets. Override these in the Connect page
or set `VITE_RTH_BASE_URL` / `VITE_RTH_WS_BASE_URL` at build time.
