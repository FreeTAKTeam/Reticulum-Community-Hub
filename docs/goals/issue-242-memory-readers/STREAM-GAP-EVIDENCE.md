# Malformed history blocks SDK stream-gap recovery

The operator's 7 October 2026 report describes 128 failed polls, no event or
announce import progress, a malformed LXMF FIELD_COMMANDS selector error, and a
4,096 increase in RCH's received counter. The daemon had 249 MiB RSS and
1.81 GiB swap. These production observations were supplied by the operator;
this investigation did not access or change the production host.

## Reproduced defect

RCH preview.16 source `4bcc6c7d523d869c8b5574dcea75da68162a7398` detects a
`StreamGap`, retrieves SDK message history, and only then processes the event
batch and saves its next cursor. History recovery bypassed the ordinary history
reader's malformed-command quarantine, recipient filter and duplicate check.
A bad history command therefore aborted recovery before cursor persistence.
Repeating the same poll could retrieve and decode the same history again.

`process_reticulumd_inbound_envelope` already returned successfully for a
previously processed envelope, but recovery still incremented `received_total`
after that no-op. This counter was not evidence of distinct delivery.

The unchanged recovery loop was first moved into the existing inbound module
with a page-fetch callback, so its behavior could be tested independently of
socket timing. A two-page fixture contains 32 valid messages followed by a
command with no selector, a later valid message, an unrelated recipient, and a
valid message on page two. Repeating recovery 128 times reproduced:

| Measurement | Preview.16 algorithm | Corrected importer |
| --- | ---: | ---: |
| Failed recoveries | 128 | 0 |
| Reported received | 4,096 | 34 |
| Successful recovered messages | 0 | 34 |
| Quarantined messages | 0 | 1 |

The corrected replay reaches page two, excludes the other recipient, and does
not count repeat imports. The regression fails on the original algorithm and
passes with the shared importer. A separate check preserves page-fetch errors.
Restart coverage checks persisted message deduplication and quarantine records.

## Correction and scope

SDK gap recovery and the ordinary history reader now share one import function
in `reticulumd_inbound`. It applies the existing direction/recipient checks,
quarantines malformed FIELD_COMMANDS using the existing diagnostic event, and
counts only newly processed envelopes. Filtering occurs before serializing
unrelated SDK history records. The SDK owns retrieval and pagination; no
transport fallback, protocol reinterpretation, history deletion, or new daemon
retention policy is introduced.

The exact 128/4,096 match establishes a reproducible defect consistent with the
operator's report. Production confirmation still needs the full error line,
installed build, and cursor/gap diagnostics. It does not establish that every
production failure followed this path.

## Daemon memory remains unqualified

Repeated failed recovery issues repeated daemon history queries. Each request
can fetch 1,000 history records and construct an SDK/ZeroMQ reply, so the defect
adds avoidable storage, serialization and allocation work. Its contribution to
the reported daemon RSS/swap has not been measured. A particular leak or retained
allocation owner cannot be inferred from the counter match.

The bundled daemon is LXMF-rs `81344ae1eccc79612fe933efe990c8da55809254`.
Its event log and reply queue have count bounds; aggregate retained payload
bytes and in-flight reply bytes still require attribution under the production
workload. HTTP readiness alone does not verify event progress. Keep
[LXMF-rs #655](https://github.com/FreeTAKTeam/LXMF-rs/issues/655) and
[RCH #242](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/242)
open pending production recovery and sustained memory/swap measurements.

## Local validation

Focused regression: `cargo test --locked --offline -p r3akt-rch-server --lib stream_gap_recovery -- --nocapture`.
All 672 workspace tests passed, with zero failures and two ignored tests. This
includes the three new recovery regressions and the existing command/quarantine
and SDK transport suites. Formatting, strict workspace/all-targets Clippy,
module budgets, and documentation links passed. Locked installed dependencies
and the native GCC toolchain were used; socket tests needed loopback access
outside the restrictive execution sandbox. Live infrastructure tests retain
their existing environment-dependent skips. No production restart, messages,
database edits, or deployment were performed.
