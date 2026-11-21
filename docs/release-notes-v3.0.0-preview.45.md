# RCH v3.0.0-preview.45 — picture images as binary (no dispatch stall)

<!-- rch-release: linux-amd64-only -->

This Linux AMD64 server prerelease keeps LXMF-rs SDK and daemon
`0.16.2-rc.2-linux` at immutable source `0940abb2ab0ea540c8c0d94283304e1c07b8e002`
(unchanged from preview.44), also recorded in config/lxmf-runtime-baseline.json.

## Changes since preview.44

- Picture-marker answers (`mission.marker.picture.get`) and thumbnail team
  relays now carry LXMF field 6 as MessagePack binary instead of a JSON array
  of byte values. An image larger than about 64 KB exceeded the daemon's
  65,536-node ZeroMQ decode budget; the daemon refused the dispatch without
  replying and every later outbound message waited behind it. REM decodes
  both forms the same way.
  [#368](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/368)

## Upgrade and limits

The Linux AMD64 archive and Debian installer include the UI, RCH server, TAK
service and matching ZeroMQ daemon. Stop writers and take consistent backups of
configuration, databases, identities and attachments before upgrading. Preserve
credentials and service overrides; installation does not start services.
Restore a compatible backup for rollback instead of opening migrated databases
with an older daemon. Source builds require Rust 1.89 or newer.

A hub already stalled by an oversized picture answer keeps that queued
intent after upgrading: mark it rejected (`state='terminal'`,
`receipt_status='rejected'` in `rch_broker_dispatch`) with the server stopped.

Physical radios, a real REM peer, production deployment, and sustained load or
long-soak qualification are separate tests.
