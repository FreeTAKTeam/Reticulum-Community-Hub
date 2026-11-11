# RCH v3.0.0-preview.38 — matched daemon recovery candidate

<!-- rch-release: linux-amd64-only -->

This candidate pairs LXMF-rs SDK v0.16.2-rc.1 and its bundled daemon at
immutable source `9908a7ef8360db30bb352ca372d70b4d07fbba8b`,
also recorded in config/lxmf-runtime-baseline.json. Publication follows the
qualified upstream release.

## Changes since preview.37

- Recover abandoned negotiated SDK sessions without losing durable custody;
  the existing RCH actor restores its service identity after expiry.
- Warn safely at startup about legacy password and PIN credentials while
  retaining their existing migration on successful verification.
- Include team-scoped mission command encoding and canonical REM team IDs.
- Add shared distance/bearing and calibrated flat-ground camera projection helpers.
- Include the updated rustix security dependency and retain the bounded
  announcement-capability parser from preview.37.

## Upgrade and acceptance

Linux AMD64 archive and Debian installer include the UI, RCH server, TAK service
and matching ZeroMQ daemon. Stop writers and take consistent backups of
configuration, databases, identities and attachments before upgrading. Preserve
credentials and service overrides; installation does not start services.
Restore a compatible backup for rollback instead of opening migrated databases
with an older daemon. Source builds require Rust 1.89 or newer.

Before publication, verify package checksums/source manifests, an actual
preview.37 upgrade preserving state, installed-binary restart and identity,
and peer delivery with durable custody. Exact evidence is added after execution.
Physical radios, production deployment, systemd PID 1 and long-soak/resource
qualification remain separate gates; issue #307 stays open for sustained acceptance.

Candidate packages are uploaded to a draft after verification. Publication may
run the existing package workflow again, but its attachment steps preserve
existing filenames so the qualified package bytes remain unchanged. Published
downloads must still be checked against the candidate digests.
