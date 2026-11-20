# RCH v3.0.0-preview.42 — LXMF-rs 0.16.2-rc.2-linux (RPP 0.3)

<!-- rch-release: linux-amd64-only -->

This Linux AMD64 server prerelease pairs RCH with LXMF-rs SDK and daemon
`0.16.2-rc.2-linux` at immutable source `d9595383b253b1c5022ab5abeacd39ea60b132dd`, also recorded in
config/lxmf-runtime-baseline.json.

## Changes since preview.41

- A shared mission Library catalog answers mission-scoped LXMF queries and
  serves Library files over RPP 0.3.
  [#359](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/359)
- A `/time` LXMF command reports mission time remaining.
  [#356](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/356)
- The dashboard event feed is redesigned for readability.
  [#357](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/357)
- Marker replays no longer stall the inbox, command claims stay stable across
  LXMF retries, and opaque announce app data is classified instead of
  re-parsed. [#352](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/352)
- The API port availability test is race-free.
  [#353](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/353)
- The bundled daemon moves to LXMF-rs main at `d959538`: RPP 0.3 RC1 engine,
  RNS Resource link admission and RDO owner binding v1.

## Upgrade and limits

The Linux AMD64 archive and Debian installer include the UI, RCH server, TAK
service and matching ZeroMQ daemon. Stop writers and take consistent backups of
configuration, databases, identities and attachments before upgrading. Preserve
credentials and service overrides; installation does not start services.
Restore a compatible backup for rollback instead of opening migrated databases
with an older daemon. Source builds require Rust 1.89 or newer.

Physical radios, a real REM peer, production deployment, and sustained load or
long-soak qualification are separate tests.
