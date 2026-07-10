# RCH Rust v3.0.0-preview.7 Release Notes

This prerelease updates the Rust RCH 3.0.0 preview line to the released
LXMF-rs `v0.8.0` runtime and makes ZeroMQ the explicit, lifecycle-managed LXMF
data plane.

Python `2.9.x` remains the stable maintenance line on `rch-python`; this is a
Rust preview intended for validation of the 3.0 runtime, packaging, migration,
LXMF, TAK integration, and local operator desktop path.

## Highlights Since preview.6

- Updated production dependencies to the published LXMF-rs `0.8.0` crates:
  `lxmf-wire`, `lxmf-sdk`, `reticulum-rs-rpc`, and `reticulum-rs-core`.
- Replaced process-global ZeroMQ actors and operation locking with an
  application-owned, lifecycle-managed `ZmqDataPlane`.
- Preserved high-throughput `send_batch` fanout, ordered recipient results,
  partial-acceptance reporting, and durable admission before network delivery.
- Added bounded priority lanes so sends and batch admission take precedence
  over short status and event-poll operations without blocking Tokio request
  workers.
- Added structured ZeroMQ queue, latency, saturation, batch, and partial-result
  diagnostics to the runtime telemetry surface.
- Added ordered SQLite migrations, pre-migration backups, integrity checks,
  query-specific repository access, and controlled incremental compaction.
- Preserved the existing HTTP, OpenAPI, WebSocket, authentication, REM,
  MessagePack, and delivery-policy contracts while integrating the mainline
  first-run setup and kill-switch work.
- Updated release packaging to build and checksum a matching ZMQ-capable
  LXMF-rs `v0.8.0` `reticulumd` sidecar.

## Runtime Boundary

ZeroMQ remains the canonical LXMF message data plane. RPC is optional and
control-only; HTTP delivery and fanout paths do not route messages through
blocking RPC calls. RCH retries only until the SDK accepts work, after which
`reticulumd` owns network scheduling and delivery receipts.

## Validation

The release candidate is gated by formatting, clippy, the full Rust workspace
test suite, locked release builds, desktop metadata validation, capability
negotiation, and local ZeroMQ delivery checks. GitHub release packaging builds
platform archives and attaches them to this prerelease after publication.

## Known Boundaries

- This remains a preview release, not stable `v3.0.0`.
- Operator packaging and desktop bundles remain preview artifacts while field
  feedback and multi-device receipt validation continue.
- Python parity and Rust transition gaps remain tracked in the repository
  release/readiness documentation.
