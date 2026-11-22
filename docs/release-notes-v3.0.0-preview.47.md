# RCH v3.0.0-preview.47 — events on the web map

<!-- rch-release: linux-amd64-only -->

This Linux AMD64 server prerelease keeps the SDK and daemon on Fabric
(formerly LXMF-rs) `v0.17.0` at immutable source
`99fc770e83ed56eec81a23d8b4b864fe2cfde80e` (unchanged from preview.46), also
recorded in config/lxmf-runtime-baseline.json.

## Changes since preview.46

- The RCH web map event layer now shows events that have a position. It read
  `log_entries` from `GET /api/r3akt/log-entries`, which returns a bare array,
  so the layer was always empty.
  [#372](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/372)

## Upgrade and limits

The Linux AMD64 archive and Debian installer include the UI, RCH server, TAK
service and matching ZeroMQ daemon. Stop writers and take consistent backups of
configuration, databases, identities and attachments before upgrading. Preserve
credentials and service overrides; installation does not start services.
Restore a compatible backup for rollback instead of opening migrated databases
with an older daemon. Source builds require Rust 1.89 or newer.

Physical radios, a real REM peer, production deployment, and sustained load or
long-soak qualification are separate tests.
