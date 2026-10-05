# Issue #242 resource efficiency

Issue [#242](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/242)
reports high CPU, approximately 1 GiB of RCH memory and reclaim pressure on a
2 CPU / 2 GiB deployment with preview.12 and reticulumd rch241.2. This change
addresses two measured history-dependent costs. Production CPU attribution and
qualification under the reported memory limit remain open.

## Cause and change

Every nonempty RCH announce batch previously decoded the entire saved announce
history and copied it into temporary domain snapshots. Runtime diagnostics
loaded history twice and sorted all records to return ten. With 100,000 retained
announces, even a small batch incurred work proportional to historical state.
Imports now load only the batch's peer keys, retaining domain classification,
first-seen timestamps and unchanged-record behavior. Diagnostics uses indexed
counts, timestamps and identity membership, decoding at most ten payloads.
Subscriber destination and announced-identity aliases retain their existing
normalization and duplicate-count behavior, with a consistent read transaction.

The daemon's completed propagation-mark predicate uses `LOWER(peer)`, while its
existing index starts with the raw peer. SQLite scanned the mark table for each
lookup. LXMF-rs commit `67e63710986111fbf671dd3cf823d57615f8596f` adds a
nonunique expression index on `(LOWER(peer), transient_id, state)`. The query,
terminal states, mixed-case aliases and original rows remain unchanged. RCH's
Cargo dependencies and existing CI/release workflow pins use this exact commit.
This is a demonstrated SQL cost, not proof that it caused the production CPU
spike. A Tokio worker thread name alone cannot distinguish async reactor work
from Tokio blocking-pool work.

## Database upgrade and downgrade

RCH schema 4 adds timestamp and normalized-identity projections. An existing
schema-3 database is backed up to `<database>.pre-migration-v4.bak` before upgrade.
The backfill streams payloads in one transaction, preserves their original
bytes, and records schema 4 only after success. Malformed payloads abort the
migration and roll back schema/index/version changes; repair the source data
rather than deleting history. Row writes, snapshots and the Rust offline Python
importer all use the same projection writer.

Stop every RCH writer before upgrading. Mixed-version writers sharing one
SQLite database are unsupported. Payload-only inserts/replacements from older
RCH versions are rejected so new readers cannot trust incomplete projections.
Keep the backup and sufficient free disk for the backup, indexes and migration
journal. Downgrade only with all services stopped and by restoring the pre-v4
backup; this discards writes made since the backup. Do not strip columns or
recreate history to downgrade.

The daemon index is created by its existing transactional schema initializer.
It requires writable storage and extra disk. A synthetic one-million-mark
fixture added approximately 118.6 MB and built the index in 612 ms locally;
production startup time is unmeasured. No RCH or daemon history retention rule
changes.

## SQL qualification

The exact daemon predicate was measured with SQLite 3.46.1 and synthetic mark
state. Answers for 15 terminal/negative/mixed-case cases and the ordered logical
row digest were unchanged after indexing.

| Mark rows | Original median lookup | Indexed median lookup |
| --- | ---: | ---: |
| 10,002 | 0.673 ms | 0.00418 ms |
| 100,002 | 8.992 ms | 0.00423 ms |
| 1,000,002 | 95.063 ms | 0.00513 ms |

At 100,002 rows the 1,024-lookup batch fell from 9,223.1 ms to 4.19 ms. The
compiled Rust regression requires an indexed `SEARCH` for the exact production
query and verifies legacy reopen, nonunique aliases and unchanged records.

## Runtime qualification method

The local baseline uses the published preview.12 server from source
`9380e39687047e84ee645c3a961abe3b3855d351`, binary SHA-256
`b9b009207467bc1dd04f850e31351a884f69dc3593406075572e3588511c673c`, and
the published rch241.2 daemon from source
`bbde8f2ce35eef8e5a4d99042faed38c6b8fbf68`, binary SHA-256
`c6f883be2c2cbf2fee9f6ecdef89d2f28682336a04e63a1eac427dd651aa7d63`.
The candidate uses the working RCH fix (server SHA-256
`d56231b933a72c521ec947236ee471b141c237fdeaada9ac0c5816fde0cdcf99`)
and LXMF-rs `67e6371`; its daemon SHA-256
is `f968e0a209429a3450bf9af61a525021a521219523e6c263ec6760b3025a0e47`.
These candidate binaries have not been published as a new prerelease.

Both fixtures retain 100,000 synthetic announce payloads, initially 551 fresh
and the remainder at least a day old. Three real TCP-connected daemons run with
propagation enabled, five-second transport announces and 60-second node
announces. RCH polls ZeroMQ events every 100 ms. Each fixture uses two Tokio runtime
workers and identical two-CPU affinity on the same Intel Core Ultra 7 165H host
(Linux 7.0.0-34, glibc 2.43). No 2 GiB memory cgroup is enforced. The daemon
runtime databases are small; the separate SQL probe supplies large mark state.
Build activity and overlapping fixtures can affect timings and host swap.
The baseline fixture supplied an overlong path to the unused Unix RPC listener;
it failed at startup. TCP readiness and ZeroMQ traffic remained available. The
candidate uses a short Unix socket path. This auxiliary listener is not part of
the compared traffic. The baseline harness also needs independent final-report
verification because its report serializer used the wrong direction field;
application delivery and raw-history evidence are verified separately. All
100,000 seed payloads were regenerated byte-for-byte and bound to the first
runtime timestamp; four distinct fresh inbound records and Delivered receipts
were verified. Baseline child exit codes were not captured, though all owned
processes exited after cleanup. Candidate shutdown codes are checked explicitly.

Each run lasts at least 30 minutes, samples process RSS/PSS/anonymous memory,
swap, CPU and file descriptors approximately every five seconds, and requests
authenticated runtime diagnostics and all daemon readiness endpoints. It
requests authenticated announce roughly every minute, imports four fresh real
messages with SDK delivery receipts, restarts the receiving daemon at minute 20,
and sends another message at minute 21. The final ordered digest verifies all
100,000 original raw payloads survived; persisted inbound messages must contain
every sent marker. Freshness naturally changes during the run.

The five-minute warm-up is excluded from steady resource and latency summaries.
CPU is measured as process CPU-time delta divided by wall time, expressed as a
percentage of one CPU; daemon restart PID transitions are excluded from that
delta. Local budgets are RCH PSS <=256 MiB, each process <=10% of one CPU,
diagnostics/announce p95 <=250 ms, readiness p95 <=100 ms and no steady-state
timeout. These are local qualification targets, not production SLAs.

## Completed local comparison

Both workloads completed 30 minutes (345 baseline and 357 candidate samples).
The steady window starts after minute five. Percentiles use the nearest-rank
method; resource medians and peaks are sampled process values.

| Metric | Preview.12 / rch241.2 baseline | Fixed candidate | Local budget |
| --- | ---: | ---: | ---: |
| RCH median RSS | 706.1 MiB | 139.8 MiB | recorded |
| RCH median / peak PSS | 703.5 / 753.3 MiB | 137.3 / 193.9 MiB | <=256 MiB |
| RCH median anonymous memory | 692.1 MiB | 125.8 MiB | recorded |
| RCH sampled swap | 0 | 0 | recorded |
| RCH CPU, one-core percentage | 11.41% | 1.47% | <=10% |
| Each daemon CPU, one-core percentage | 0.525 / 0.159 / 0.160% | 0.581 / 0.180 / 0.177% | <=10% |
| Diagnostics p95 | 227.7 ms | 4.60 ms | <=250 ms |
| Authenticated announce p95 | 107.5 ms | 108.0 ms | <=250 ms |
| Daemon readiness p95, worst node | 0.99 ms | 0.99 ms | <=100 ms |

The candidate meets every stated local budget. The approximately 80% lower
median RSS and 87% lower RCH CPU establish the effect on this retained-history
fixture; they are not production savings estimates. Authenticated announce and
daemon readiness latency were already within budget on this local baseline.
The daemon CPU spike was not reproduced, so its similar small-fixture runtime
CPU numbers do not establish the expression index's production impact.

Each run had one sampled readiness refusal during the intentional daemon-only
restart, one cursor reset and two event-poll errors confined to that restart.
Imports resumed, subsequent errors stayed flat and the final error was clear.
Each run had four distinct Delivered receipts and fresh persisted inbound
records, including the post-restart and final late messages. No messages were
quarantined. All 100,000 original payloads were regenerated byte-for-byte and
verified; the candidate pre-v4 backup also passed integrity/count/digest checks.
Candidate current and retired daemon/RCH processes all exited with code zero.
Baseline shutdown codes are unavailable because of the disclosed serializer
error. Candidate source hashes and live process images were independently bound
to the recorded binary hashes; moving a regression test to satisfy module
budgets produced an identical stripped server binary.

## Source validation and retained evidence

The committed `scripts/release-readiness.ps1 -ServerOnlyAlpha` runner passed on
Rust 1.88: formatting, workspace clippy with denied warnings, 698 workspace
tests, denied-warning documentation, document links, optimized server build and
HTTP smoke. One external-load test remains ignored in that standard workspace
suite; the explicit three-daemon qualification supplies the bounded live proof.
The four release-critical backend package suites also passed. LXMF-rs's full
RPC suite passed all 759 tests, with formatting, RPC all-target clippy, boundary
and module-size checks. Independent POST review found no source blockers.

Local evidence is retained under the ignored `target/issue242/` directory:
release/backend/daemon test logs, immutable candidate binaries, source-file hash
manifest, baseline/candidate fixture scripts, raw samples and SQLite state,
receipt output, independent audits, and the SQL probe script/results. These are
local qualification artifacts, not committed production data or public release
assets. Published preview.12 and rch241.2 assets remain historical baselines.

## Remaining production evidence

The exact production SQLite state, allocation profile, symbolized daemon CPU
profile and original network workload are unavailable. The production report's
2 GiB reclaim/swap behavior and high daemon CPU cannot be certified from the
local fixture. Full-history public listing, REM roster enrichment and some message alias
lookups still have
history-dependent work; a baseline authenticated `/Client` probe took 274 ms
with this fixture. Those paths are outside this bounded correction and require
separate workload measurements before changing their alias-selection behavior.
Keep #242 open until deployment measurements establish its production
acceptance. Do not erase the existing databases to obtain a lower memory result.
