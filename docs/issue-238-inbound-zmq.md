# Inbound ZeroMQ recovery: RCH issue #238

RCH [issue #238](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/238)
reported a healthy daemon HTTP/TCP service while ZeroMQ event polling repeatedly
timed out. Socket regressions reproduced two contributing failure paths:

- SDK connection retry and ZMTP handshake used zeromq's 30-second default before
  the configured RPC deadline began. RCH's actor caller returned much earlier.
- The daemon's single response writer waited on a departed client endpoint,
  delaying responses to healthy event-poll clients.

The SDK now applies one deadline to lock acquisition, connection, send and
correlated receive. It binds/advertises its actual response endpoint and resets
failed sockets under the same owner. Sync RPC calls use that implementation.
The daemon delivers at most 32 responses concurrently, each bounded to one
second, and cancels owned response sockets at shutdown while joining active RPC
mutations. RCH separately bounds queue residence, returns explicit expiry errors,
and budgets negotiation plus identity restoration plus the requested RPCs.

## Deployment

All current RCH LXMF dependencies and CI daemon builds pin
`7e26c1a9c415e5cdabcaed1bab618698288be239`, based on LXMF-rs `0.13.0`.
SDK contract version 2 / release `v2.6`, the configured endpoints, and the RCH
northbound contract are unchanged. Deploy the matching patched `reticulumd`;
SDK-only updates cannot repair an older daemon's shared response writer.
Published preview.11 artifacts continue to contain their original `0.12.0`
baseline; this fix has not published replacement artifacts.

## Evidence

Before the fix, both SDK handshake deadline regressions and the daemon
stalled-peer/healthy-event-poll regression failed. RCH's delayed identity-restore
regression failed with the exact outer timeout from the report. Those targeted
regressions now pass. The upstream implementation is reviewed in
[LXMF-rs PR #653](https://github.com/FreeTAKTeam/LXMF-rs/pull/653).

Fresh local validation on the paired source revisions:

- RCH: formatting, strict workspace/all-target clippy, 689 passing workspace
  tests (one separately gated load test ignored in the ordinary suite), and the
  four focused server/core/transport/TAK suites. Optimized server build passed.
- LXMF: formatting, strict affected-package/all-target/all-feature clippy,
  242 SDK unit tests, 519 daemon binary tests and the remaining selected-package
  integration/doc suites; boundary, module-size and architecture checks passed.
- The committed three-daemon local Reticulum gate passed field-command receipt,
  direct receipt, two-recipient fanout and ZeroMQ polling. Its new RCH import
  check persisted six announces and one inbound message with zero poll errors.
  The load run accepted and received all 500 messages (250 per receiver).
- A real managed-daemon interruption kept RCH PID `2342187` running while
  `reticulumd` restarted from PID `2342252` to `2342349`. HTTP `/Status` remained
  running, diagnostics exposed `SDK_TRANSPORT_ZMQ_TIMEOUT`, and polling recovered
  without restarting RCH. Four announces and one actual peer message were then
  imported; `/Chat/Messages` returned the marker. The final diagnostic showed
  one expected interruption error and no current error. Shutdown left no owned
  processes running.

The local acceptance artifact is retained under
`target/issue-238/runtime-mesh-recovery-verified/evidence.json`, alongside the
reproduction helpers and build outputs. Reproduce the committed mesh acceptance
with `scripts/local-reticulum-live-gate.ps1 -IncludeZmqEventPoll -IncludeZmqLoad`
and a clean patched `reticulumd` binary. No public replacement release,
production-network, or physical-device acceptance is claimed by this bug fix.
