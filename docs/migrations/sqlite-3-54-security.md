# Bundled SQLite security alignment

Current source builds pair LXMF-rs `0.16.1` at immutable source
`9b972f9a8d3a7949eae89bc78f7a9691f06f3ed1` with RCH's direct `rusqlite 0.41.1`.
The single native `libsqlite3-sys 0.39.1` bundles SQLite 3.54.1 and satisfies
[RUSTSEC-2026-0459](https://rustsec.org/advisories/RUSTSEC-2026-0459.html)
(CVE-2026-119375), whose patched range starts at native library 0.39.0.
No advisory exception is added. The old wrapper requires a different native
`links = "sqlite3"` version, so both direct and paired dependencies must move
together. Existing `bundled`/`backup` features and LXMF's `hooks` remain enabled.

The wrapper raises the current workspace and desktop minimum to Rust 1.89.
The locked MSRV job and current check instructions follow it. Existing Rust
1.99.1 quality, release and Debian build pins remain unchanged. Dated Rust 1.88 /
SQLite 3.53.2 results and versioned release notes retain their original attribution.
SDK version 0.16.1 and the null runtime release tag do not imply a new release.

This is source/lock preparation, not native qualification. The RCH schema remains 9.
This change does not edit RCH SQL, payload formats, backup policy or application
runtime logic. Patched-engine validation must still exercise schema 7/8 upgrades
and backups, active-count results/work, broker regressions and affected strict
checks. In particular the upstream backup/restore changes require the existing
migration coverage. Earlier
engine VM-step figures and sustained-run results do not qualify SQLite 3.54.1.
Exact paired runtime qualification is recorded separately on
[PR #304](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/304).
