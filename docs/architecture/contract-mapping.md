# R3AKT Contract Mapping (Backend)

This document maps imported R3AKT AsyncAPI contracts to implemented backend handlers in RCH.

## Canonical Inputs

- `docs/architecture/asyncapi/r3akt-mission-sync-lxmf.asyncapi.yaml`
- `docs/architecture/asyncapi/r3akt-checklist-lxmf.asyncapi.yaml`
- `docs/architecture/R3AKT_Domain_Class_Diagram.mmd`

## LXMF Envelope Mapping

- `FIELD_COMMANDS (0x09)`: command envelopes with `command_type`, `args`, `command_id`, `source`, `timestamp`, optional `correlation_id`.
- `FIELD_RESULTS (0x0A)`: standard `{status: accepted|rejected|result}` payloads.
- `FIELD_EVENT (0x0D)`: mission/checklist event envelopes with `event_type` and `payload`.
- `FIELD_GROUP (0x0B)`: preserved from ingress to egress for scoped fan-out compatibility.

## Mission-Sync Commands

- `mission.*`, `topic.*` are routed by `reticulum_telemetry_hub/mission_sync/router.py`.
- Capability ACL is enforced via persisted grants in `identity_capability_grants`.
- Envelope source identity must match transport-derived sender identity.
- Legacy command path (`Command` / `PLUGIN_COMMAND`) remains active via `command_manager.py`.

## Checklist Commands

- `checklist.*` are routed by `reticulum_telemetry_hub/checklist_sync/router.py`.
- Checklist/domain state is persisted through `reticulum_telemetry_hub/mission_domain/service.py` and `r3akt_*` tables.
- Domain events and snapshots are persisted in `r3akt_domain_events` and `r3akt_domain_snapshots` with retention.

## HTTP Compatibility

- Canonical join/leave: `/RCH` (`POST`, `PUT`).
- Backward-compatible alias remains active: `/RTH` (`POST`, `PUT`).

## Backend Domain Routes

- Checklist lifecycle: `/checklists/*`.
- Registry + ACL + domain audit: `/api/r3akt/*`.
- Mission association routes now include parent/zone/rde operations and
  assignment/team-member link management.

## Deprecation Notes

- `/RTH` and legacy command payloads are retained for dual-stack rollout.
- Migration to mission/checklist command envelopes can proceed incrementally per client capability.

## Compatibility Timeline

1. Feature-branch and pre-release validation:
   `/RCH`, `/RTH`, mission/checklist envelopes, and legacy command payloads all
   remain enabled.
2. First release containing full R3AKT backend milestones:
   `/RCH` is canonical; `/RTH` and legacy command payloads are documented as
   compatibility-only.
3. Post-rollout stabilization:
   keep `/RTH` and legacy payload support for at least two stable minor releases
   and a minimum 90-day notice window before any removal decision.
4. Removal:
   not scheduled in this branch; final cutover is a separate change after
   compatibility SLOs and client migration checks pass.
