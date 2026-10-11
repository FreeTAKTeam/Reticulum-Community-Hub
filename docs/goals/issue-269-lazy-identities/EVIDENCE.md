# Issue #269 validation

Validated locally on 2026-10-11, based on main
`e619335238a094ef7eb7703163da492b8c9a142e`, on
`corvo/issue-269-lazy-identities`. Dependency pins remain unchanged.

## Product acceptance

A real built UI and Rust server used a disposable SQLite fixture with 15,000
identities and 100,000 announces. Seventy-five identities were made recent for
pagination checks; the remaining history stayed available.

A loopback HTTP recorder observed zero `/Identities` requests while opening
Dashboard, Topics, Chat and default Users. Opening Identities made exactly one
50-record Recent request. Next requested only page 2 (25 records). All history
requested page 1, with a total of 15,000. Three rapid search changes (`id1`,
`id149`, `id14999`) issued one final search request, returning the historical
identity `id14999`. The DOM retained 50, 25 and 1 identity cards respectively.
Screenshots were inspected; clipped controls found during extraction were fixed
with local layout constraints and wrapping, then verified in the browser.

The same fixture was copied for the previous published preview.23 Linux binary.
Its former UI traversal (150 sequential 100-record pages) fetched 9,525,476 bytes
in 38,116.62 ms. This represents the eager behavior being removed, rather than a
comparison of equal query scopes.

Final HTTP measurements used six repetitions per query, discarding the first
for median calculation. The changed server used a debug build; the baseline was
a published release build. These are local observations, not a timing SLA.

| Final query | Records returned / matched | Body bytes | Median ms |
| --- | --- | --- | --- |
| Recent first page | 50 / 75 | 34,048 | 86.45 |
| All history first page | 50 / 15,000 | 34,053 | 27.37 |
| Historical identity search | 1 / 1 | 777 | 578.54 |
| Exact advertised destination lookup | 1 / 1 | 776 | 8.01 |

A Linux server memory snapshot after fixture requests observed 108,236 KiB
RSS/high-water for the changed debug server and 162,596 KiB for the baseline.
Different build modes and allocator retention limit this comparison. Browser
heap and sustained production RSS were not measured. Deterministic tests verify
configured lookup-cache/concurrency bounds, and page decoding tests prove no
unselected identity/announce payload hydration.

## Checks and review

- `cargo fmt --all -- --check`: passed.
- `cargo clippy --workspace --all-targets --locked -- -D warnings`: passed.
- `cargo test --workspace --locked`: 753 passed, 0 failed, 2 existing ignored.
- UI typecheck, lint and production build: passed.
- UI full suite: 47 files, 190 tests passed.
- `git diff --check`: passed.

The initial sandboxed Rust run could not bind a test loopback socket. The final
suite ran with loopback access. An intermediate legacy fixture mismatched raw
in-memory identity values with normalized durable values; the fixture now
persists the original raw records and retains its original equality assertion.

The isolated worktree reused installed locked UI dependencies through a temporary
symlink. Its external Vitest harness added only Vite filesystem access for that
symlink; no shipping test configuration or dependency manifest changed.

DB tests cover typed migration/backups/rollback, history preservation, raw-key
winners, annotation preference independent of recency, voice-owner suppression,
roster/team/REM/moderation exceptions, Unicode name matching, transactional write
maintenance and read-only operation. A realistic fixture corrupts unselected
payloads after a successful read to prove page-only decoding. Production SQL
query-plan evidence includes indexed announce/relationship probes, exact directory
key lookup, and selection before payload joins. Substring search and totals may
scan scalar directory rows; they do not decode historical payloads.

POST correctness and maintainability review closed all substantive findings:
refresh/revisit retries bounded enrichment; Chat online evidence uses the existing
chat timestamp separately from announces; Dashboard preserves advertised aliases;
search copy matches the API; actual production SQL plans are exercised. Root
integration also verified the corrected browser layout and configuration loading.

## Local artifacts and boundaries

Machine-local logs, fixtures, metrics and screenshots are untracked beneath the
original repository's `target/rch-269-evidence/`: `workspace-tests.log`,
`clippy.log`, `ui-tests.log`, `ui-build.log`, `core-query-plans.log`,
`identity-directory-fixture.db`, `identity-directory-fixture.metrics.json`,
`http-metrics.json`, `baseline-http-metrics.json`, `browser-requests.jsonl`,
`browser-acceptance.json`, `server-memory-snapshot.json`, `recent-page.png` and
`historical-search.png`.

The existing server startup identity-state mirror and explicit legacy unpaged
response remain compatibility paths. Request payload decoding, directory-page
residency and enrichment are bounded by this change. Validation concerns the
northbound directory and shared UI; it does not claim transport/hardware or
release acceptance. No PR, remote push or release was requested for this fix.
