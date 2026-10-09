# Durable ZeroMQ cutover

RCH requires the LXMF-rs revision pinned in Cargo manifests, Cargo.lock and all
LXMF_REF workflow values. A managed daemon receives `--zmq-durable-broker`;
start a separately managed daemon with that flag explicitly. The existing
PUSH/PULL or ROUTER/DEALER endpoints retain their configuration.

RCH does not maintain a legacy polling/history-import or outbound retry owner.
The local SQLite inbox commits custody before `ack_stored`, then one ordered
worker commits business changes, completion and generated delivery intents in
the same transaction. Stable outbound operations reconcile uncertain daemon
admission before retry. `DaemonStored`, `RchStored`, `RchApplied`/`RchRejected`
and network `Delivered` remain separate states.

Before cutover, stop new sends/intake, drain or record the old retry queue, stop
both services, and make consistent backups of databases, identities and the RCH
state directory. Do not copy a live main SQLite file alone. The additive schema
migration backs up existing RCH data. Bootstrap events preserve historical rows
without executing old commands or replaying old relays. One RCH process owns a
state directory, enforced by a separate SQLite lease.

Paired LXMF-rs source: `e237f80c0c9e219e4090be04a4229d3328074f73`
merged into Framework `main` by PR #660. Cargo dependencies and managed
daemon builds use this same immutable revision.

The daemon physical budget is persisted on first enablement. Its main database
page cap uses one quarter of the selected budget to leave WAL and control
headroom; an oversized existing database refuses cutover. Use a sufficient
initial `--zmq-broker-budget-bytes` when starting a separate daemon. Shared daemon writers enforce the admission bound; external
writable connections and old binaries must not share its database.

RCH bounds inbox/outbox and presentation separately. Unknown required event
versions pause ordered application for upgrade. Malformed recognized inputs
retain original payload/reason as durable rejections. Storage pressure reports
errors and retries; it never acknowledges uncommitted inbox data.

Use `/Status` and `/diagnostics/runtime` together. Inspect broker lane errors,
stored/applied positions, pending/rejected counts and dispatch operation IDs.
HTTP 200 is insufficient acceptance evidence. Prove a unique `Test1234` through
custody, application and an actual receipt on the target deployment.

A restored daemon database must be declared once using
`--zmq-broker-restored` (with `--zmq-durable-broker`). It rotates journal
incarnation and invalidates old issued receipts. A journal mismatch or daemon
checkpoint ahead of restored RCH custody reports `RecoveryRequired`; there is
no silent tail adoption or automatic reconstruction of a lost interval.
Restore a coherent pair or perform an explicitly reviewed recovery. Do not
point old binaries at migrated databases; rollback uses pre-cutover backups
and reconciliation of work admitted after that backup.

Full daemon contract, limits and recovery details are maintained in LXMF-rs:
[OPERATIONS.md](https://github.com/FreeTAKTeam/LXMF-rs/blob/e237f80c0c9e219e4090be04a4229d3328074f73/docs/goals/zmq-rch-durable-broker/OPERATIONS.md).
Local socket, SQLite, crash and paired-worker tests do not establish hardware
power-loss behavior or a production multi-hour memory/swap plateau.
