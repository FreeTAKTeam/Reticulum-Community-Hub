# Idle durable-broker work: issue 276

The [production report](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/276)
identified repeated SQLite connection setup and completed-history lookups in
otherwise empty broker lanes. These are separate from the daemon's propagation
refill and announce-cache work tracked in
[LXMF-rs issue 663](https://github.com/FreeTAKTeam/LXMF-rs/issues/663).

Schema 8 adds partial indexes `rch_broker_dispatch_pending_state(state)` for
`state='pending'` and `rch_broker_inbox_unfinished(journal_id, position)` with
exactly the existing `status NOT IN ('applied','rejected')` predicate. Dispatch retains
rowid admission order; inbox retains journal/position order. The migration uses
the existing backup and immediate-transaction workflow, including a second
version check after acquiring the writer. No payload or history is deleted.

The server retains one configured connection per intake, application and
dispatch owner. SQLite setup runs on a blocking worker under the broker work
gate; each operation also checks the gate and purge state. An exclusive purge
drains the lane-store registry before wiping or unlinking database/WAL files;
joined shutdown also closes retained stores. Announce projection
does not need a local store. Resume, custody-before-ACK, uncertain admission
reconciliation and the existing poll intervals keep their contracts.

This reuses SQLite's [partial-index support](https://www.sqlite.org/partialindex.html)
and the existing joined worker lifecycle, following
[Tokio's shutdown guidance](https://tokio.rs/tokio/topics/shutdown), rather than
adding a shared connection pool or another queue owner.

## Controlled query evidence, 2026-10-15

The regression executes the same SQL constants as the public pending methods.
Costs below are SQLite VM steps, not elapsed time or production CPU estimates.

| Completed history rows | Inbox before | Inbox after | Dispatch before | Dispatch after |
| --- | ---: | ---: | ---: | ---: |
| 32 | 258 | 17 | 105 | 10 |
| 10,000 | 75,018 | 17 | 30,009 | 10 |

After migration both lookups have zero full-scan steps. The new regressions also
exercise the observed 2,392 inbox and 330 dispatch history sizes, unfinished
`error`/`upgrade_required` states, insertion order, state transitions, version-7
upgrade, retained history, a pre-migration backup, and idempotent reopen.

Run `cargo test --locked -p r3akt-rch-core --lib
durable_inbox::pending_lookup_tests -- --nocapture` for the cost and migration
evidence. Server tests exercise actual ZeroMQ-backed worker cycles, connection
reuse and joined shutdown, alongside existing replay and custody regressions.

Final local RCH workspace validation passed 697 tests with two existing ignores,
plus workspace formatting and Clippy with warnings denied. A disposable source
copy using the patched LXMF 0.14.0 workspace also passed all eight paired
durable-broker tests, covering lost ACK and both restarts, replay beyond the old
event window, outbound receipt reconciliation, paused/resumed workers and actual
purge while worker connections are retained. The repository's immutable LXMF
dependency pin is unchanged by that qualification.

## Acceptance boundary

These are local SQLite and socket tests. They do not establish a multi-hour
memory/swap plateau, attribute each historical ZeroMQ timeout, or demonstrate
fresh delivery on the deployed two-core droplet. Production acceptance still
needs the paired daemon fixes, production-shaped database/WAL and announce
inventory, before/after CPU and logical-read measurements, cgroup anon/file/swap
and reclaim counters, and fresh durable inbound/outbound/fanout delivery.
