# RCH preview.11 candidate stabilization

Qualification date: 2026-09-30. Candidate target: `v3.0.0-preview.11`.
Source base: `188e54f89559510dd82e5474e01553cd33177307`, with the local
candidate changes. LXMF-rs baseline: `v0.12.0`,
`20717f4456d1b402bcc3cb7e8a1a3a86c9bb4755`, SDK configuration version 2,
contract release `v2.6`, and daemon feature `zmq-pipeline-rpc`.

This report records the local qualification completed before
[PR #239](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/239).
The candidate passed the required local Linux software gates, a real
three-daemon delivery gate and extracted-package runtime qualification. At that
checkpoint no candidate commit, tag, push or public release existed. Hosted
checks, review follow-ups and published source/artifact identity are recorded in
the PR and the versioned GitHub release. These local results do not establish
stable v3.0.0 readiness or hosted multi-platform acceptance.

## Confirmed corrections

Failure-before/fix-after regressions cover strict authentication and local setup,
browser origins, bounded uploads and safe attachment serving, atomic durable
writes, delivery-receipt races, worker ownership/shutdown, TAK stream framing,
TLS/cancellation/counting, trust revocation, bounded snapshot progress and durable
marker replay. The focused durability and receipt suites pass all 32 regressions:
23 durability tests and nine receipt/callback tests. The final callback review
reproduced seven negative-callback failures and a weaker-receipt ordering failure
before correction.

SQLite owns the complete read/modify/commit sequence. Projections and events
publish after commit. Negative delivery callbacks cannot downgrade settled
history, and destination-only callbacks select eligible pending work. A weaker
propagation acknowledgement cannot replace delivery confirmation; the reverse
upgrade remains valid. Legacy roster aliases are normalized and coalesced within
the same transaction, including whitespace and case variants.

The shared UI has one deadline/cancellation owner per request and synchronously
invalidates backend-scoped projections on connection changes. Late page
initialization cannot create sockets, timers or maps after unmount. Image
previews are bounded, cancellable and revoke their object URLs. The packaged
browser evidence exercises the final code after these corrections.

## Local qualification results

| Gate | Result and evidence under `target/solid-release/` |
| --- | --- |
| Committed `release-readiness.ps1 -ServerOnlyAlpha` | Passed; `readiness-final.log`: format, strict workspace clippy, workspace tests, denied-warning rustdoc, documentation links, release server build and HTTP smoke |
| `cargo test --workspace` | 682 passed, zero failed, one ignored live test; the ignored test was exercised separately by the real daemon gate |
| Focused server/core/transport/TAK tests | Server 440 passed, one ignored; core 81, transport 54 and TAK 70 passed; `server-focused-final.log`, `focused-final.log` |
| Locked Rust 1.85 workspace/all-target check | Passed; `msrv-final.log` |
| RustSec audit with `--deny warnings` | Passed for 285 locked dependencies; `rust-audit-final.log` |
| Rust module budgets | Passed without widening the allowlist; `module-size-final.log` |
| Documentation and script checks | 27 tracked / 31 candidate Markdown files checked; five affected PowerShell scripts parse and final diff checks passed; `documentation-final.log`, `packaging-script-parse-final.log` |
| Locked shared UI installation | Passed; `ui-ci-current.log` |
| UI lint, strict types, tests and production build | Passed; 40 test files / 136 tests; `ui-lint-current.log`, `ui-types-current.log`, `ui-tests-current.log`, `ui-build-current.log` |
| UI and desktop dependency audit | Zero vulnerabilities; `ui-audit-current.log`, `desktop-audit-current.log` |
| Release server and TAK service builds | Passed; `readiness-final.log`, `focused-final.log` |
| Real Reticulum receipt, topic fanout, field join/reply, event polling and load | Passed with three LXMF 0.12.0 daemons; 500 requested, 500 accepted, 500 received, 250 per receiver; `reticulum-live-final.log` |
| Extracted server package runtime | Passed setup/authentication, 400 concurrent diagnostic/status reads, daemon failure/recovery, durable replay and restart; `package-runtime-qualification.json` |
| Packaged UI browser state | Map and persisted marker render; stored raster preview loads at 96x96; navigating away removes the map canvas and telemetry subscription; no browser console errors; `packaged-runtime-final/browser-evidence.json` and screenshots |
| Full Linux desktop bundle | Build passed; extracted AppImage sidecar program sections match the prepared server, TAK service and daemon; `desktop-build-final.log`, `desktop-audit-final.json` |
| Server archive and install helper | Checksum, manifest, executable binaries, UI, license and current docs verified after extraction; install-copy helper preserves them; `package-audit-final.json`, `installer-copy-final.log` |
| Final independent completion review | POST aligned; correctness, maintainability and completion verifier passed for the approved local candidate, with no important remaining finding; `completion-review-final.md` |

The RustSec refresh found [RUSTSEC-2026-0009](https://rustsec.org/advisories/RUSTSEC-2026-0009)
in `time 0.3.45`, retained by inactive optional cookie dependencies in the lockfile.
No active workspace dependency used `time`, including the all-features/all-target
dependency query. The locked graph now uses patched `time 0.3.47`; no advisory
ignore was added. Its inactive Rust 1.88 requirement does not enter the supported
Rust 1.85 build, which was checked again with the final lockfile.

The release gate's HTTP smoke is distinct from the real Reticulum evidence. The
500-message local fixture completed in 2.630 seconds; that timing describes this
loopback fixture and is not a deployment throughput guarantee.

## Extracted-package operator evidence

The archived server, TAK service, daemon and UI were independently extracted and
used for qualification on `127.0.0.1:18910`, with temporary SQLite state and owned
ZeroMQ endpoints. No credentials or private identities are included in this
report.

1. Unauthenticated `/Status` returned 401. Trusted local first-run setup enrolled
   credentials, authenticated `/Status` returned 200, and diagnostics negotiated
   SDK `0.12.0` / contract `v2.6` with a running managed daemon and event poller.
2. Two batches of 200 concurrent status/diagnostic reads, at concurrency eight,
   returned 400 HTTP 200 responses in total, before and after daemon recovery.
3. A proxy deliberately discarded a committed marker-create 201 response. A
   retry returned the exact original record and the database contained one
   marker. A Unicode-whitespace roster join followed by canonical leave did not
   resurrect membership on restart.
4. PNG and text uploads were retrieved byte-for-byte with the expected safe
   content types and `nosniff` headers. After restart, credentials, the marker and
   both attachments persisted; setup remained complete and the roster remained
   empty.
5. Terminating the owned daemon produced an observable SDK timeout/error in
   diagnostics. `/Control/Start` created a new daemon, event polling resumed and
   `/Control/Announce` succeeded.
6. Graceful server shutdown exited successfully with no owned daemon left behind.
   The restarted packaged server also shut down successfully with an active
   telemetry WebSocket subscriber.
7. The served packaged UI rendered the persisted map marker and stored image.
   Map-to-files navigation removed its canvas and reduced telemetry subscribers
   to zero. Closing the preview and navigating back removed the preview image.

The browser download-file capture was not qualified; raw download bytes and
headers were qualified over HTTP. The Windows installation helper was exercised
as a file-copy workflow under local PowerShell, not as Windows-native runtime
acceptance.

## Artifact identity

The local server archive is
`rch-rust-full-linux-x64-v3.0.0-preview.11-local-candidate.tar.gz` under
`target/solid-release/packages/`, with an adjacent `.sha256` file. The external
`package-audit-final.json` records its final checksum. Its manifest records the
LXMF release pin, SDK contract, daemon feature and verified daemon checksum.
`git_ref` and `git_sha` are null in these historical local artifacts because they
were assembled before the candidate commit; hosted assets must refer to the
actual released source. The external
`source-evidence.json` records the base and candidate source snapshot without
including unrelated `design-qa.md`.

| Artifact | SHA-256 |
| --- | --- |
| Extracted server | `d974330e7e63e15b4452c0de450b1aabeda0f34b16213d1e7b8049b872a05f36` |
| Extracted TAK service | `db10106a5798ceb28a2b48f33c5724d1d3a571220f8b8de71b0ff024b806889e` |
| Extracted LXMF 0.12.0 daemon | `0d691c0d84fbb0d98e1a7c946220a78a23ce43655de99ccc7cb16e28b8fd8763` |
| `RCH Desktop_3.0.0-preview.11_amd64.AppImage` | `584cd13eb7f47497560c4b8210221dc6a5799e57e0ba999b9c60b210be9b5e61` |

The AppImage is under the configured Cargo build output's `release/bundle/appimage/`.
The bundler changes ELF loader details; inspection separately verified identical
`.text`, `.rodata`, `.data` and `.data.rel.ro` sections for each sidecar. Prepared
sidecar whole-file hashes match the release binaries above. A documentation-only
final repack retains those already exercised binaries and UI assets.

## Tracker disposition and remaining acceptance

Tracker state was checked on 2026-09-30. The following issues remain open on
GitHub; this local work did not comment on, close or resolve them.

| Tracker scope | Candidate disposition |
| --- | --- |
| [#217](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/217), [#218](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/218), [#220](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/220), [#224](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/224), [#230](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/230) | Confirmed auth/setup/origin/internal-route/throttle/INI defects corrected with regressions |
| [#222](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/222), [#223](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/223) | Safe attachment response and bounded streaming upload corrections; existing axum 2 MiB default was finite but prevented the documented 8 MiB contract |
| [#219](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/219), [#221](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/221) | Verified TLS defaults and confirmed auth/trust/proxy/CSP findings corrected; real loopback certificate/framing tests passed |
| [#227](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/227), [#228](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/228), [#229](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/229), [#231](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/231) | Remote credential transport, security headers, Markdown/dependency advisories, legacy migration, setup disclosure and placeholder defaults corrected |
| [#232](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/232) | Library builds use the immutable Git dependency; daemon development/packaging uses the explicit pinned source |
| [#233](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/233) | Unused HTML/secret paths removed and cohesive owners extracted where needed; legacy large modules remain and the unused identity directory is explicitly ephemeral |
| [#238](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/238) | LXMF 0.12.0 event polling, direct receipts, fanout, load and unavailable-daemon recovery qualified locally; this is not a claim about continued 0.10.1 support |
| [#237](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/237) | Python 2.9.6 AppImage/systemd scope remains outside this Rust candidate |

The native desktop window and complete native operator workflow are **implemented
but unproven in this run**: an unrelated user service owns local port 8000, and it
was preserved. Desktop build and bundle content were qualified separately from
the extracted server/browser flow. Windows/macOS/ARM packages, external TAK, REM
phone/deck hardware and Python-server integration were not exercised here.
Hosted candidate checks and public assets were outside this local checkpoint;
their final results and source identity must be verified separately on the PR
and versioned release. Baseline hosted checks do not qualify the candidate diff.

The TAK queue, recent-key history and identity component are process-local.
Inbound TAK protobuf is unsupported. Socket DNS uses the platform resolver and
cannot be interrupted by the socket deadline. Post-commit notifications remain
observable best effort, without a durable distributed outbox. Broader legacy UI
and server decomposition remains outside this bounded release work.

Runtime data, logs, screenshots and generated archives are ignored local evidence,
not repository sources. The scoped pre-alignment upgrade stash and backup remain
recoverable, `design-qa.md` is unchanged, and the dirty sibling LXMF-rs checkout
was not modified.
