# Release 2.6.2

## Overview
This release delivers a focused reliability and performance improvement pass across outbound delivery and message normalization, plus telemetry listener lifecycle hardening and small correctness cleanups.

## Detailed improvements

### 1) Outbound delivery reliability and observability
- Added a runtime stabilization pass for LXMF distribution and diagnostics to reduce transport instability during active operation.
- Refined outbound fan-out behavior to use a soft cap with deferred batching instead of immediate drops, improving delivery fairness under pressure.
- Refactored outbound queue timeout handling to shared futures monitoring, reducing timeout-path overhead and improving dispatch consistency.
- Hardened fan-out and send-timeout paths for clearer back-pressure behavior and easier production diagnostics.

### 2) Telemetry listener lifecycle hardening
- Refactored telemetry listener handling to support multiple listeners safely.
- Added unsubscribe callback support and ensured listener cleanup on broadcaster close to prevent stale subscriptions.
- Improved websocket telemetry broadcaster handling and associated tests to reduce lifecycle leak risk.

### 3) Command normalization robustness
- Added runtime guards around command-name normalization call sites to avoid incorrect callable assumptions.
- Refined typing/callability checks in command manager integration to avoid runtime/type-checking edge cases.
- Added stricter normalization path handling in mission domain guards.

### 4) Runtime stability and diagnostics
- Hardened LXMF-related runtime behavior in Northbound and runtime metric paths for cleaner startup and better error handling.
- Improved command daemon test behavior around async/no-return conditions.

### 5) Documentation and validation
- Updated AGENTS operational guidance.
- Expanded/updated tests across:
  - `northbound` services and websocket handlers
  - command manager and outbound queue
  - daemon test and telemetry paths
  - REST/websocket/telemetry integration scenarios
- These updates tighten regression coverage around the above runtime changes.

## Full change list
- Merge PR #173: Refactor outbound queue send timeout handling to shared futures monitoring
- Merge PR #174: Add outbound fan-out soft cap with deferred batching and batch enqueue API
- Merge PR #175: Support multiple telemetry listeners, return unsubscribe callback, and unsubscribe on broadcaster close
- Merge PR #176: Stabilize LXMF distribution runtime and diagnostics
- Additional cleanup and hardening commits:
  - `Use typed CommandManager access for command normalization`
  - `Add runtime callable guard before normalize_name call`
  - `Fix callable narrowing for command name normalization`
  - `Fix callable typing for normalize_command_name in mission guard`
  - `Fix command normalizer callable check for pylint`
  - `Harden telemetry broadcaster listener lifecycle`
  - `Refine fanout cap to defer recipients instead of dropping`
  - `Refactor outbound queue send timeout dispatch handling`
  - `Suppress false positive assignment-from-no-return in daemon test`
  - `Fix mission-domain regressions in team and checklist upserts`