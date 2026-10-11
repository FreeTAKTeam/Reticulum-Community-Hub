# RCH v3.0.0-preview.22 — Linux telemetry receive testing

Linux AMD64 full-server testing candidate for the reproduced receive defects in
[RCH #258](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/258).

## Changes

- Normalize the daemon's flat telemetry projection into the existing nested RCH
  location contract so valid uploads reach the normal map API.
- Decode signed altitude and bearing correctly. Recover complete packed sensors
  from new durable journal frames only after matching verified source,
  destination and message ID; preserve optional and unknown sensors through
  persistence and restart.
- Record malformed/unsupported telemetry separately from valid commands/chat,
  with privacy-safe diagnostics and bounded, exact MessagePack parsing.
- Retain preview.21's SDK/library/CI/bundled daemon pairing at LXMF-rs
  `a424760137c7eaee5d5de7fb9ef2347871b85da1` and its explicit
  `--zmq-durable-broker` Linux service flag. This avoids rolling back #657's
  response lifecycle correction when releasing current main.
- Include the merged bounded directory loading and independent Users/Teams/Chat
  initialization from #264.

## Upgrade and test

Back up both RCH and daemon databases, identities and configuration. Verify the
archive SHA-256 sidecar before extracting. Install the server and bundled daemon
from the same archive together, retain deployment configuration and endpoints,
and check `/Status` and `/diagnostics/runtime` after startup.

Send fresh telemetry, confirm its normal map projection and request a collector
snapshot. Historical projected-only records still lack original packed sensor
bytes and remain unavailable to collector replies. This release does not rewrite
already persisted historical records; fresh uploads provide the complete packet.
Topic-free collector requests retain the approved global snapshot policy;
requests with a TopicID still require subscription.

See the [receive diagnosis and versioned matrix](telemetry-receive-compatibility.md),
[collector contract](telemetry-collector-compatibility.md) and
[durable broker runbook](durable-broker.md).

## Scope and evidence

The existing release workflow owns the Linux AMD64 full-server archive and its
checksum. It includes RCH, shared UI, TAK service and matching ZeroMQ daemon;
desktop and other platforms are skipped. The embedded release manifest records
source commits, SDK contract and binary checksums.

The unmodified Columba 2.2.6 codec produced the synthetic regression fixture and
passed its JVM roundtrip/timebase checks. Initial local workspace validation
passed 724 tests with two existing ignores, strict Clippy and formatting.
Publication CI and server-only readiness validate the final paired candidate.
These are testing-build gates; actual installed-client/deployment receive-error
confirmation, Android/Reticulum sessions, sustained production memory/swap,
physical power-loss and live TAK hardware acceptance remain outstanding.
#258's broader live acceptance and #259's extraction handoff remain open.
