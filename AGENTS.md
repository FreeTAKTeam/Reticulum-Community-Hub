# AGENTS.md - RCH Shared Web UI

This branch contains only the shared Vue UI source for RCH. Python backend work
belongs on `rch-python`; Rust backend and packaging work belongs on `rust-next`.

## Expected Work

- Maintain `ui/` as the single web UI source.
- Preserve backend compatibility with both Python RCH 2.9.x and Rust
  `r3akt-rch-server`.
- Use existing API base URL configuration: `VITE_RCH_BASE_URL`,
  `VITE_RCH_WS_BASE_URL`, `VITE_RTH_BASE_URL`, and `VITE_RTH_WS_BASE_URL`.

## Checks

```powershell
npm --prefix ui ci
npm --prefix ui run lint
npm --prefix ui run test
npm --prefix ui run build
```

Do not commit `ui/dist`, `node_modules`, logs, screenshots, local databases, or
temporary Playwright/Vite files.

