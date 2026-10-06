# Issue #242 resource efficiency implementation plan

**Intent:** Keep RCH responsive with approximately 100,000 persisted announces on a two-CPU, 2 GiB deployment, and diagnose the paired daemon's resource demand.
**Current Behavior:** Every nonempty announce import batch loads and clones the complete history through a temporary domain snapshot. Runtime diagnostics loads history twice and sorts all records to display ten. Daemon CPU and storage pressure are observed but not yet attributed.
**Expected Outcome:** Import work depends on incoming peers, diagnostics deserializes at most ten recent records, subscriber identity checks use indexed projections, and persisted history remains intact. Change daemon algorithms only for independently measured defects.
**Target-Perspective Output:** Authenticated diagnostics, announce, imported peer records and message receipts remain correct while operator-visible CPU, RSS/PSS, swap and latency measurements show the effect.
**Truth Owner:** RchSqliteStore owns persistence and indexed projections; RchCore owns announce classification and normalization. LXMF runtime/storage owns any daemon change.
**Contract Boundary:** Existing announce payloads and REST/SDK contracts remain authoritative. Projections are derived transactionally from these payloads; no new history retention policy.
**Cutover:** Redirect import to existing peer-key lookup; replace diagnostics full-history reads with one store summary and indexed membership API. Add versioned SQLite migration with backup and streaming backfill. Migration 4 adds write guards rejecting payload-only inserts/replacements (the preview.12 writers) that omit timestamp projections. Stop all RCH writers before upgrading; mixed versions writing one database are unsupported. Downgrading requires restoring the pre-v4 backup while services are stopped, and discards writes made since that backup. Never downgrade by stripping columns or recreating history.
**Displaced Path:** Remove full-history materialization from batch import and diagnostics. Full history listing remains available where the public contract requires it; no duplicate cache or connection owner.
**Value Density:** Fix history-amplified hot paths first; profile daemon separately before touching propagation or polling policy.
**Acceptance Evidence:** Exact baseline/fixed release builds and approximately 100,000-row disposable state; compare counts, raw payloads, classifications, freshness boundaries, deterministic ordering and query plans. Measure CPU, RSS/PSS, anonymous memory, swap and endpoint latency during at least 30-minute paired runtime runs with real local peer events, announce and restart/message delivery. Explicit local measurement budgets: no persistent history loss; summary <=10 decoded payloads; indexed timestamp/identity reads; diagnostics and authenticated announce p95 <=250 ms; daemon readiness p95 <=100 ms with no steady-state timeout; after warm-up, RCH and each daemon <=10% of one CPU averaged over the observation window; RCH steady PSS <=256 MiB on this fixture. Before/after runs use identical two-CPU affinity and host memory environment; the fixture does not enforce a 2 GiB memory cgroup, so production memory-pressure acceptance remains unproven. These are local qualification targets, not asserted production SLAs. Record hardware, workload, memory enforcement, failures and unproven production differences.
**Evidence Lane:** Source regressions and migration/query-plan tests, release-mode before/after runtime artifacts, independent verification. Production preserved databases and exact network workload are unavailable locally; synthetic history does not establish full production resolution.
**Kill Criteria:** No history pruning, raised service limits, hidden errors, skipped delivery proof, speculative daemon change, permanent alternate full-scan fallback, or claim of production resolution from unit tests.
**Architecture Slice:** Core lib.rs/migrations own schema/write/read queries (row writer `upsert_identity_announces`, snapshot writer `save_topic_snapshot_tables`, offline Python database importer `python_migration::InsertRow::apply`, migration `migrate` and new `0004_identity_announce_projections.sql`); server lib.rs owns import and diagnostics response; server topic_diagnostics.rs owns subscriber checks. Root Cargo pins/workflows change only if a verified daemon fix is required. Preserve dirty sibling LXMF checkout, design-qa.md, UI, the legacy Python server and published tags. The Rust offline Python importer delegates announce writes to the shared projection writer.
**Plan Review Gate:** Requires PRE review before execution.

## Tasks

1. **Measure and review** (root; read-only explorer): capture issue and baseline source; seed synthetic history; collect baseline profiles and daemon architecture evidence. PRE reviewer checks data ownership, compatibility and acceptance. No production state changes.
2. **Bound import** (root, server lib.rs/tests): load only batch peers using existing key query, retain existing RchCore classification/first-seen/update behavior. Verify unchanged, duplicate, newer/older and malformed announces against representative history; unrelated payloads unchanged. Sequential.
3. **Bound diagnostics** (root, core lib.rs/new migration/tests, server lib.rs/topic_diagnostics.rs/tests): timestamp/normalized identity projections, transactional row/snapshot writes, streaming rollback-safe migration, indexed summary and membership. Verify legacy migration/reopen, malformed backfill rollback of columns/indexes/version/payload bytes, rejection of old payload-only writes, row and snapshot writes, freshness/ties/empty cases, query plans and full REST compatibility. Membership preserves normalized destination OR normalized announced identity, including case, whitespace and absent aliases. Record migration 4 only after streaming backfill succeeds; retain backups and rollback. Before any daemon edit, append its measured defect, exact owner/files and regression to this plan. Sequential after PRE.
4. **Profile daemon** (root with read-only explorer): reproduce suspected expensive work with representative synthetic state and counters/profile. Implement only confirmed bounded correction through the current clean checkout, update pinned source if needed, and run upstream checks. If local evidence cannot attribute production CPU, document the missing profile rather than invent a fix.
5. **Qualify and integrate** (root; independent reviewer/maintainer/verifier): format, workspace clippy/tests and affected package checks; server release readiness gate; before/after paired runtime measurements, fresh persistent inbound messages and restart recovery; POST correctness and maintainability review. Commit/push only verified task changes to the current branch. Keep issue open if its complete production acceptance remains unproven; no merge or new release without an explicit request.

## Task 4 measured daemon correction

At 100,002 propagation-peer mark rows, the exact completed-mark `LOWER(peer)` predicate took 8.992 ms median and a 1,024-lookup batch took 9,223.1 ms. A nonunique expression index on `(LOWER(peer), transient_id, state)` reduced these to 0.00423 ms and 4.19 ms with identical answers and logical row digest, including historical uppercase aliases. This proves an indexed-lookup defect, not attribution of the production Tokio-worker spike.

Owner: `LXMF-rs/crates/libs/rns-rpc/src/storage/messages_parts/messagesstore_sections/list_announces.rs`, existing transactional `init_schema` index block. Add one `CREATE INDEX IF NOT EXISTS` expression index; keep the current predicate, mark state transitions, existing indexes and all rows. Regression owner: a new `outbound_message_sections` test include, validating mixed-case/terminal/negative lookups, nonunique index, exact query plan and legacy reopen without data mutation. Run focused and full RPC tests, relevant lint/diagnostic/boundary checks; build and qualify the resulting daemon before updating RCH's exact source pins. At one million rows the index added approximately 118.6 MB disk space and took 612 ms to build locally; record that startup needs a writable database and sufficient disk. Production startup cost remains unmeasured.

## Execution disposition

PRE and POST source review passed. The committed server-only release gate, four backend package suites, upstream RPC 759 tests/lint, module budgets and documentation checks passed. Both 30-minute local workloads completed; independent audits verify all 100,000 raw payloads, four distinct Delivered/persisted messages, post-restart imports and candidate zero shutdown codes. The candidate meets every local resource/latency budget; see [the evidence report](../../issue-242-resource-efficiency.md) for exact metrics, source/binary identities, fixture deviations and evidence limits. The bounded implementation is locally qualified. Original production daemon CPU attribution and the 2 GiB reclaim-pressure acceptance remain unproven, so #242 stays open. No merge or release is part of this source integration.

## Follow-up: retained announce lookups after preview.13

Preview.13 already contains the diagnostics/import correction. With 100,000
preserved synthetic records, current-main release-mode measurements still show
214.6 ms median for a one-client roster enrichment and 78.7 ms for one recipient
freshness probe. Redirect these paths to the schema-4 normalized destination and
announced-identity indexes. Core remains the read owner; no new cache, connection
owner, schema migration, history retention policy or daemon change.

Preserve raw destination ordering across all requested identities, deduplicate
rows matching both indexes, retain REM source precedence and exact raw-field
semantics for the delivery timestamp helper. Relay sender names and active topic
subscribers use the same bounded matching reader. Storage/decode failures in
these paths propagate to callers; they must not become missing/freshness-false
fallbacks. Empty client rosters must never mean full-history selection.

Verification: alias/case/Unicode whitespace/timestamp boundary/query-plan tests,
full-reader equivalence for shared-identity annotations and relay ties,
corrupt unrelated versus requested payloads, storage errors, unchanged raw
history digest in the explicit 100,000-row release probe, required workspace
checks and committed server-only readiness gate. Public full-history APIs and
chat-name alias graph construction retain their existing contract. The original
production daemon CPU spike and 2 GiB memory-pressure acceptance still require
fresh deployment evidence; this follow-up does not certify them.

## Related LXMF-rs #655 follow-up

The operator report identifies reticulumd as the source of measured disk traffic.
Synthetic daemon probes reproduce three costs: repeated unchanged announce-cache
writes, a second RAM copy of every durably stored propagation payload, and full
payload materialization for ID/size-only offers. A blocked identity-lookup
regression also demonstrates event publication blocked behind the poll's log lock.

Owner: LXMF-rs transport announce cache; RPC MessagesStore metadata projection;
RPC propagation ingest/fetch/alias paths and private event log; SDK ZeroMQ timeout
diagnostics. SQLite is the single persistent payload owner. Remove the private
RAM payload map and its fallback reads; durable deletion is authoritative. Use the
existing covering destination/size/ID index. Compare cache bytes with bounded
reads, preserving mutable headers and interface changes. Snapshot requested
visible shared event references and release the log before identity-independent
encoding/metadata. Keep cursor/overflow/event limits and the SDK shared deadline.
No speculative cancellation, new eviction policy, service-limit increase, history
pruning or schema change.

Evidence: baseline RSS after ingest/list of 1,000 64 KiB inputs was
139,292/207,216 KiB; fixed was 11,860/11,860 KiB with the same persistent row and
byte counts. Repeated 10,000-cache flush kernel write accounting fell from
40,960,000 bytes to zero, with exact-byte/mtime correctness tests. Production
allocation attribution, aggregate event/response byte admission and overnight
2 GiB memory-pressure acceptance remain open. Verify upstream tests/lint, daemon
build/runtime, then pin RCH and all workflows to the exact pushed upstream SHA,
re-run the committed server release gate and push the existing follow-up PR.


### Follow-up review disposition

POST correctness and maintainability reviews found the bounded source changes
aligned with the follow-up contract. Independent verification confirms three
persisted Delivered receipts across restart, all 100,007 original raw rows,
matching dependency/workflow pins and binary hashes, per-service limits and
zero process exits. The maintainability review identified three current
packaging/transition baseline descriptions still naming the old daemon SHA;
those references now match `81344ae1eccc79612fe933efe990c8da55809254`.
Historical published release evidence retains its original pins. Production
overnight/reclaim acceptance remains unproven; #242 and #655 stay open.
