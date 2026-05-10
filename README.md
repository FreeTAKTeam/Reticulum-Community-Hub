# RCH Shared Web UI

This branch is the canonical Vue web UI source for Reticulum Community Hub.

The Python `rch-python` branch keeps its legacy backend and Electron wrapper.
The Rust `rust-next` branch consumes this UI as the web frontend for
`r3akt-rch-server` and the Tauri desktop shell.

## Branch Rules

- Keep active UI feature work here first.
- Merge UI changes into `rust-next` for the Rust product line.
- Backport only critical UI fixes into `rch-python`.
- Do not add Python backend, Electron packaging, Rust backend, runtime
  databases, logs, or generated QA artifacts to this branch.

## Validation

```powershell
npm --prefix ui ci
npm --prefix ui run lint
npm --prefix ui run test
npm --prefix ui run build
```
