# Memory reader evidence: issue #242 follow-up

## Result

The fixed release build removes confirmed startup/permission announce decoding and whole-message chat copies. This establishes a local reduction in request memory amplification, not a production steady state or a daemon fix.

RSS in MiB (KiB measurements divided by 1024):

| Retained fixture | Startup: preview.15 / fixed | Peak, concurrent rights: preview.15 / fixed | Peak, chat limit 1: preview.15 / fixed | After all reads: preview.15 / fixed |
| --- | ---: | ---: | ---: | ---: |
| small | 12.9 / 13.1 | 13.7 / 13.8 | 14.1 / 14.0 | 14.1 / 14.0 |
| 100k_announces | 55.2 / 13.0 | 436.3 / 13.7 | 428.6 / 13.9 | 428.7 / 13.9 |
| 25k_messages | 242.3 / 242.3 | 243.3 / 243.1 | 466.4 / 243.1 | 460.1 / 243.3 |
| combined | 283.3 / 242.2 | 664.4 / 243.0 | 691.9 / 243.1 | 691.9 / 243.3 |

All four cases have matching response byte counts and SHA256 hashes, matching raw announce/message payload fingerprints before and after both runs, zero swap, and clean exit 0. An independent verifier recomputed fingerprints, row counts and payload totals from all eight actual databases and reproduced every rounded value below. The approximately 243 MiB retained footprint with 25,000 messages remains: this patch does not change message-cache retention.

## Method and identity

- Baseline: downloaded Linux AMD64 server from v3.0.0-preview.15, SHA256 `cde660663d2fb13673935f40e1f0581f92e385950433ed3da4128b7ca5347df1`.
- Fixed release binary: SHA256 `ab5f28a5175860ff7eedd2cb76865725f59d248086e997eae8274a7ddb992c3a`, built from this PR against base `b21a9771acb0722fb4a5c7e4fc5e75ba4ed00fa7`.
- Same four fixture seeds in separate SQLite backups: no history; 100,007 announces; 25,000 messages; both. Announce payloads total 40,046,206 bytes; message payloads total 47,663,506 bytes. Messages are synthetic copies with deterministic distinct IDs/timestamps. No private database or payload is committed.
- Linux, two CPU affinity slots, two Tokio workers, isolated user services, MemoryHigh=1 GiB and MemoryMax=1536 MiB. No daemon or external mesh traffic.
- Wait for `/Status`, then sample `/proc/PID/smaps_rollup` every 25 ms during one `/api/r3akt/rights/grants` request, two concurrent requests, and `/Chat/Messages?limit=1`. Measure startup and post-request state after 300 ms. Peak sampling is approximate; RSS is process resident memory rather than total service-cgroup memory.
- Permission response is an empty grant list in the memory fixture; separate regressions verify populated grant normalization and relevant malformed-grant errors. Chat response hashes match with retained metadata.
- Local raw artifacts: `/tmp/rch-memory-readers-{baseline-v2,fixed}/results.json`; harness `/tmp/rch-memory-readers-comparison.py`; frozen fixed binary `/tmp/rch-memory-readers-binaries/r3akt-rch-server`. These are local test artifacts, not release packages.

## Verification

- `cargo fmt --all -- --check`: passed.
- Committed `scripts/release-readiness.ps1 -ServerOnlyAlpha`: passed, including strict workspace Clippy, workspace tests (664 passed, zero failed, two ignored), Rustdoc warnings, documentation links, release build and HTTP smoke. All four required backend packages are included in workspace tests.
- New regressions: startup/ordinary reads skip malformed unrelated announces; full reader preserves exports/errors; permission reads normalize populated grants and expose malformed relevant grants; expanded mission/team output remains equal; chat preserves ties, all filters, REM exclusion and attachments; allowlist excludes REM and future commands.
- Module-size and diff checks: passed. PRE/POST, correctness and maintainability review: aligned after correcting expanded mission reads.
- Initial sandboxed gate could not bind an existing localhost test socket; the unchanged gate passed with local socket access. This was an environment restriction, not a code failure.
- Optional external Reticulum/TAK gates were not configured; tests that require those environments do not establish live interoperability acceptance.

## Daemon and production acceptance remain open

The released daemon (`81344ae1eccc79612fe933efe990c8da55809254`, binary SHA256 `a1c02bcc7e0411439b1ed944537a53f4eca7af168e5e3c0cf4c97b2b7ec4aac8`) completed 2,259 successful empty event polls in an isolated 170-second run, with zero errors and clean exit. After warmup RSS changed only about 20 KiB. No growing socket, descriptor or thread population was observed. This excludes real mesh announcements, propagation payloads, populated storage and registered RCH identities, so it does not explain or disprove the reported production daemon growth.

Count-bounded retained event payloads and the peer-crypto map are source candidates to measure, not proven causes. No LXMF-rs source change is included.

RCH active-only message caching needs durable read/update fallbacks and preservation of unresolved SDK admissions/late receipts; arbitrary eviction is unsafe. #242 and LXMF-rs #655 remain open pending that work and representative 30-minute production memory, swap, CPU, latency and delivery acceptance.

## UI-triggered extension

The later UI request replay, final binary identity and allocator/browser evidence
are recorded separately in [UI-EVIDENCE.md](UI-EVIDENCE.md). The four-fixture
measurements above remain the prior reader-slice results for binary `ab5f28a5`;
they are not relabeled as the later UI experiment.
