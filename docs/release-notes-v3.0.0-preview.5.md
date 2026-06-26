# RCH Rust v3.0.0-preview.5 Release Notes

This prerelease refreshes the Rust RCH 3.0.0 preview line after the
`v3.0.0-preview.4` package release.

Python `2.9.x` remains the stable maintenance line on `rch-python`; this is a
Rust preview intended for validation of the 3.0 runtime, packaging, migration,
LXMF, TAK integration, and local operator desktop path.

## Runtime Requirement

RCH Rust 3.0 requires a running LXMF-rs `reticulumd` instance. The server
package includes the RCH server, TAK service, shared UI, and service templates,
but it does not replace the Reticulum/LXMF daemon. Start and configure
`reticulumd` first, then run RCH with its ZeroMQ SDK command and response
endpoints pointed at that daemon. Without `reticulumd`, RCH can serve its
northbound API/UI, but Reticulum messaging, peer discovery, delivery receipts,
and announce operations will not work.

## Highlights Since preview.4

- Added release-candidate stress-gate preparation and bounded `reticulumd`
  bridge connect handling for safer propagated dispatch validation.
- Updated vulnerable dependency locks for the shared UI.
- Added propagation fallback for timed-out broadcasts so delayed direct sends
  can continue through the propagation path instead of ending as avoidable
  delivery failures.
- Added `docs/user-story-status.md` as the canonical RCH user-story ledger,
  with 30 traceable feature rows seeded from the release contract matrix,
  UI routes, release audit, live stress report, and core runtime modules.
- Hardened release-candidate parity around OpenAPI/export aliases, checklist
  mission UID compatibility, Reticulum config path handling, broadcast retry
  state, dashboard stale-card behavior, and control/status synchronization.
- Expanded UI regression coverage for topics, users, mission pages, mission
  audit flows, chat, dashboard state, and mission workspace state.
- Refreshed desktop package metadata to `3.0.0-preview.5` so generated desktop
  artifacts carry the current preview version.

## Validation

The release-prep branch is validated with:

- `cargo fmt --all -- --check`
- `cargo clippy --workspace --all-targets -- -D warnings`
- `cargo test --workspace -- --test-threads=1`
- `cargo test -p r3akt-rch-server`
- `cargo test -p r3akt-rch-core`
- `cargo test -p r3akt-transport-rns`
- `cargo test -p r3akt-tak-connector`
- `cargo build --release -p r3akt-rch-server`
- `pwsh ./scripts/release-readiness.ps1 -ServerOnlyAlpha`
- `npm --prefix ui ci`
- `npm --prefix ui run lint`
- `npm --prefix ui run test`
- `npm --prefix ui run build`
- `npm --prefix apps/rch-desktop install`
- `npm --prefix apps/rch-desktop run build`

GitHub PR validation must pass:

- `Rust PR Quality Control`: Format, Clippy, Workspace Tests, Release Builds,
  and Dependency Audit.
- `Rust workspace`: release-readiness gate.

The GitHub release package workflow is expected to attach release artifacts
after the prerelease publish event completes.

## Known Boundaries

- This remains a preview/alpha release, not stable `v3.0.0`.
- Operator packaging and desktop bundles are still preview artifacts while field
  feedback settles.
- External TAK, Reticulum/RMAP, and live-device gates remain optional evidence
  for this preview unless a blocker appears during release validation.
- Keep Python parity and Rust transition gaps tracked in the repository
  release/readiness documentation.
