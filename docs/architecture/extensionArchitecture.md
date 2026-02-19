# RCH Extensions Architecture (v1.1)

## Summary

Reticulum Community Hub (RCH) will implement a service-only extension runtime. All extensions run out-of-process and communicate with core RCH through the Internal API command/query/event plane over local HTTP and WebSocket streams.

This architecture is designed to:

1. Avoid in-process runtime contention and Python scaling limitations.
2. Provide strong fault isolation and independent lifecycle control per extension.
3. Deliver a unified operator experience in a single command center UI.

## Goals

1. Standardize backend extensibility for northbound and southbound capabilities.
2. Unify command handling on `internal_api` and deprecate direct legacy command execution.
3. Provide install/enable/start/stop/restart/update/uninstall operations from API, CLI, and UI.
4. Integrate extension status, actions, and views into one RCH UI command center.
5. Enforce signed extension package validation for install/update.

## Non-Goals (v1)

1. In-process plugin execution for extension business logic.
2. Remote frontend code execution (module federation/iframe-hosted runtime JS).
3. Cluster-first distributed orchestration.
4. Public extension marketplace.

## Decision Baseline

1. Runtime model: service-only, one process per extension.
2. IPC model: local HTTP + WebSocket using Internal API semantics.
3. Lifecycle owner: RCH supervisor, with hot lifecycle operations.
4. Security model: local trusted peer runtime access; signed packages required for installation.
5. Storage model: extension-owned domain state + core-owned registry/health metadata.
6. Deployment target: single-node edge host first.
7. OS support target: Linux and Windows parity.

## Architecture Overview

### Core Components

1. Extension Registry
   - Stores extension identity, version, manifest projection, enablement, runtime state, config hash, install audit metadata.

2. Extension Supervisor
   - Spawns and manages one extension process per extension.
   - Enforces restart policy, backoff, and resource budgets.

3. Extension Command Gateway
   - Routes commands from core/UI/API to extension command endpoints.
   - Normalizes results into Internal API result/events.

4. Extension Event Ingest
   - Accepts extension-produced events/results.
   - Publishes to core EventBus for fan-out to existing subscribers and UI streams.

5. Extension UI Registry
   - Serves backend-managed extension metadata for dynamic navigation/widgets/actions.

### Runtime Boundary

1. Core RCH process hosts control-plane functionality only.
2. Every extension executes in its own OS process.
3. Extension service endpoints bind to loopback by default.
4. Extension failures are isolated from core and from other extensions.

## Extension Taxonomy and Placement Policy

### Southbound Adapter Extensions

1. Purpose: external protocol/device/network integrations.
2. Examples: Meshtastic, TAK gateway, MQTT/serial radio adapter.
3. Runtime: service process (required).

### Northbound Feature Extensions

1. Purpose: internal automation, enrichment, analytics, workflow features.
2. Examples: report builder, alert rules, transformation pipeline.
3. Runtime: service process (v1 policy).

### UI Module Extensions

1. Purpose: command center views/actions powered by backend metadata.
2. UI execution model: local shell components only, no remote extension script execution.

## Canonical Command Plane

All extension traffic flows through `reticulum_telemetry_hub/internal_api`.

### Required Direction of Flow

1. UI/API operator action -> Core Internal Command.
2. Core command targeting extension -> Extension Command Gateway.
3. Extension result/event -> Extension Event Ingest.
4. EventBus dispatch -> subscribers/WS streams/UI.

### Legacy Convergence

1. Introduce compatibility adapters that map legacy `CommandManager` paths into internal commands.
2. Keep legacy interfaces for a deprecation window (two minor releases).
3. Emit deprecation metadata/log warnings on legacy usage.

## Public Interfaces

### New Core REST Endpoints

1. `GET /extensions`
2. `POST /extensions/install`
3. `GET /extensions/{id}`
4. `PATCH /extensions/{id}`
5. `POST /extensions/{id}/start`
6. `POST /extensions/{id}/stop`
7. `POST /extensions/{id}/restart`
8. `POST /extensions/{id}/update`
9. `DELETE /extensions/{id}`
10. `GET /extensions/{id}/logs`
11. `GET /extensions/registry/ui`
12. `GET /extensions/events/stream`
13. `POST /extensions/{id}/command`

### Extension Service Contract (Per Extension Process)

1. `GET /ext/v1/health`
2. `POST /ext/v1/commands/{action}`
3. `POST /ext/v1/config/reload`
4. Optional: `GET /ext/v1/metrics`

### Extension to Core Callback Contracts

1. `POST /internal/extensions/{id}/events`
2. `POST /internal/extensions/{id}/results`
3. `WS /internal/events/stream` for extension subscriptions where needed.

## Manifest and Packaging Specification

### Manifest Schema Fields

1. `id`, `name`, `version`, `description`
2. `kind` (`southbound_adapter`, `northbound_feature`, `automation`, `ui_module`)
3. `runtime` (fixed `service` in v1)
4. `launch` (`command`, `args`, `env`, `working_dir`)
5. `api` (bind host/port, declared endpoints)
6. `interfaces` (commands/events/queries consumed and produced)
7. `ui` (`nav_items`, `routes`, `widgets`, `actions`)
8. `resources` (`cpu_limit`, `memory_limit`, `timeouts`, restart policy)
9. `config_schema` (JSON Schema reference)
10. `signature` (signer metadata and detached signature reference)

### Package Format

1. File extension: `.rchext`
2. Contains: manifest, payload, checksums, signature artifacts.
3. Install/update workflow:
   - Signature verification against trusted keyring.
   - Checksum validation.
   - Manifest schema validation.
   - Compatibility validation (`rch_version`, `os`, `arch`).
4. Any verification failure blocks installation/update.

## Lifecycle and Operations

### State Machine

1. `installed`
2. `enabled`
3. `starting`
4. `running`
5. `degraded`
6. `stopping`
7. `stopped`
8. `failed`
9. `updating`
10. `uninstalled`

### Hot Operations

Supported without restarting RCH core:

1. enable
2. disable
3. start
4. stop
5. restart
6. update

### Supervisor Policies

1. Restart policies: `never`, `on-failure`, `always`.
2. Exponential backoff with max cap.
3. Failure cutoff to avoid crash loops.
4. Per-extension resource governance:
   - CPU budget
   - Memory ceiling
   - Max concurrent commands
   - Command timeout

## Unified Command Center UI

### UI Integration Model

1. Add `/extensions` route as operator control hub.
2. Sidebar navigation merges core routes plus extension-provided nav items.
3. UI registry endpoint drives dynamic rendering metadata.
4. Only approved local shell widgets are rendered.

### Initial Widget Catalog

1. `statusCard`
2. `metricGrid`
3. `actionPanel`
4. `eventTable`
5. `logTail`
6. `mapOverlayToggle`

### Action and Event Behavior

1. UI actions call core extension command endpoints.
2. Extension results are presented through normalized result objects.
3. Live health/lifecycle updates stream from extension event channel.
4. Failed/degraded extensions are surfaced globally and per extension card.

## Data Ownership and Persistence

### Core-Owned Data

1. Extension registry metadata.
2. Lifecycle/runtime status.
3. Config projections and audit entries.
4. Health snapshots and event summaries.

### Extension-Owned Data

1. Extension-specific domain data and storage.
2. Backups for extension domain data handled by extension-defined policy.

## Security Model (v1)

1. Signed package enforcement for install/update.
2. Local trusted peer runtime communication, loopback-default.
3. Extension processes run with least-privilege filesystem scope (extension data directory and declared mounts only).
4. Full capability-token or mTLS command-level authorization deferred to future phase.

## Reference Alignment

### Meshtastic Integration Pattern

Adopt process management and service lifecycle principles from `Reticulum_Meshtastic_Integration`:

1. explicit service start/stop/status semantics
2. resilient reconnect behavior
3. clearly bounded bridge adapter logic

### R3AKT Pattern

Adopt contract-first and service-boundary principles from `R3AKT`:

1. strict command/event/result separation
2. service-oriented decomposition
3. API contract alignment tests

## Implementation Plan

### Phase 0: Contracts and Schemas

1. Add extension architecture docs and manifest schema.
2. Extend OpenAPI with extension lifecycle and command endpoints.
3. Define extension service HTTP contract docs and examples.

### Phase 1: Extension Core Backend

1. Implement extension registry persistence.
2. Implement signed package verifier and installer.
3. Implement supervisor abstraction for Linux and Windows.

### Phase 2: Command/Event Integration

1. Implement extension command gateway.
2. Implement extension event/result ingest.
3. Wire lifecycle and health streams to existing WS/event infrastructure.

### Phase 3: Legacy Convergence

1. Add adapters from legacy command surfaces to internal commands.
2. Add deprecation metadata and logging.
3. Validate parity for existing command workflows.

### Phase 4: Unified UI Command Center

1. Add extension overview and per-extension detail pages.
2. Convert sidebar/routes to include dynamic extension metadata.
3. Implement shell widget renderer and action dispatcher.

### Phase 5: Reference Extension Migration

1. Package Meshtastic integration as a managed extension package.
2. Validate lifecycle/health/command behavior end-to-end.
3. Add one northbound feature extension as a second reference.

### Phase 6: Hardening and Release

1. Complete contract, integration, and end-to-end test coverage.
2. Validate Linux and Windows lifecycle parity.
3. Publish migration guide and deprecation schedule.

## Test Plan

### Contract Tests

1. Manifest schema validation pass/fail suite.
2. OpenAPI route and payload conformance for new extension endpoints.
3. Internal API schema conformance for command/event/result envelopes.

### Runtime Tests

1. Signed install success.
2. Tampered package install failure.
3. Hot lifecycle transition correctness.
4. Crash loop handling and supervisor backoff behavior.

### Integration Tests

1. End-to-end command round-trip core <-> extension <-> UI.
2. Parallel multi-extension command handling.
3. Event propagation latency to UI stream within defined SLA.

### Platform Tests

1. Linux lifecycle parity verification.
2. Windows lifecycle parity verification.

## Acceptance Criteria

1. At least two extensions (southbound and northbound) operate as managed external processes.
2. No extension business logic executes in core process.
3. Core and UI use unified Internal API command/event semantics for extension operations.
4. Extension install/update enforces signature verification.
5. Operators can manage full extension lifecycle from command center and CLI without restarting RCH.
