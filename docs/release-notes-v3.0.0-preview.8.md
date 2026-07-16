# RCH Rust v3.0.0-preview.8 Release Notes

This prerelease adds the authoritative team-scoped REM peer directory used by REM 1.2.6 SemiAutonomous mode.

Python `2.9.x` remains the stable maintenance line on `rch-python`; this is a Rust preview intended for validation of the 3.0 runtime, packaging, migration, LXMF, TAK integration, and local operator desktop path.

## Highlights Since preview.7

- Added the LXMF command `rem.registry.team_peers.list` with accepted/result lifecycle responses in `FIELD_RESULTS`.
- Scopes results to active REM-capable identities that share at least one team with the requester.
- Supports primary and linked client identities, canonical `lxmf.delivery` destinations, deduplication, moderation exclusions, and the existing one-hour announce freshness window.
- Rejects unrostered or non-REM callers before acceptance and excludes the requesting destination from its own result.
- Returns `scope: shared_teams`, `effective_connected_mode`, and the existing peer metadata contract while preserving the legacy peer command and HTTP endpoint.
- Ingests standard raw LXMF `FIELD_COMMANDS` envelopes from reticulumd while preserving the signed LXMF source, command correlation ID, and message deduplication key.
- Documents the RCH-before-REM upgrade order and fail-closed behavior of newer REM clients against older hubs.

## Validation

- Formatting, clippy, full workspace tests, dependency audit, release builds, release-readiness, and the ZMQ projection floor passed in CI.
- Core and server tests cover shared-team inclusion, other-team exclusion, linked identities, canonical destinations, deduplication, caller exclusion, moderation, stale/non-REM filtering, connected-mode calculation, and unrostered rejection.
- A live Pixel 7 received an accepted/result response containing only its two eligible shared-team peers; REM then targeted telemetry only to those two telemetry-capable destinations.

## Upgrade Order

Deploy this RCH release before enabling SemiAutonomous mode in REM 1.2.6. The legacy `rem.registry.peers.list` command and `GET /api/rem/peers` remain available for older REM clients.

## Known Boundaries

- This remains a preview release, not stable `v3.0.0`.
- Operator packaging and desktop bundles remain preview artifacts while field feedback and multi-device receipt validation continue.
- Python parity and Rust transition gaps remain tracked in the repository release/readiness documentation.
