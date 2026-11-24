# RCH v3.0.0-preview.46 — Fabric 0.17.0 (LXMF events to REM)

<!-- rch-release: linux-amd64-only -->

This Linux AMD64 server prerelease moves the SDK and daemon to
Fabric (formerly LXMF-rs) `v0.17.0` at immutable source
`99fc770e83ed56eec81a23d8b4b864fe2cfde80e`, also recorded in
config/lxmf-runtime-baseline.json. The Fabric repository and crate names are
unchanged.

## Changes since preview.45

- SDK and bundled `reticulumd` daemon move from LXMF-rs `0.16.2-rc.2-linux`
  (`0940abb2ab0ea540c8c0d94283304e1c07b8e002`) to Fabric `v0.17.0`.
- Events (`mission.registry.log_entry.upsert`) arriving over LXMF are relayed
  to the team with the same REM command shape as the REST fanout, so REM
  stores them as events. The sender's announced name is used as callsign when
  none is given. When the message also carries telemetry, its latitude and
  longitude become the event position: stored on the log entry, returned by
  the API, sent to REM and shown on a new RCH web map event layer.
  [#369](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/369)
- `url` 2.5.8 -> 2.5.9 for RUSTSEC-2026-0592.

## Upgrade and limits

The Linux AMD64 archive and Debian installer include the UI, RCH server, TAK
service and matching ZeroMQ daemon. Stop writers and take consistent backups of
configuration, databases, identities and attachments before upgrading. Preserve
credentials and service overrides; installation does not start services.
Restore a compatible backup for rollback instead of opening migrated databases
with an older daemon. Source builds require Rust 1.89 or newer.

Physical radios, a real REM peer, production deployment, and sustained load or
long-soak qualification are separate tests.
