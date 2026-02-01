# Sideband Telemetry Message Format

This document describes how Sideband structures telemetry over LXMF and how Reticulum Community Hub (RCH) ingests, stores, and republishes it for both LXMF clients and the northbound UI/API. It also documents how operator-managed markers are folded into the telemetry stream.

## LXMF envelope

- Telemetry is carried in LXMF message fields: a single snapshot is placed in `FIELD_TELEMETRY` (0x02) and streams or batches in `FIELD_TELEMETRY_STREAM` (0x03) (`reticulum_telemetry_hub/lxmf_daemon/LXMF.py:9`).
- `FIELD_TELEMETRY` is msgpack-encoded; RCH unpacks it, persists the decoded sensors, and logs a human-readable view (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py:180`).
- `FIELD_TELEMETRY_STREAM` is a plain list; each entry is `[peer_hash_bytes, unix_timestamp, packed_payload, appearance?]` assembled in `handle_command()` when RCH serves a telemetry request (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py:231`). Sideband accepts an optional appearance element; RCH sends `{4: ["person", b"\xff\xff\xff", b"\x00\x00\x00"]}`-style payloads where the list is `[icon_name, foreground_rgb_bytes, background_rgb_bytes]`. When marker metadata includes a symbol, the icon name comes from the marker symbol registry (MDI entries such as `friendly` -> `rectangle`) and the background color is derived from the symbol key.
- Telemetry replies intentionally leave the LXMF body empty so telemetry data is transported exclusively via the structured fields.

## Sensor map payload

- The payload under `FIELD_TELEMETRY` (or the third element of each stream entry) is a map keyed by numeric Sensor IDs (SIDs). SIDs are fixed in `reticulum_telemetry_hub/lxmf_telemetry/model/persistance/sensors/sensor_enum.py:1`.
- Each SID maps to a sensor-specific payload. RCH keeps the wire format identical to Sideband by using each sensor's `pack()`/`unpack()` methods when serializing (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py:308`) and deserializing (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py:326`).
- A `SID_TIME` entry is always ensured on egress so clients can reconstruct the snapshot time (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py:315`).

### Commonly used sensors and payload shapes

- **SID_TIME (0x01)** - unix timestamp (float or int). Packed and unpacked in `reticulum_telemetry_hub/lxmf_telemetry/model/persistance/sensors/time.py:21`.
- **SID_LOCATION (0x02)** - list of packed bytes: latitude and longitude (scaled microdegrees), altitude/speed/bearing/accuracy (centi-units), and `last_update` timestamp. Validation and sentinel-altitude cleanup live in `reticulum_telemetry_hub/lxmf_telemetry/model/persistance/sensors/location.py:34` and `_normalize_altitude()` at `.../location.py:98`.
- **SID_ACCELERATION (0x06)** - `[x, y, z]` floats (`reticulum_telemetry_hub/lxmf_telemetry/model/persistance/sensors/acceleration.py`).
- **SID_ANGULAR_VELOCITY (0x0C)** - `[x, y, z]` floats (`.../sensors/angular_velocity.py`).
- **SID_INFORMATION (0x0F)** - free-text string (`.../sensors/information.py`).
- **SID_PROXIMITY (0x0E)** - boolean `triggered` flag (`.../sensors/proximity.py`).
- **SID_RNS_TRANSPORT (0x19)** - dictionary describing the local Reticulum transport (enabled flag, identity hash, uptime, byte counters, rates, interface/path/ifstats blobs, plus any extra keys). Encoding and decoding lives in `reticulum_telemetry_hub/lxmf_telemetry/model/persistance/sensors/rns_transport.py:31`.
- **SID_LXMF_PROPAGATION (0x18)** - dictionary of propagation node state including peers and message counts (`.../sensors/lxmf_propagation.py`).
- **SID_CONNECTION_MAP (0x1A)** - structured map overlay data with point updates (`.../sensors/connection_map.py`).
- **SID_CUSTOM (0xFF)** - arbitrary application-defined payload (`.../sensors/generic.py`).

The full SID set is enumerated at `reticulum_telemetry_hub/lxmf_telemetry/model/persistance/sensors/sensor_enum.py:1`. Files in `reticulum_telemetry_hub/lxmf_telemetry/model/persistance/sensors/` document each payload shape in code.

## How RCH supports Sideband telemetry

- **Sampling and emission** - `TelemeterManager.snapshot()` packs enabled sensors into a SID-to-payload map (`reticulum_telemetry_hub/lxmf_telemetry/telemeter_manager.py:284`). `TelemetrySampler` ingests that snapshot for persistence and, when `broadcast_updates=True`, optionally broadcasts it to connected peers in an LXMF message with `FIELD_TELEMETRY` (`reticulum_telemetry_hub/lxmf_telemetry/sampler.py:189`).
- **Ingress and storage** - Incoming LXMF telemetry is decoded in `TelemetryController.handle_message()`; the controller persists the unpacked sensors to SQLite and logs a human-readable version (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py:167`).
- **Responding to requests** - When Sideband sends a telemetry command with `TelemetryController.TELEMETRY_REQUEST`, the controller collects the latest snapshot per peer, serializes each payload with `packb()`, and returns a list of telemetry entries in `FIELD_TELEMETRY_STREAM` (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py:231` and `.../telemetry_controller.py:295`). If the payload includes `TopicID`, RCH filters results to that topic and denies requests from senders who are not subscribed to it.
- **Northbound snapshots and streaming** - `GET /Telemetry` returns the same latest-per-peer view used by Sideband (with optional `topic_id` filtering) by calling `TelemetryController.list_telemetry_entries()` (`reticulum_telemetry_hub/northbound/routes_rest.py`). Telemetry updates are also pushed over WebSocket `/telemetry/stream` using `TelemetryBroadcaster`, which subscribes to telemetry ingestion events (`reticulum_telemetry_hub/northbound/websocket.py`).
- **Identity labeling** - Display names are resolved from LXMF announce metadata when available; the telemetry API and WebSocket include `display_name` and `identity_label` fields in each entry (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py` and `reticulum_telemetry_hub/northbound/websocket.py`).
- **Schema fidelity** - Sensor classes mirror Sideband's wire format (for example, signed micro-degree coordinates in `Location.pack()` and timestamp enforcement in `Time.pack()`), keeping RCH's stored snapshots and outbound messages byte-compatible with Sideband.

## Northbound telemetry access

- **REST snapshot** - `GET /Telemetry?since=...` returns `{ "entries": [...] }` with each entry containing `peer_destination`, `timestamp`, `telemetry`, and optional `display_name`. The payload is humanized using the sensor `unpack()` helpers (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py`).
- **WebSocket stream** - `/telemetry/stream` expects an auth message followed by `telemetry.subscribe` with a numeric `since` value and optional `topic_id`. The server responds with `telemetry.snapshot` and (when `follow` is true) `telemetry.update` messages (`reticulum_telemetry_hub/northbound/routes_ws.py` and `reticulum_telemetry_hub/northbound/websocket.py`).
- **Latest-per-peer behavior** - Both REST and WebSocket snapshots return the most recent telemetry per peer and exclude entries without a valid `SID_LOCATION`, matching Sideband live tracking expectations (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py`).

## Operator markers and telemetry integration

- **Marker creation and storage** - Operators create markers through the northbound API (`POST /api/markers`). `MarkerService` normalizes the marker type/symbol against the registry in `rch-symbols.yaml` and assigns each marker a Reticulum identity plus `object_destination_hash` (`reticulum_telemetry_hub/api/marker_service.py` and `reticulum_telemetry_hub/api/marker_symbols.py`).
- **Identity announcements** - Marker identities are announced periodically with metadata (`object_type=marker`, `marker_type`, `symbol`) so LXMF clients can recognize them as objects (`reticulum_telemetry_hub/reticulum_server/marker_objects.py`).
- **Telemetry payloads for markers** - On `marker.created` or `marker.updated`, RCH records a telemetry payload that includes `SID_LOCATION`, `SID_INFORMATION` (marker name), and `SID_CUSTOM` metadata such as `object_type`, `object_id`, `event_type`, `marker_type`, `symbol`, `category`, `origin_rch`, `position`, `time`, and `stale_at` (`reticulum_telemetry_hub/reticulum_server/marker_objects.py`).
- **Dispatch modes** - In gateway mode (hub + northbound), marker events are announced over Reticulum and recorded as telemetry so Sideband sees them alongside peer telemetry. In northbound-only mode, events are still recorded into `telemetry.db` for the UI, but no LXMF announce occurs (`reticulum_telemetry_hub/northbound/services.py`).
- **Staleness and TTL** - Markers default to a 24-hour TTL; expired markers are skipped for announces and telemetry dispatch, while position updates refresh `stale_at` (`reticulum_telemetry_hub/api/marker_service.py` and `reticulum_telemetry_hub/reticulum_server/marker_objects.py`).
- **Symbol resolution in the UI** - The UI fetches `/api/markers/symbols` and resolves marker icons using the symbol metadata returned by the API (`reticulum_telemetry_hub/api/marker_symbols.py` and `ui/src/utils/markers.ts`).

## Live tracking (Sideband "Start Live Tracking")

- When the operator taps **Start Live Tracking** on a contact, Sideband begins polling that peer with `TELEMETRY_REQUEST` commands that carry the last timestamp it has seen (or `[timestamp, collector_flag]`). Each poll expects just the deltas newer than that timestamp.
- RCH's command handler unwraps that timestamp and loads only telemetry entries at or after it (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py:231` -> `.../_load_telemetry`:108). Results are ordered newest-first and collapsed to a single freshest snapshot per peer via `_latest_by_peer()` (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py:373`).
- The reply is placed in `FIELD_TELEMETRY_STREAM` as a plain list of `[peer_hash_bytes, unix_timestamp, packed_payload, appearance]` entries (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py:293`). Sideband consumes that stream directly, updating the live track without any RCH-specific UI logic. The optional appearance entry uses the LXMF icon appearance field with MDI icon names and RGB colors.
- RCH only includes peers that have a valid `SID_LOCATION` payload; peers without location telemetry are omitted from responses.
- RCH ensures each payload always includes a `SID_TIME` sensor so Sideband can animate movement chronologically (`reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py:315`). Location readings ride along unchanged using Sideband's wire format (`reticulum_telemetry_hub/lxmf_telemetry/model/persistance/sensors/location.py:34`), so coordinates/altitude/speed remain compatible with Sideband's tracker.
- To make live tracking meaningful, keep RCH ingesting fresh telemetry. For local telemetry, enable `--daemon` so `TelemetrySampler` writes new snapshots to `telemetry.db`. Peer telemetry still depends on inbound LXMF updates; broadcast of local telemetry only occurs when `broadcast_updates=True` (`reticulum_telemetry_hub/lxmf_telemetry/sampler.py`).

### Example (humanized)

The decoded example at `docs/example_telemetry.json` shows stream responses with entries containing `peer_destination`, `timestamp`, and `telemetry` maps. A typical `telemetry` block includes `time`, `location`, `acceleration`, and `angular_velocity` objects that were humanized from the raw SID map using the sensor `unpack()` methods. The final entry demonstrates an operator marker payload, with `information` holding the marker name and `custom.marker` capturing marker metadata.
