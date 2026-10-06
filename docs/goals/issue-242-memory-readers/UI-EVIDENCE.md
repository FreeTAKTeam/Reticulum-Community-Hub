# UI-triggered memory amplification

The operator reported RCH at 714 MiB RSS plus 15 MiB swap after UI use, versus
52 MiB before UI use. This local comparison reproduces the scale of the jump
and identifies concrete request allocations. It does not establish production
heap retention, long-term stability, or the daemon's separate growth cause.

## Changed paths

- `/Identities` queries announce aliases only for listed identity states and
  actual client display records. Voice owners absent from identity states remain
  available; normalization, announce metadata and voice suppression are preserved.
- `/api/rem/peers` uses the indexed timestamp range before decoding. It decodes
  one candidate at a time and retains only REM records, then restores raw
  destination order. The existing freshness, runtime cutoff, source precedence,
  moderation and registered-mode rules remain authoritative. Moderation and
  modes share the same SQLite read transaction.
- Ban/Unban/Blackhole response enrichment queries only the changed identity.
  A committed moderation action still reports optional relevant decode failures.
- Shared roster and discovery refreshes share pending requests per backend
  request identity, including credential/revision changes. Stale responses cannot
  publish or clear a newer request's loading state. Discovery waits for both
  branches to settle after a failure before admitting another refresh.
- Reticulum configuration checks disposal after both initial awaits and suppresses
  late load notifications. Leaving the page cannot start a new polling timer.

Full export/command/authorization readers and stored announce/message history
are unchanged. The earlier PR changes to startup, permission reads and limited
chat copying are also included in the fixed binary.

## Controlled replay

Baseline: released preview.15 `r3akt-rch-server`, SHA-256
`cde660663d2fb13673935f40e1f0581f92e385950433ed3da4128b7ca5347df1`.

Fixed release binary, SHA-256
`d6a073c1d96c91f9f28cd9fcbf16a9e65923bb2871f436e0465d3614f6263686`.
Both use the pinned LXMF-rs source `81344ae1eccc79612fe933efe990c8da55809254`.

Fixtures use the same retained state: one actual client, seven identity states,
zero messages and zero REM modes. The large fixture has 100,007 announces,
40,046,206 encoded payload bytes; the small fixture removes only announces.
These are controlled fixtures, not a copy of the operator's production database.

Each fresh process has two Tokio workers, the same two-CPU affinity, 1 GiB
memory-high/1.5 GiB memory-max, no daemon and loopback HTTP. The sequence is
`/Client`, `/Identities`, `/api/rem/peers`, one Dashboard refresh, then three
concurrent Dashboard refreshes. Each Dashboard refresh loads `/Status`, then
missions, team members, events and the sequential roster chain concurrently.
Sampling uses `smaps_rollup` every 25 ms and a 300 ms post-request sample.
Sampled peaks may miss shorter allocation bursts.

Uninstrumented large-fixture results, MiB:

| Stage | Released peak / after RSS | Fixed peak / after RSS |
| --- | ---: | ---: |
| Startup | 55.2 | 13.3 |
| Clients | 55.2 / 55.9 | 13.3 / 14.0 |
| Identities | 388.7 / 323.6 | 14.0 / 14.2 |
| REM peers | 323.6 / 323.6 | 14.2 / 14.4 |
| Dashboard refresh | 644.6 / 640.4 | 14.4 / 14.6 |
| Three overlapping refreshes | 755.6 / 684.6 | 14.6 / 15.1 |

Small fixtures both end at 14.9 MiB. All four
uninstrumented processes exit cleanly and have zero sampled swap. All stable
roster response sizes/hashes match, including nested Dashboard results and each
concurrent refresh. Dynamic status/timing/event content is not an equality claim.
Announce and message row counts and length-delimited raw-key/payload SHA-256
fingerprints match before/after and across binaries. No history is removed.

## Allocator accounting

A separate diagnostic-only preload samples glibc `mallinfo2()` every 25 ms.
Allocated accounting is `uordblks + hblkhd`; reusable arena space is `fordblks`.
This is chunk/arena accounting, including allocator overhead, not a Rust object
profile or proof that every reachable object is understood. The probe is not
linked into the product. Instrumented RSS is reported separately because
allocator locks, sampling and scheduling may change the observed RSS plateau.

In the large released fixture, `/Identities` peaks at 348.8 MiB allocated,
then drops to about 1.1 MiB while RSS remains 323.8 MiB. After three overlapping
refreshes, RSS is 723.1 MiB, allocated accounting about 1.3 MiB, and reusable
arena space 709.2 MiB. The fixed fixture ends at 14.7 MiB RSS with about
1.3 MiB allocated. This demonstrates temporary allocation amplification plus
allocator retention for this replay, rather than an accumulating live heap.
All four instrumented processes exit cleanly with unchanged history. The small
instrumented baseline had about 11 MiB swap; the other instrumented cases had
zero sampled swap. Do not compare instrumented and plain runs as one experiment.

Local audit artifacts are under `/tmp/rch-ui-memory-{baseline,fixed-final,baseline-allocator,fixed-final-allocator}`.
The harness is `/tmp/rch-ui-memory-profile.py`; probe source/library are
`/tmp/rch-allocator-probe.c` and `/tmp/rch-allocator-probe.so`. JSON results,
allocator streams, process logs and preserved databases support these claims.

## Browser and verification

The built UI and fixed release server ran on an isolated loopback instance with
the retained large fixture and test-only setup credentials. Real browser
navigation loaded Dashboard, Users, all seven identities with announce metadata,
Configure and the Reticulum editor, then returned to Dashboard. The daemon was
not connected; the editor correctly showed runtime unavailable. Server RSS
was 12.1 MiB before navigation and 15.4 MiB after, with zero swap. Screenshot,
startup/final memory samples and `/Status` plus `/diagnostics/runtime` responses
are in `/tmp/rch-ui-browser-audit` (`startup-final.json`,
`after-browser-final.json`, `dashboard-final.png`). These short observations are not soak evidence.

Regressions cover raw destination ordering, exact SQL freshness boundary,
case-insensitive REM classification, runtime filtering, moderation/mode semantics,
alias display, voice owners absent from state rows, unrelated stale corruption,
relevant corruption/error reporting and retained history. UI regressions cover
shared requests, failure/retry, A-to-B-to-A backend changes, stale completion,
slow polling, discovery sibling failure and unmount during initial loading.

Installed locked UI dependencies pass lint, typecheck, all 162 tests and build.
Final `cargo fmt --all -- --check` and the committed
`scripts/release-readiness.ps1 -ServerOnlyAlpha` gate pass: strict workspace
Clippy, 669 workspace tests passed/zero failed/two ignored, Rustdoc warnings,
documentation links, release build and HTTP smoke. All four required backend
packages are included. Module-size and staged diff checks pass; documentation
links pass for all 51 tracked Markdown files. PRE/POST, correctness,
maintainability and independent evidence review are aligned. The verifier
recomputed all eight databases' raw fingerprints and all stable roster hashes.
An existing durability test was updated to corrupt the relevant indexed peer,
retaining its committed-write and warning assertions; unrelated corruption is
covered separately. External mesh/TAK acceptance was not configured.

## Remaining risks

Browser chat still retains streamed messages without a live-history cap; this
can grow browser memory, and cannot directly explain server RSS. Server message
history remains cached and outbound insertion is not uniformly bounded. A safe
active-only cache requires durable read/replay/receipt fallbacks; arbitrary
trimming can discard pending work. No new retention policy is introduced here.

The existing large server/UI modules make review harder but their size is not
proof of a leak. Production RCH plateau, daemon memory growth and reply-path
failures remain separate acceptance work. This patch has not been deployed to
the operator's machine and does not publish a release.
