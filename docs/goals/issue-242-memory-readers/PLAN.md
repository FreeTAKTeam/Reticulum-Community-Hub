# Remove RCH full-history memory amplification

**Intent:** Reduce the confirmed RCH memory amplification observed while testing preview.15; keep #242 and upstream #655 production acceptance open.
**Current Behavior:** Startup decodes all announces it does not retain. Permission reads construct several full announce snapshots. Chat copies every cached message before returning a limited selection. Ordinary R3AKT read-command snapshots also decode announcements not used by those HTTP commands.
**Expected Outcome:** Startup and ordinary permission/HTTP read commands do not decode unrelated announce history; limited chat reads copy only selected messages. Retained data and admitted SDK work stay intact.
**Target-Perspective Output:** The same northbound responses from the same retained fixture, with lower measured RCH RSS/PSS/anonymous request peaks and preserved database bytes.
**Truth Owner:** SQLite owns persistent application history. RCH core owns permission normalization and domain reads. SDK/daemon owns admitted delivery and routes.
**Contract Boundary:** Existing REST response semantics, identity normalization, timestamp ordering, attachments, and typed delivery state.
**Cutover:** Replace unnecessary readers and message copies directly, without compatibility alternatives or data deletion.
**Displaced Path:** Startup's full announce snapshot; full domain/announce permission snapshots and clone; full cached message copy preceding chat limits; unneeded announces in ordinary HTTP read-command snapshots.
**Value Density:** Small reader-only changes remove the confirmed announce and full-message copy amplification; no migration or transport redesign.
**Acceptance Evidence:** Meaningful regressions plus the same immutable four-fixture released-binary comparison (small, 100k announces, 25k messages, combined), response equality, raw history preservation, clean exits; workspace checks and committed server readiness gate.
**Evidence Lane:** Source mapping and local controlled memory attribution; current hosted CI after pushing. Production plateau and long-lived daemon retention are separately unproven.
**Kill Criteria:** No second reader fallback that restores whole-history decoding; no full-message clone before chat filtering/limit; no announce decoding in startup or permission paths; no arbitrary message eviction.
**Architecture Slice:** Modify server lib.rs, core lib.rs and bounded read helpers/tests. SQLite read transactions remain consistent. Full domain export and REM source authorization keep their full-history/domain semantics. SDK transport, daemon source, schema, packaging, UI, and write/receipt paths are outside the patch.
**Plan Review Gate:** PRE and POST review aligned with no blockers. POST found one expanded-mission reader still decoding announces; corrected and covered by a real mission/team regression. Ordinary HTTP commands use an explicit announce-free allowlist; full exports and REM remain on the full reader.

## Tasks

1. Main: replace startup announce hydration with the existing no-announce snapshot reader. Regression proves unrelated malformed history is not decoded and original bytes persist.
2. Main: add one consistent permission snapshot for capability grants/operation rights and consume it without redundant clones. Add an explicit no-announce ordinary R3AKT read-command snapshot; preserve full snapshots for exports/REM authorization and transactional writes. Test existing normalization/security behavior and unrelated malformed history.
3. Main: filter/sort borrowed cached chat records and clone only selected results, preserving stable ties, all filters, REM visibility and attachments. No message retention rule changes.
4. Main + independent reviewers/verifier: run appropriate Rust checks, committed gate, baseline/fixed response and memory comparison, preserve raw row fingerprints and source/binary identity, review and push a focused PR.

All implementation is sequential in the main agent. Independent reviews and the read-only daemon growth probe may run concurrently with disjoint temporary artifacts. No source changes or release publication in LXMF-rs are authorized by this plan.

## Known remaining work and risks

Message history remains cached. Active-only caching requires durable chat/count/replay/read/update fallbacks and careful handling of unresolved partial SDK admission, late receipts and restart recovery. Existing inbound insertion may evict active outbound records; do not add another eviction policy here. This patch therefore reduces proven copy amplification without claiming all production memory growth is fixed. Daemon event/socket/allocator/mesh retention needs separate measured attribution; changing it from the production interval alone would be guessing.
