# RCH v3.0.0-preview.21 — Linux response lifecycle testing

Linux AMD64 full-server testing pre-release for the paired ZeroMQ response
lifecycle fix in [LXMF-rs PR #661](https://github.com/FreeTAKTeam/LXMF-rs/pull/661),
tracking [LXMF-rs #657](https://github.com/FreeTAKTeam/LXMF-rs/issues/657).

RCH library dependencies, SDK, CI and bundled `reticulumd` all use immutable
LXMF-rs revision `a424760137c7eaee5d5de7fb9ef2347871b85da1`. This enables
response-socket generation negotiation in the RCH client and bounded reply
connection reuse in the matching daemon. Deploy both binaries from this archive
together. Older SDK clients remain supported with per-request connections.

The daemon removes the fixed response-connect delay, limits idle plus active
reply connections to 32 and distinguishes response connect/send failures in
its diagnostics. Request deadlines and mutation retry behavior remain intact.
This release retains the durable RCH inbox/outbox from preview.19 and includes
the merged [RCH #260 fix](telemetry-collector-compatibility.md):
Columba/Sideband collector requests preserve valid packed telemetry, use the
Python-compatible global snapshot without a TopicID and require subscription
when one is supplied. Older records without packed telemetry are unavailable.

The Linux `reticulumd.service` template explicitly enables `--zmq-durable-broker`
so a fresh installation starts the required durable handoff.

## Upgrade and test

Back up the RCH and daemon data directories before installing. Install the
server, shared UI, TAK service and bundled daemon from the same full archive.
Verify its SHA-256 sidecar, retain existing deployment configuration and
identities, and check `/Status` and `/diagnostics/runtime` after startup.
Verify a unique test message and its receiver receipt; see the
[durable broker runbook](durable-broker.md) and
[telemetry collector compatibility notes](telemetry-collector-compatibility.md).

The existing release workflow builds the Linux AMD64 full archive and checksum
only for this preview; desktop and other platforms are skipped. Package source,
SDK contract metadata and daemon checksum are recorded in
`release-manifest.json`.

## Scope

This is a testing pre-release. Multi-hour production memory/swap stability,
physical power-loss recovery, public-network delivery and live TAK hardware
acceptance remain separate gates. A bounded local validation does not establish
that the complete production incident is resolved.
