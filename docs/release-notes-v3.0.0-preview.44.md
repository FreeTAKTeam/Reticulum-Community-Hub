# RCH v3.0.0-preview.44 — LXMF-rs 0.16.2-rc.2-linux (ZeroMQ fair-queue fix)

<!-- rch-release: linux-amd64-only -->

This Linux AMD64 server prerelease pairs RCH with LXMF-rs SDK and daemon
`0.16.2-rc.2-linux` at immutable source `0940abb2ab0ea540c8c0d94283304e1c07b8e002`,
also recorded in config/lxmf-runtime-baseline.json.

## Changes since preview.43

- The SDK and daemon move to LXMF-rs `0940abb`, which fixes the ZeroMQ fair
  queue that could spin the `rch-lxmf-zmq-data-plane` thread at 100% CPU and
  stop the durable inbox after picture-marker traffic. Broker lane failures are
  now logged instead of being dropped silently.
  [#363](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/363)
- Attachment file IDs are never reused after a delete, and deleting a file
  clears the marker-picture references to it, so a picture marker can no longer
  serve another picture's bytes. No database migration is needed.
  [#365](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/365)

## Upgrade and limits

The Linux AMD64 archive and Debian installer include the UI, RCH server, TAK
service and matching ZeroMQ daemon. The daemon changes in this release, so
restart it together with the server. Stop writers and take consistent backups of
configuration, databases, identities and attachments before upgrading. Preserve
credentials and service overrides; installation does not start services.
Restore a compatible backup for rollback instead of opening migrated databases
with an older daemon. Source builds require Rust 1.89 or newer.

Marker-picture references that already point at a reused file ID are not
repaired by this release.

Physical radios, a real REM peer, production deployment, and sustained load or
long-soak qualification are separate tests.
