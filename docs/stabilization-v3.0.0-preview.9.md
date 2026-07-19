# v3.0.0-preview.9 stabilization report

## Scope

This pass audited tracked Rust crates and binaries, the shared Vue/TypeScript
UI, the Tauri shell, migrations, scripts, workflows, packaging, configuration
guidance, and current documentation. The Python 2.9.x branch and shared-UI
ownership contract were not changed.

## Findings and corrections

- Added `r3akt-identity` and the maintained ingest example to the workspace;
  removed retired node/router/store prototypes and the example that depended on
  them.
- Replaced single-use response-body parsing in the UI API client so JSON, text,
  malformed JSON, 401/403, timeout, and retry paths preserve status and detail.
- Added `vue-tsc --noEmit` and corrected the pre-existing types it exposed.
- Replaced new password and PIN records with Argon2id PHC hashes and added
  automatic successful-login migration for legacy preview SHA-256 records.
- Added per-client HTTP, WebSocket, and kill-switch PIN throttling, including
  HTTP `429` and `Retry-After` behavior.
- Propagated authentication-store failures instead of treating them as invalid
  credentials. Unexpected 500s now have generic client details and an
  `X-Request-ID` correlated with the server log.
- Removed the hard-coded desktop credential and made mutex, sidecar startup,
  termination, and shutdown failures explicit.
- Denied unsafe Rust across the workspace, expanded MSRV/rustdoc/UI gates, and
  made the Ubuntu release gate discover multiarch OpenSSL paths.
- Removed the MSRV-compatible but RustSec-affected `time` dependency after
  `RUSTSEC-2026-0009` was published; the maintained date/time surface now uses
  the Rust 1.85-compatible `chrono` crate and the denied-warning audit is clean.
- Updated the desktop shell to the Rust 1.88 release toolchain and current
  Rust-1.88-compatible Tauri/plist graph, removing the desktop `quick-xml` and
  `anyhow` advisories found during the final prerelease audit. The server
  workspace retains its Rust 1.85 MSRV.
- Added maintained HTTP, WebSocket, Reticulum, TAK, operations, and
  troubleshooting examples.

## Compatibility

No northbound route was removed or renamed. Existing success/error envelopes
remain intact. The compatible additions are `429` plus `Retry-After`,
`X-Request-ID` on unexpected 500s, sanitized unexpected error details, and
expanded plaintext `/Examples` output.

ZeroMQ remains the delivery data plane and RPC remains control-only. Existing
databases need no manual hash migration.

## Validation evidence

Local results from the stabilization worktree are recorded below. Hosted and
published results are completed on the draft PR and release page because those
identifiers do not exist until after this source is committed.

| Gate | Result |
| --- | --- |
| Rust 1.85 MSRV workspace check | Passed with the locked dependency graph |
| Rust 1.88 release check and release test compilation | Passed |
| stable fmt, strict clippy, workspace and focused tests | Passed; 328 server tests passed and only the dedicated environment-gated load test was ignored in normal CI |
| `cargo audit --deny warnings` | Passed; 224 dependencies scanned, no advisory ignored |
| denied-warning workspace rustdoc | Passed |
| UI install, lint, type-check, 112 tests, production build | Passed |
| server and TAK release builds | Passed |
| Tauri sidecars and desktop AppImage build | Passed using Rust 1.88 and the pinned LXMF-rs v0.9.5 daemon binary |
| committed release-readiness gate | Passed, including HTTP smoke and automatic Ubuntu multiarch OpenSSL discovery |
| local Reticulum receipt/fanout/event/load gate | Passed: direct receipt, topic fanout, ZeroMQ event poll, and 500/500 load messages received |
| hosted PR checks | Pending |
| published asset/checksum/manifest audit | Pending |

## External limitations

External TAK infrastructure and REM phone/deck hardware are environment-gated.
Neither was configured in the release-cut environment, so the external TAK and
REM phone/deck checks were not run. Deterministic local and hosted gates still
block publication.

The Tauri Linux graph inherits GTK3 bindings that RustSec marks unmaintained,
and its upstream `glib` branch carries an unsound-API warning. The current
Tauri release has no GTK4 migration path; RCH does not call the affected
`VariantStrIter` API. These ecosystem notices remain disclosed and monitored,
while the separately gated server workspace passes `cargo audit --deny
warnings` without exceptions.

## Release identity

- Version/tag: `v3.0.0-preview.9`
- Source branch: `agent/preview-9-stabilization`
- Merge commit: pending
- LXMF-rs baseline: `v0.9.5`, commit
  `7cafc5b4be21ff4f777d0f2300cfb79e5d0da23c`
- Server archives: Windows x64, macOS x64, macOS arm64, Linux AMD64, Linux
  Raspberry Pi 64
- Desktop packages: Windows x64 NSIS, Linux x64 AppImage
