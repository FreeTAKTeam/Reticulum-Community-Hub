# Review record

## PRE

Independent SOL review of the plan and current source: **aligned**, no blockers.

- Required a same-actor idle-expiry recovery case in addition to replacement-client restarts. The plan now requires the existing worker/actor to restore its identity and consumer and acknowledge fresh durable work after expiry.
- Removed a proposed always-zero closed-session counter because the selected contract uses idle expiry and adds no close API.
- Confirmed existing `SDK_BROKER_NEGOTIATION_REQUIRED` recovery classification, bounded durable-worker retry and production actor identity restoration. These source findings still require paired runtime evidence.

## Implementation review

The parent reviews the implementation agents' changes independently and owns merge decisions.

- RCH #320: reviewed startup warning classification, shared verification predicate, nonmutating credential reads, unchanged upgrade-on-success path and exact public setup response. No correctness blocker found. Hosted audit exposed RUSTSEC-2026-0486 in the existing rustix lock entry; the fix updates only the affected version/checksum/references to 1.1.6 and preserves unrelated dependency selections.
- LXMF #756: reviewed authenticated principal/route scoping, monotonic expiry, in-flight pin lifetime, capacity behavior and preserved durable ownership. Required a recognizable expiry response when an ordinary SDK request itself discovers expiry. The implementation and tests cover that case; documentation explicitly limits ordinary-method behavior after another request has already reaped the entry. Durable requests always retain the existing restoration signal. Removed unrelated Windows dependency graph changes from the lockfile repair.
- RCH #307 integration: required the actual bounded worker to recover the same actor after expiry and advance its durable checkpoint. Standalone evidence must include a real peer delivery for every graceful/abrupt restart incarnation, plus another after reclamation. Historical live-gate filters matching zero tests cannot be counted as delivery evidence.

Final POST decisions, exact heads, CI outcomes and integration results are recorded in EVIDENCE.md once complete.
