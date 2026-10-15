# RCH v3.0.0-preview.25 — desktop durable-broker launch correction

Preview.25 carries the durable-broker resource-stability work from
[preview.24](release-notes-v3.0.0-preview.24.md) and fixes the desktop sidecar
launch configuration found during post-publication package inspection.

## Changes

- Retain preview.24's schema 8 indexes for pending dispatches and unfinished
  inbox events, with additive migration backups and preserved completed history.
- Keep intake, application, and dispatch SQLite connections with their worker
  owners across idle cycles. Purge closes retained connections before wiping or
  unlinking database files, and joined worker shutdown closes them as well.
- Pass `--zmq-durable-broker` when the Tauri desktop launcher starts its managed
  `reticulumd` sidecar, matching the durable ZeroMQ mode used by server packages.
- Bridge the configured local identity into broker-only daemon startup. This mode
  does not create transport interfaces or listeners.
- Keep the paired LXMF-rs 0.14.0 daemon at immutable revision
  `9c8bc7b52c4ed5eeb94716247b900864d812fcb6`
  (`reticulumd-test-0.14.0-issue663.2`) and Rust 1.88 minimum.

## Upgrade and test

Preview.24's desktop artifacts did not enable durable broker mode for the
managed daemon, and broker-only startup did not bridge the configured local
identity. Install the preview.25 desktop package and matching server/daemon
artifacts together. Verify the SHA-256 sidecars and confirm the managed daemon
starts with `--zmq-durable-broker`; then check `/Status`,
`/diagnostics/runtime`, and a fresh message receipt.

Preview.24's prepublication local RCH workspace run passed 697 tests with two
existing ignores, and the paired durable-broker suite passed eight tests,
including lost-ACK recovery, replay, receipt reconciliation, paused/resumed
workers, and purge while idle worker connections were retained. Preview.24's
full-platform packaging run completed all seven jobs, but the desktop launcher
flag omission was discovered after publication. Preview.25 release checks and
package verification remain required for this correction.

## Scope and remaining acceptance

The full release matrix contains five server packages and two desktop packages,
each with an individual SHA-256 sidecar. Local SQLite, socket, replay, and
lifecycle tests do not establish sustained production memory or swap behavior,
fresh delivery on the deployed two-core host, or physical power-loss recovery.
Multi-hour production-shaped load, hardware acceptance, and live client
delivery remain outstanding.
