# Issues #252 and #255 validation evidence

Base: `f2e90c4826dc944134b2fe4339009fda3eeb01a1`. Branch:
`corvo/issues-252-255-bounded-persistence`. Dependency pins and release packaging
are unchanged. The original checkout and its unrelated `design-qa.md` are preserved.

## Contract and policy

The user approved 500 messages, 32 MiB estimated residency, and 30 minutes of
inactivity, with queued/retrying/admitted/pending-receipt work remaining in bounded
durable workers. History remains in SQLite. Startup activity comes from a persisted
scalar projection; runtime activity uses a monotonic clock. Eviction occurs on
publication, diagnostics reads, or maintenance ticks (at most 30 seconds after the
idle deadline). History reads do not depend on presentation residency.

Command selection is split into seeds, relationship dependencies, authority/routing,
and merge modules. Commands reuse the domain owner; they do not duplicate business
validation. Incremental hydration preserves staged updates and deletions. Authority
is resolved after merging staged membership and target scope. SQLite reservation,
command results, audits, changed-row writes and durable intents retain their atomic
boundary; projection publication follows commit. Legacy broad constructors remain
explicit compatibility/test adapters, absent from production HTTP command selection.

## Deterministic checks

Regression coverage includes response parity across registry/checklist families,
checklist cells in mission expansion, filtered lists, unchanged unrelated/corrupt
history, destination collision rejection, staged member denies, global REM mode
summaries, concurrent field updates, atomic rollback, and migration decode failure.
Message tests cover count/byte/age bounds, compatibility rebuild activity, durable
history filters/order/attachments after eviction and restart, unresolved admission,
and late delivery receipts. Broker tests preserve an earlier accepted command and
its responses when a later envelope is rejected.

Final validation passed: `cargo fmt --all -- --check`, strict workspace/all-target
Clippy, workspace tests (728 passed, 2 existing ignored), and the committed
`release-readiness.ps1 -ServerOnlyAlpha` runner. The runner repeated the tests,
built release binaries/docs, checked document links, and passed authenticated HTTP
smoke, including `/Status` and `/diagnostics/runtime`. Workspace tests include
core (108), server (390), transport (64), TAK (58), and bridge (14) unit tests,
plus their integration suites. No hosted CI or PR publication is part of this run.

## Reproducible local measurement

Use the committed `resource_fixture` and `persistence_probe` core examples against
new databases, with 100 and 25,000 announces/messages. Fixtures use current typed
writers. The probe repeatedly hydrates the bounded recent window and patches one
mission, recording decoded rows/payload bytes, residency and Linux process RSS.
The large run uses 5,000 iterations. This is a deterministic local soak, not a
production mesh or physical-client soak.

A separate temporary measurement harness wraps the same probe in an allocation-free
atomic counting allocator over `std::alloc::System`. The repository forbids unsafe
code, so allocator instrumentation is kept outside the repository and does not
alter that policy. Its peak counts requested live Rust allocation bytes above the
pre-command baseline, including selected snapshots and result encoding; it excludes
SQLite's C allocations and allocator overhead. Process RSS covers the whole process.

Current-source results, 5,000 iterations per fixture:

| Fixture | Decoded command rows | Command payload bytes | Peak requested Rust allocation per command | Peak process RSS | Resident messages |
| --- | ---: | ---: | ---: | ---: | ---: |
| 100 messages / announces | 1 | 305 | 25,846 B | 28,088 KiB | 100 |
| 25,000 messages / announces | 1 | 305 | 25,846 B | 29,928 KiB | 500 |
| Above plus 25,000 unrelated missions and 5,000 same-actor unrelated rights | 1 | 305 | 25,846 B | 30,008 KiB | 500 |

The large caches retained at most 4,448,700 estimated bytes. The registry-scale
fixture copied the typed history database, inserted valid named MessagePack mission
and right records with matching scalar keys, and cleared only the previous probe
command-result keys so every measured request executed its mutation. History/audits
were retained. Allocation and decoded-row cost remain identical across the fixtures.
All samples, fixture metadata and external-harness source hashes are preserved in
[measurements.json](measurements.json).

The actual release server was started on an isolated copy with 25,000 messages.
After startup and 30 authenticated durable chat reads it reported 500 resident
messages, 4,448,700 estimated bytes, all 25,000 messages in history, zero active
fixture dispatch operations, and 500 cache insertions. RSS ranged from 37,612 to
37,860 KiB. It shut down gracefully. This confirms local startup/history/cache
behavior; no production-duration or mesh soak claim is made.

## Review and environment

PRE review completed before implementation. Independent correctness/maintainer
review found staged authority, cell expansion, destination collision, filtered list,
multiple-envelope isolation and cache-activity rebuild gaps; each was corrected
with focused coverage. Latest source review found no further concrete blocker.
Final gates and measurements passed; POST review is recorded below.

A temporary-directory quota exhausted during a validation attempt. Only generated
files from this task were archived into an ignored validation directory and then
disposed after the successful rerun. Final gates
use an isolated `TMPDIR` below `target/rch-252-255-validation`; no unrelated files,
build artifacts or sibling repositories were cleaned. External TAK/Reticulum live
and physical-device acceptance are not run by the server-only gate.

Final POST/correctness/maintainability review approved the scoped local evidence
lane. The reviewer independently matched all three probe outputs and the release
runtime output to measurements.json, verified 728 passed / zero failed / two ignored
workspace results and the terminal readiness completion, and found no remaining
important source or evidence blocker. Hosted CI, external mesh, and physical-device
acceptance remain outside this local lane.
