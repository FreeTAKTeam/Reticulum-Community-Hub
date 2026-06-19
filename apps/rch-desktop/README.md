# RCH Desktop for Rust

This is the Tauri desktop shell for the Rust RCH product line. It reuses the
shared Vue UI from `ui/` and launches `r3akt-rch-server` as a managed local
sidecar.

## Build

```powershell
npm --prefix ui ci
npm --prefix apps/rch-desktop install
npm --prefix apps/rch-desktop run build
```

The sidecar preparation step builds `r3akt-rch-server --release` and copies the
binary into `src-tauri/binaries/` with the host target-triple suffix required by
Tauri.

## Runtime

The desktop app starts the backend on `127.0.0.1:8000` and stores Rust runtime
state under the platform application data directory. The UI keeps using the
existing RCH base URL configuration and falls back to local HTTP when loaded
from the desktop shell.
