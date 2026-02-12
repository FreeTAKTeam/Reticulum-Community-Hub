# RCH Architecture

## Overview

Reticulum Community Hub (RCH) is split into a Reticulum/LXMF runtime, a storage
layer, telemetry ingestion and sampling, a northbound API, and an admin UI. It
also includes optional services (gpsd, tak_cot) and an internal adapter for
transport-agnostic integrations.

## Core components

- `reticulum_telemetry_hub/reticulum_server/`: Hub runtime, command manager,
  message dispatch, event log, outbound queue, and Reticulum wiring.
- `reticulum_telemetry_hub/api/`: API service and storage facade for topics,
  subscribers, identities, and attachments.
- `reticulum_telemetry_hub/lxmf_telemetry/`: Telemetry ingestion, persistence,
  and sampling/broadcast logic.
- `reticulum_telemetry_hub/northbound/`: FastAPI REST + WebSocket interface.
- `reticulum_telemetry_hub/config/`: Unified config loader and runtime models.
- `reticulum_telemetry_hub/atak_cot/`: TAK/CoT bridge helpers.
- `reticulum_telemetry_hub/internal_api/`: Internal API schemas and adapters.

## Data flows

- **LXMF commands**: inbound LXMF messages are normalized by the command manager,
  validated, applied via the API service, and replied to over LXMF.
- **Telemetry**: telemetry fields are decoded and stored in `telemetry.db`.
  Telemetry requests return a `FIELD_TELEMETRY_STREAM` payload, optionally
  filtered by topic.
- **Northbound API**: REST endpoints map to the same command and storage paths,
  while WebSocket streams read from the event log and telemetry broadcaster.

## DR-2 Structured SITREP Generation and Parsing

RCH supports structured SITREP objects with:

- `priority`
- `coordinates_ref` (reference to telemetry objects, not raw coordinates)
- `notes`
- `timestamp`
- `origin_identity`

### SITREP datapack standard

For compact wire representation, SITREP packets use canonical datapack keys:

- `v`: schema version
- `p`: priority
- `r`: coordinates reference (`telemeter_id` + `sensor_id` + sample time)
- `n`: notes
- `t`: timestamp
- `o`: origin identity

### Secure Reticulum transport

- SITREP datapacks are wrapped in a Reticulum envelope for transport.
- When destination identity material is available, payload is encrypted before
  transmit.
- Imported encrypted payloads are decrypted, then parsed back into structured
  SITREP objects.

### Parsing and persistence/logging

- Parsed SITREPs are reconstructed as first-class domain objects.
- Each successful import writes a `MissionChange` record
  (`change_type = SITREP_IMPORTED`) linked to the SITREP identity.
- `Mission` and `Task` remain first-class planning concepts; SITREPs can be
  associated to mission/task context and reflected in mission change history.
- A `LogEntry` is also written for auditability and traceability of parsing,
  validation, and persistence outcomes.

## DR-8 Asset and Resource Registry

R3AKT supports structured registry management for:

- Assets
- Mission task assignments
- Client/team-member profiles
- Skills
- Team member and skill mappings

### Domain model coverage

- `Asset` tracks resource identity, type, lifecycle status, location, and notes.
- `MissionTaskAssignment` links `Mission`, `checklistTask`, and `TeamMember`
  (with optional asset usage and assignment metadata).
- `ClientProfile` provides structured profile metadata for each `TeamMember`.
- `Skill` defines a reusable skill catalog.
- `TeamMemberSkill` models the many-to-many mapping between team members and
  skills, including validation metadata.
- `TaskSkillRequirement` captures minimum skill requirements per task.

## Reference documents

- `docs/internal-api.md` (normative internal API contract)
- `docs/internal-api-overview.md` (internal API overview)
- `docs/internal-api-examples.md` (example envelopes)
- `docs/reticulum-adapter-mapping.md` (LXMF to internal mapping)
- `API/ReticulumCommunityHub-OAS.yaml` (REST/OpenAPI spec)
- `docs/TelemetryDocumentation.md` (Sideband telemetry wire format)
- `docs/tak.md` (TAK integration)
- `ui-architecture.md` (UI architecture)
- `docs/ui-design.md` (UI design spec)
- `docs/ui-wireframe.md` (UI wireframes)
- `ui/README.md` (UI dev/build steps)
- `docs/dataArchitecture.md` (domain class diagram including DR-2 SITREP model)
- `docs/architecture/R3AKT_Domain_Class_Diagram.mmd` (standalone Mermaid source)
