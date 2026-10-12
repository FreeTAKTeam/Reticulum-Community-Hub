# Chat retention and indexed persistence evidence

Status: implementation, independent POST review and all required local checks
passed. Duplicate migration reconciliation policy is still awaiting
the user's choice; that gate prevents declaring both issues complete. No PR,
push, release or physical-network acceptance is claimed.

Branch: `corvo/issues-253-256-chat-indexes`, based on PR #266 head `eb60dd6`.
The original checkout, unrelated files, PR #266 and sibling LXMF checkout remain
preserved. This change has no dependency pin or packaging changes.

## Operator and contract acceptance

The configured presentation owner limits conversation/global messages, estimated
bytes, activity age, suppression IDs and viewport overscan. All defaults reside
in `ui/src/config/chat-retention.json`; validated `VITE_CHAT_*` configuration is
applied at build time. Pending outbound and concurrent send reservations are
protected. Capacity errors are visible before new requests; remotely received
work can be omitted from presentation while remaining durable on the backend.
SDK `sent` with `sdk_terminal:false` remains pending; malformed flags are
rejected explicitly. Completed delivery knowledge survives delayed failures and
bounded tombstones. Oversized completion details release pending protection
without escaping the byte bound. Tombstones can expire or be shed at capacity;
they are bounded presentation metadata, not durable lifecycle truth.

Store tests cover per-conversation/global/byte/age bounds, concurrent admissions,
old receipts, history/live races and stale read/send/upload continuations after
backend/auth scope changes. ChatPage rejects stale hash/upload continuations
before sending; auth revocation clears all private bookkeeping. Resource-specific
403 does not silently log out a valid session.

The additive authenticated `/Chat/History` route pages authoritative broadcast,
topic and direct-peer history using timestamp/integer-ID cursors. Equal timestamp
ordering and case-insensitive updates retain integer IDs. Direct history matches
inbound source and outbound destination, including self messages without duplicate
rows. The original `/Chat/Messages` array contract remains. Python fallback keeps
the newest bounded legacy list and explicitly reports older paging unavailable;
a sparse direct conversation may be absent from that newest global legacy list.

## Actual browser measurements

Real Chromium ran the production Vite build against controlled HTTP/WebSocket
fixtures: 24,000 live events across ten topics, with Topic 0 actively rendered.
The test checks actual Pinia diagnostics without a production test hook, collects
heap after explicit Chromium GC, and counts mounted message cards.

| Events | Retained messages | Largest conversation | Estimated bytes | Suppression IDs | Used JS heap (bytes) | Mounted cards |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4,000 | 2,000 | 200 | 3,111,810 | 2,100 | 5,432,348 | 5 |
| 8,000 | 2,000 | 200 | 3,643,950 | 4,000 | 5,644,660 | 5 |
| 12,000 | 2,000 | 200 | 3,654,030 | 4,000 | 5,541,920 | 5 |
| 16,000 | 2,000 | 200 | 3,659,970 | 4,000 | 5,526,920 | 5 |
| 20,000 | 2,000 | 200 | 3,660,050 | 4,000 | 5,620,276 | 5 |
| 24,000 | 2,000 | 200 | 3,659,990 | 4,000 | 5,629,920 | 5 |

The last four heap samples span 103,000 bytes, below the unchanged 8 MiB test
budget. Older paging loads a 100-message page; Home/End keyboard scrolling keeps
fewer than 40 mounted cards. A live insertion preserves the reading row and its
pixel offset. Measured idle DOM mutations over 500 ms: zero. Route exit closes
the message stream; explicit auth revocation leaves zero messages, bytes and
suppression IDs. The screenshot was visually inspected. These bounded fixtures
show a local plateau, not production-duration traffic or whole-process RSS.

An earlier browser assertion compared absolute scrollTop across height measurement;
it was corrected to reading-row identity and offset, since measured prefixes can
change absolute scrollTop while preserving the operator's reading position.
The strict heap and DOM budgets remain unchanged.

## SQLite measurements

The committed `message_index_probe` example seeded 25,000 typed messages with
4 KiB content across ten topics, then updated/looked up 1,000 identities.
Each fixture used the same transaction batches and checkpoint method. The
baseline is immutable PR #266 head `eb60dd6`, schema 6. Final schema 7 uses partial
conversation indexes matching actual direction/scope queries; broad candidate
indexes were removed after measuring their fixed storage cost.

| Metric | Baseline schema 6 | Final schema 7 |
| --- | ---: | ---: |
| Seed time (ms) | 203,011 | 11,623 |
| 1,000 keyed updates + reads (ms) | 17,448 | 1,204 |
| DB before updates (bytes) | 123,498,496 | 126,754,816 |
| DB after updates (bytes) | 123,543,552 | 126,767,104 |
| DB growth across updates (bytes) | 45,056 | 12,288 |
| Maximum WAL bytes | 4,243,632 | 4,243,632 |
| Final free pages | 8 | 3 |

The final DB is approximately 2.6% larger due to uniqueness/history projections
and indexes. Update growth is 12 KiB versus 44 KiB; maximum WAL is equal. These
single-run dev-profile timings are directional evidence, not a benchmark promise.

Build provenance was checked by schema version and index definitions. A shared
Cargo example alias initially reused the baseline artifact; those measurements
were discarded. Final local crates were rebuilt with `CARGO_INCREMENTAL=0`,
the qualified binary was copied, and schema 7 plus partial-index predicates were
verified before measurement. Registry dependencies and lockfiles were reused.

A copy of the populated 25,000-row baseline migrated in 5,269 ms and reopened
in 3 ms. Length-framed SHA-256 over every integer ID, message ID and raw payload
before/after and in the schema-6 backup was identical:
`3737cb83f10b054c1356098a4df02cd6741432789162e43aa7ef9e2b50c9a55b`.
The fresh/upgrade parity tests compare the complete owned index set. Malformed
payload and duplicate identity tests roll back schema 7; duplicate resolution
is not executed pending policy. Attachment detachment exercises 600 matching
rows in bounded 256-row batches without decoding an unrelated corrupt payload.

Query-plan tests verify NOCASE point lookup, each owned partial history index,
disjoint direct-peer branches and existing topic attachment access. Explicit
`INDEXED BY` prevents the generic visible-chat index from scanning unrelated
history when SQLite favors it on tiny databases. A missing owned index produces
an explicit query failure rather than silently scanning all history; operators
must repair corrupted/externally modified schemas.

## Checks and independent review

- Installed locked UI dependencies: `npm --prefix ui ci` passed.
- UI typecheck, lint, tests and production build passed: 195 tests in 47 files.
- Actual browser suite passed: four tests; replay test 42.9 seconds, suite 50.9 seconds.
- Six focused core migration/index tests passed after partial-index cutover.
- Final committed `release-readiness.ps1 -ServerOnlyAlpha` passed: strict
  workspace Clippy, workspace tests, warnings-as-errors documentation, link
  validation, optimized server build and local HTTP smoke. Core: 114 passed;
  server: 392 passed and two explicit live-network ignores. Workspace testing
  also passed transport and TAK suites. `cargo fmt --all -- --check` passed.
- An earlier full readiness run passed. A later rerun encountered an unchanged
  SDK replay test's 250 ms ZeroMQ timeout under concurrent benchmark/build load;
  its isolated rerun passed without changes or timeout weakening. The final run
  ran without browser/benchmark load and passed, including that SDK replay.
- Independent source reviewer checked cache, lifecycle/scope disposal, variable
  height viewport, migration, index predicates and contracts. Findings were
  corrected, including SDK terminal metadata handling. Final POST/evidence review
  approved the implemented local acceptance lane after independently comparing
  every populated database row and raw payload with the backup. Duplicate policy
  remains the sole completion gate for this requested implementation scope.

Ignored local artifacts are retained under
`target/rch-253-256-validation/`: `baseline-probe.json`, `partial-probe.json`,
`populated-partial-upgrade.json`, corresponding SQLite fixtures/backups and gate
logs. Browser samples and screenshot live in the worktree's
`ui/test-results/chat-retention-sustained-c-5dcaf-olling-bounds-rendered-rows-chromium/`.
Generated reports, binaries, databases and screenshots are not source changes.

These are local deterministic acceptance lanes. No physical devices, public mesh,
external TAK service, Python runtime, multi-process stress migration, hosted CI
or production-duration load was exercised. Environment-gated tests and ignored
live-network tests do not establish those external acceptance lanes.
