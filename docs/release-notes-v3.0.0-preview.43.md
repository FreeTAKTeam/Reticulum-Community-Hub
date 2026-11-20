# RCH v3.0.0-preview.43 — LXMF-rs 0.16.2-rc.2-linux (RPP 0.3)

<!-- rch-release: linux-amd64-only -->

This Linux AMD64 server prerelease pairs RCH with LXMF-rs SDK and daemon
`0.16.2-rc.2-linux` at immutable source `d9595383b253b1c5022ab5abeacd39ea60b132dd`
(unchanged from preview.42), also recorded in config/lxmf-runtime-baseline.json.

## Changes since preview.42

- Mission Library fetch over RPP packages attachments kept in the database
  (`rch-db:N`, such as LXMF marker pictures) and answers `file_unavailable`
  for a file the hub cannot read, instead of an internal error that held every
  later inbound message in the inbox.
  [#361](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/361)

## Upgrade and limits

The Linux AMD64 archive and Debian installer include the UI, RCH server, TAK
service and matching ZeroMQ daemon. Stop writers and take consistent backups of
configuration, databases, identities and attachments before upgrading. Preserve
credentials and service overrides; installation does not start services.
Restore a compatible backup for rollback instead of opening migrated databases
with an older daemon. Source builds require Rust 1.89 or newer.

Operators upgrading from Python RCH should check that every Library attachment
path is absolute and readable by the service user; RPP serving answers
`file_unavailable` for those that are not.

Physical radios, a real REM peer, production deployment, and sustained load or
long-soak qualification are separate tests.
