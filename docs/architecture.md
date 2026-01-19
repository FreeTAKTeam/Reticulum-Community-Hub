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
