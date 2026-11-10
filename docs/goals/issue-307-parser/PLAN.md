# Bound announcement capability parsing Implementation Plan

**Intent:** Prevent issue #307's input-triggered allocation abort and deploy the fix to the existing droplet.
**Current Behavior:** The preview.36 capability parser trusts MessagePack counts before validating input, and recursively scans without a depth budget. Two 101/102-byte persisted records requested 17,679,783,040 bytes.
**Expected Outcome:** Malformed or oversized capability metadata is rejected with bounded work/memory; ingestion and subsequent replay continue.
**Target-Perspective Output:** The droplet runs a hash-verified patched server; Status/runtime stay healthy, the broker progresses and no allocation aborts recur during bounded observation.
**Truth Owner:** RCH backend's announcement capability decoder.
**Contract Boundary:** Raw app-data hex/bytes from daemon announce projection or internal identity announce -> normalized capability list.
**Cutover:** Replace the old decoder helpers with one bounded module, build a server-only hotfix from deployed preview.36, install into a separate release directory and atomically switch the server binary with rollback metadata.
**Displaced Path:** Remove unchecked/recursive legacy parser helpers; every nested and fallback MessagePack decode uses the same validation boundary.
**Value Density:** Fix the vulnerable server without changing daemon, SDK pin, UI, schema or unrelated main-branch changes.
**Acceptance Evidence:** Sanitized attack/count/depth/truncation tests, valid-format compatibility tests, real broker replay with malformed then valid records across restart; required fmt/clippy/workspace tests and server release gate; Linux artifact hash match, local actual-record verification, and live Status/runtime/PID/replay-progress samples.
**Evidence Lane:** Isolated local builds/tests plus authorized production deployment; do not inject attack records into production.
**Kill Criteria:** Do not deploy on parser regression or failed required relevant checks. Roll back if new binary cannot start or health fails. Never claim permanent protection against every attack from this fix.
**Architecture Slice:** New crates/r3akt-rch-server/src/announce_capabilities.rs (+ bounded MessagePack helper/tests modules if size warrants); lib.rs routes both decoder callers and runtime diagnostics; durable_broker tests verify replay. Cargo dependency pins, LXMF checkout, UI, identities, configs and databases are outside source-edit scope.
**Plan Review Gate:** Requires PRE review before execution.

## Design

- Max app-data 16 KiB, nesting 32 and total MessagePack items 4096. Bounds apply before allocation/serde decoding, including embedded binary/string and byte-array capability slots.
- Parse lengths/counts with checked arithmetic and validate fixed-width primitive payloads, containers and exact document end; structural walk allocates no input-sized collection.
- Preserve existing plain UTF-8, direct maps/strings, REM array and embedded MessagePack capability formats.
- Reject bad optional capabilities without rejecting the whole announce/page. Following PR review, count only failed outer decode calls; opaque optional-slot probes do not increment the counter. Emit payload-free failure logs at most once per 60 seconds of monotonic time.
- Keep the production records private. Committed tests use sanitized equivalent headers and benign sentinel data.

## Tasks

1. PRE review of plan and trust boundary (reviewer; read-only).
2. Implement bounded decoder and focused tests (main; only named server source/test files). Verify valid controls, exact trigger, maximum lengths, depth, all truncated scalar types, nested/embedded bypass attempts.
3. Verify daemon-backed page/restart replay with a bad record followed by valid records, plus required repository checks and release readiness runner. Test actual private record copies locally.
4. Correctness/maintainability/POST review (reviewer; read-only); fix blockers.
5. Commit the focused patch; build Linux server from that commit and capture SHA-256. Preserve previous executable/release and obtain a consistent RCH SQLite backup before cutover. No public release or issue message is required for deployment.
6. Deploy the server hotfix, preserve daemon and configuration, verify installed/running hash and observe Status/runtime, broker progress and stable PIDs for at least five minutes. Record scope and limits.

Implementation is sequential in main. Reviewer tasks are read-only. Docker image preparation can run independently.
