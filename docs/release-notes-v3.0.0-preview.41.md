# RCH v3.0.0-preview.41 — LXMF-rs 0.16.2-rc.2-linux

<!-- rch-release: linux-amd64-only -->

This Linux AMD64 server prerelease pairs RCH with LXMF-rs SDK and daemon
`0.16.2-rc.2-linux` at immutable source `4dc89a4afd54b8653ee9236b62d5d1f720b484bf`, also recorded in
config/lxmf-runtime-baseline.json.

## Changes since preview.40

- Picture markers carry LXMF `FIELD_IMAGE` thumbnails.
  [#343](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/343)
- The broker skips unchanged announce sweeps, counts inbox status
  incrementally and keeps only moderated identity states resident.
  [#342](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/342)
- Map graphics acceptance for RCH and REM sensor FOV and SPI is documented.
  [#340](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/340)
- The bundled daemon moves to LXMF-rs `v0.16.2-rc.2-linux`: legacy MeshChat
  history import, eligible-only announce retention and an `rnsh` teardown fix.

## Upgrade and limits

The Linux AMD64 archive and Debian installer include the UI, RCH server, TAK
service and matching ZeroMQ daemon. Stop writers and take consistent backups of
configuration, databases, identities and attachments before upgrading. Preserve
credentials and service overrides; installation does not start services.
Restore a compatible backup for rollback instead of opening migrated databases
with an older daemon. Source builds require Rust 1.89 or newer.

Physical radios, a real REM peer, production deployment, and sustained load or
long-soak qualification are separate tests.
