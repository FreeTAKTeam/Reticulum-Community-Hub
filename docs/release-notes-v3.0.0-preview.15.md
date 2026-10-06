# RCH v3.0.0-preview.15 — Linux AMD64 testing candidate

This candidate tests the SDK/daemon ownership corrections for
[issue #247](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/247),
merged through [PR #248](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/248).
Only the Linux AMD64 full server archive and SHA-256 sidecar are published.
The archive includes RCH, the web UI, TAK service, service templates, and
matching `reticulumd`. No desktop installer or other platform archive is built.

## Changes from preview.14

RCH no longer invents routes from announce history, rewrites destinations from
names or aliases, chooses propagation nodes, or resends daemon-admitted work
using local receipt deadlines. SDK path status/discovery, stable-ID batch
admission, and typed daemon receipts own the transport decisions. Unused
internal delivery mutation callbacks have been removed without compatibility
shims. Application recipients, moderation, payload encoding, and the queue
before daemon admission remain RCH responsibilities.

The daemon baseline is unchanged from preview.14:
`81344ae1eccc79612fe933efe990c8da55809254`, built with `zmq-pipeline-rpc`.
The earlier #242/#655 fixes are retained. This candidate does not add a new
daemon memory or response-writer fix. Memory pressure causing response delays
remains a hypothesis requiring measurements on the affected server.

## Validation and limits

All thirteen checks passed on the reviewed application changes in PR #248,
including the committed `release-readiness.ps1 -ServerOnlyAlpha` gate.
The local two-daemon acceptance delivered six messages, independently checked
receiver history and SDK path metadata, and retained 100,001 malformed unrelated
announce rows. See [the issue evidence](goals/issue-247-sdk-routing/EVIDENCE.md).
Release build and independent public archive verification are separate package
acceptance steps. Neither check proves overnight production memory, swap,
disk-write behavior, or delayed responses on the affected host.

## Upgrade and test

1. Stop RCH and reticulumd, and back up both data directories, databases, and
   configuration before replacing binaries. Keep the preview.14 archive for
   rollback. No new database migration is introduced relative to preview.14.
2. Extract the Linux AMD64 archive, verify its SHA-256 sidecar, and install its
   server and daemon together. Preserve existing configuration, service users,
   permissions, and ZeroMQ endpoints. Linux AMD64 requires an x86_64 host and
   the Ubuntu 24.04/glibc 2.39 runtime baseline.
3. Start the daemon and RCH. Check `/Status` and `/diagnostics/runtime`, then
   send a message and confirm the receiving client actually receives it.
4. Observe both processes overnight: RSS, swap-in activity, memory pressure,
   disk writes, and request/reply timeout warnings. If timeouts recur, retain
   matching request identifiers and daemon warnings before restarting it.

External integrations calling the removed `/internal/delivery-*` mutation
callbacks must stop doing so. Delivery state now comes through SDK receipts.
