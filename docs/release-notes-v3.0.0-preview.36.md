# RCH v3.0.0-preview.36 — latest daemon Linux AMD64 release

<!-- rch-release: linux-amd64-only -->

This preview pairs the RCH server with the latest published [LXMF-rs daemon and SDK, v0.16.1-rc.1-linux](https://github.com/FreeTAKTeam/LXMF-rs/releases/tag/v0.16.1-rc.1-linux). Both use immutable source `213af2d8048ded5ff38f67ca8c0b4cc143d19ada`. RCH includes changes merged through `c2bf78adc2795574a5fb8c39e6cdea7e523b7ef0`.

The paired daemon adds Link-MDU-aware propagation retrieval, indexed durable-dispatch retry polling, IFAC credential preservation, and duplicate tracking after carrier acceptance. It also includes bounded announce history and resource-maintenance changes. The experimental SQLite cache release has no completed sustained memory-stability qualification. See the upstream release for the full change list and remaining acceptance limits.

Assets are the Linux AMD64 server archive, Debian/Ubuntu installer, and SHA-256 checksums. The archive includes the shared UI, server, standalone TAK service, and ZMQ-capable daemon. RCH rebuilds the daemon from the same source with Tokio 1.53.3 for Debian 12 compatibility; its checksum differs from the upstream static-musl binary. Other architectures and desktop bundles are outside this release's scope. Older releases and unpublished candidates are preserved.

Stop services and take SQLite-consistent backups of configuration, identities, databases, and attachments before upgrading. Preserve credentials, interfaces, and systemd overrides. The daemon's dispatch-index migration adds one-time startup I/O and disk/WAL usage; do not open a migrated database with an older daemon for rollback. Restore a consistent backup using the upstream migration procedure. Announce-history retention can remove older history. Installation does not start services automatically. See the [Debian package guide](../packaging/README.md#debian-amd64-installation).

Release qualification is recorded in the [readiness audit](release-readiness-audit.md). This remains preview software; physical-radio/real-peer, sustained-load, deployment, and systemd PID 1 acceptance require separate validation.
