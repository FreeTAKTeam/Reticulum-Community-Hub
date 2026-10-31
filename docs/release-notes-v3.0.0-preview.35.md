# RCH v3.0.0-preview.35 — consolidated Linux AMD64 release

<!-- rch-release: linux-amd64-only -->

This preview includes all RCH changes merged through `b3931fc3896423c99f1e9b6f848906266065bda6`, including R3S sensor telemetry, non-REM marker delivery, persistent offline marker recipients, and daemon announce reconciliation. Offline recipients remain eligible for later delivery, and reconciliation uses the daemon's durable announce cursor rather than event delivery alone.

The SDK and bundled ZMQ-capable daemon use LXMF-rs 0.16.0 at `888355c580932f886cfbf9f7076758b065a69879`, the consolidated source for [reticulumd-test-0.16.0-linux-888355c5.1](https://github.com/FreeTAKTeam/LXMF-rs/releases/tag/reticulumd-test-0.16.0-linux-888355c5.1). This includes peer-quota/refill corrections, bounded announce-history retention, and paginated latest-peer reconciliation with a durable cursor. The Ubuntu daemon archive and RCH's Debian-compatible daemon are built for different C runtimes from this same source; their binary checksums differ.

Assets are the Linux AMD64 server archive, Debian/Ubuntu installer, and SHA-256 checksums. The archive includes the shared UI, server, standalone TAK service, and daemon. Other architectures and desktop bundles are outside this release's scope. Preview.34 and older unpublished candidates are preserved.

Stop services and take a consistent backup of configuration, identities, databases, and attachments before upgrading. Preserve existing credentials, interfaces, and systemd overrides. Announce-history retention defaults to 100,000 historical rows plus latest-peer information; it can remove older history. New indexes and catch-up maintenance can add first-start I/O. Installation does not start services automatically. See the [Debian package guide](../packaging/README.md#debian-amd64-installation).

Release qualification is recorded in the [readiness audit](release-readiness-audit.md). This remains preview software; physical-radio/real-peer, sustained-load, deployment, and systemd PID 1 acceptance require separate validation.
