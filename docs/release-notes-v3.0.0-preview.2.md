# RCH Rust v3.0.0-preview.2 Release Notes

This prerelease refreshes the Rust RCH 3.0.0 preview line for LXMF-rs
`reticulumd` `v0.5.0`.

Python `2.9.x` remains the stable maintenance line on `rch-python`; this is a
Rust preview intended for validation of the 3.0 runtime, packaging, migration,
LXMF, and TAK integration path.

## Runtime Requirement

RCH Rust 3.0 requires a running LXMF-rs `reticulumd` instance. The server
package includes the RCH server, TAK service, shared UI, and service templates,
but it does not replace the Reticulum/LXMF daemon. Start and configure
`reticulumd` first, then run RCH with its ZeroMQ SDK command and response
endpoints pointed at that daemon. Without `reticulumd`, RCH can serve its
northbound API/UI, but Reticulum messaging, peer discovery, delivery receipts,
and announce operations will not work.

## Highlights Since preview.1

- Pinned RCH CI and release packaging to LXMF-rs `v0.5.0` for deterministic
  daemon compatibility.
- Routed ZeroMQ SDK event polling through the persistent actor socket so
  response endpoints stay stable across outbound sends and inbound polls.
- Added focused transport coverage for explicit loopback response endpoints and
  event polling after outbound sends.
- Bumped RCH desktop preview metadata to `3.0.0-preview.2` so desktop artifacts
  no longer carry the older preview.0 package version.

## Validation

Local validation on the prepared release commit passed:

- `cargo fmt --all -- --check`
- `cargo clippy --workspace --all-targets -- -D warnings`
- `cargo test --workspace`
- `cargo test -p r3akt-transport-rns poll_lxmf_zmq_events`
- `cargo build --release -p r3akt-rch-server`
- Local YAML parse of the Rust CI/release workflows

The GitHub release package workflow is expected to attach release artifacts
after the prerelease publish event completes.

## Known Boundaries

- This remains a preview/alpha release, not stable `v3.0.0`.
- Operator packaging and desktop bundles are still preview artifacts while field
  feedback settles.
- Keep Python parity and Rust transition gaps tracked in the repository
  release/readiness documentation.
