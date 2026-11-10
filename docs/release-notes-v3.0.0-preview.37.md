# RCH v3.0.0-preview.37 — Linux AMD64 testing release

<!-- rch-release: linux-amd64-only -->

This preview includes RCH changes merged through `6aa061ffae10c235885b20129c6049e994dca8ef` and pairs LXMF-rs SDK 0.16.1 with a ZMQ-capable daemon built from the same source, `9b972f9a8d3a7949eae89bc78f7a9691f06f3ed1`. No upstream release tag is asserted for this source-built pairing. RCH builds the daemon with Tokio 1.53.3 for Debian 12 compatibility.

## Changes since preview.36

- Keep markers without a stored expiry visible instead of treating their update time as expiry ([#306](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/306)). The marker store does not persist expiry, so the accepted `ttl_seconds` input still has no effect.
- Provide a shared R3S object-message encoder, including position-only updates ([#309](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/309)).
- Bound untrusted announcement capability parsing to prevent oversized MessagePack allocations, while preserving announce ingestion for invalid optional capabilities ([#310](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/310)). The separate SDK session-lifecycle issue is not resolved by this fix.
- Keep the saved hub name and service announcements consistent ([#300](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/300)) and show inbound group chat in the correct Broadcast or topic conversation ([#301](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/301)).
- Retry durable-worker startup after recoverable storage errors ([#303](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/303)); add the active-dispatch index, update the paired LXMF source, and align bundled SQLite with the security fix ([#304](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/304)).

## Packages and upgrade

The Linux AMD64 server archive and Debian/Ubuntu installer include the shared UI, server, standalone TAK service, and matching daemon. SHA-256 files accompany both packages. Other architectures and desktop bundles are outside this candidate's scope. Installation does not start services automatically; see the [Debian package guide](../packaging/README.md#debian-amd64-installation).

Stop services and take SQLite-consistent backups of configuration, identities, databases, and attachments before upgrading. Preserve credentials, interfaces, and systemd overrides. The RCH database upgrades to schema 9, and the daemon's dispatch-index migration can add startup I/O and disk/WAL usage. Do not open a migrated database with an older daemon for rollback; restore a consistent backup. Announce-history retention can remove older history.

This is preview software. Package qualification is pending until performed. Physical-radio and real-peer operation, sustained resource/load stability, production deployment, and systemd PID 1 acceptance remain separate gates; see the [readiness audit](release-readiness-audit.md).
