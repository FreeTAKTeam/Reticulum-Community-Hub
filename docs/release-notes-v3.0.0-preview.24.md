# RCH v3.0.0-preview.24 — durable broker and ZeroMQ resource stability

Full-platform testing candidate for the idle durable-broker resource churn in
[RCH #276](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/276)
and paired LXMF-rs polling and response lifecycle work in issues
[#663](https://github.com/FreeTAKTeam/LXMF-rs/issues/663),
[#657](https://github.com/FreeTAKTeam/LXMF-rs/issues/657), and
[#655](https://github.com/FreeTAKTeam/LXMF-rs/issues/655).

## Changes

- Add schema 8 partial indexes for pending dispatches and unfinished inbox
  events. Migration backs up the existing database, preserves completed
  history, and keeps the established event order and state predicates.
- Keep intake, application, and dispatch SQLite connections with their worker
  owners across idle cycles instead of reopening and migrating on each pass.
  The exclusive purge closes retained connections before wiping or unlinking
  database files, and joined worker shutdown closes them as well.
- Pair the RCH durable-broker changes with LXMF-rs 0.14.0 and the
  `reticulumd-test-0.14.0-issue663.1` daemon build, which carries the related
  bounded, indexed 128-candidate propagation refill transactions and an
  unchanged announce-cache fast path. SDK, workflow checkouts and bundled daemon
  share immutable source `c2174f3295240dd3f171c41310effed7416f0949`.
  Review of #655 found no separate
  SDK client defect requiring an additional workaround.
- Set the server workspace minimum Rust version to 1.88, matching the paired
  LXMF-rs dependency.

## Upgrade and test

Back up the RCH and daemon databases, identities, and configuration before
upgrading. Verify the package SHA-256 sidecar, then install the server and
matching daemon from the same archive. Retain the configured ZeroMQ endpoints
and daemon `--zmq-durable-broker` mode. Check `/Status` and
`/diagnostics/runtime` after startup, then send a fresh message and verify its
stored, applied, and receipt states.

The prepublication local RCH workspace run passed 697 tests with two existing
ignores; the paired durable-broker suite passed eight tests, including lost-ACK
recovery, replay, receipt reconciliation, paused/resumed workers, and purge
while idle worker connections were retained. Final validation against the
published LXMF pin and release-platform packages remains part of this
candidate's release checks.

## Scope and remaining acceptance

The release workflow owns the five server archives and two desktop packages,
with individual SHA-256 sidecars. Server archives include the RCH server, TAK
service, shared UI, and matching ZeroMQ daemon; the embedded manifest records
the source revision and daemon checksum.

Local SQLite, socket, replay, and lifecycle tests do not establish sustained
production memory or swap behavior, fresh delivery on the deployed two-core
host, or physical power-loss recovery. Multi-hour production-shaped load,
hardware acceptance, and live client delivery remain outstanding.
