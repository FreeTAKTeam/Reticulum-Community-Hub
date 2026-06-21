# RCH Rust v3.0.0-preview.4 Release Notes

This prerelease refreshes the Rust RCH 3.0.0 preview line for LXMF-rs
`reticulumd` `v0.5.1`.

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

## Highlights Since preview.3

- Pinned RCH release and PR workflows to LXMF-rs `v0.5.1`.
- Added LXMF roster command semantics in the plain LXMF command path and help.
- Added roster-backed group chat fanout with canonical inbound records and a
  shared outbound payload boundary.
- Optimized group fanout so RCH builds one shared outbound payload and leaves
  only per-recipient transport wrapping to LXMF-rs.
- Fixed LXMF peer routing around stale announces, recent chat presence, and
  propagation fallback so dead roster entries do not produce avoidable
  `peer_not_announced` failures.
- Fixed relayed group chat display text so inbound relays use the original
  sender display name instead of a topic prefix.
- Refreshed desktop package metadata to `3.0.0-preview.4` so generated desktop
  artifacts carry the current preview version.

## Validation

The release-prep commit was validated locally with:

- `cargo fmt --all -- --check`
- `cargo clippy -p r3akt-rch-server --all-targets -- -D warnings`
- `cargo test -p r3akt-rch-server --lib -- --test-threads=1`
- `cargo test --workspace -- --test-threads=1`

GitHub PR validation for the merged LXMF routing fixes passed:

- `Rust PR Quality Control`: Format, Clippy, Workspace Tests, Release Builds,
  and Dependency Audit.
- `Rust workspace`: release-readiness gate.

The GitHub release package workflow is expected to attach release artifacts
after the prerelease publish event completes.

## Known Boundaries

- This remains a preview/alpha release, not stable `v3.0.0`.
- Operator packaging and desktop bundles are still preview artifacts while field
  feedback settles.
- Keep Python parity and Rust transition gaps tracked in the repository
  release/readiness documentation.
