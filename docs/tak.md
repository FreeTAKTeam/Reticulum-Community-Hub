# TAK / CoT Integration

## Overview
- The hub can relay Reticulum telemetry and chat into TAK as Cursor-on-Target (CoT) events. Integration is implemented under `reticulum_telemetry_hub/atak_cot` and uses [PyTAK](https://pypi.org/project/pytak/) to talk to a TAK server.
- `TakConnector` builds CoT events (location, telemetry-derived, chat, and keepalive) and hands them to `PytakClient`, which wraps PyTAK queue workers to serialize/send the XML payloads.
- The `tak_cot` daemon service (`reticulum_telemetry_hub/reticulum_server/services.py`) schedules periodic CoT traffic: a takPong keepalive plus the latest location snapshot every `poll_interval_seconds`.

## Configuration
- Connector settings live in `TakConnectionConfig` (`reticulum_telemetry_hub/config/models.py`). Defaults: `tcp://127.0.0.1:8087`, callsign `RTH`, poll interval `30s`, TAK protocol `0`, FTS compatibility `1`, TLS options empty.
- `TakConnectionConfig.to_config_parser()` produces the `fts` config section that PyTAK expects:
  - `COT_URL` (`tcp://` or `udp://`), `CALLSIGN`, `TAK_PROTO`, `FTS_COMPAT`
  - TLS fields: `SSL_CLIENT_CERT`, `SSL_CLIENT_KEY`, `SSL_CLIENT_CAFILE`, `SSL_VERIFY` (set to `false` when `tls_insecure=True`)
- The connector derives the CoT contact endpoint from `COT_URL` as `<host>:<port>:<scheme>` (e.g., `127.0.0.1:8087:tcp`) and uses it in the `detail.contact` element.

## Components and flow
- `PytakClient` (`reticulum_telemetry_hub/atak_cot/pytak_client.py`)
  - Provides `create_and_send_message(...)` which spins up PyTAK TX/RX queue workers and accepts `Event`, XML `Element`, bytes, strings, or dicts.
  - `SendWorker` converts payloads to XML bytes; `ReceiveWorker` can parse inbound CoT into `Event` objects when `parse_inbound=True` (the connector sets `False` because only TX is needed).
  - Defaults to an internal `ConfigParser` if none is provided; normally the connector passes `TakConnectionConfig.to_config_parser()`.
  - Runs a dedicated background asyncio loop to keep the PyTAK session alive across repeated calls (including from synchronous threads) and logs connection success/failure through both the PyTAK logger and the RNS console.

- `TakConnector` (`reticulum_telemetry_hub/atak_cot/tak_connector.py`)
  - Location source: prefers live `TelemeterManager` sensors, falls back to the persisted `TelemetryController` store. Produces a `LocationSnapshot` with lat/lon/altitude/speed/bearing/accuracy.
  - Identity mapping: UIDs and callsigns come from the LXMF peer hash when available; optional `identity_lookup` can replace hashes with human-readable labels.
  - Location / telemetry CoT (`a-f-G-U-C`): `send_latest_location()` and `send_telemetry_event(...)` call `_build_event_from_snapshot(...)`, which sets:
    - `how=h-g-i-g-o`, start/stale timestamps based on last update and `poll_interval_seconds`
    - `detail`: `contact` (callsign + endpoint), default group (`Yellow` / `Team Member`), `track` (course/speed), `takv` (platform metadata constants; version set to the current RTH release, e.g., `0.44.0`), `uid` (Droid callsign), and `status` (battery currently `0.0`)
  - Chat CoT (`b-t-f`): `send_chat_event(...)` wraps LXMF message text in a GeoChat payload with `Chat`, `ChatGroup`, `ChatHierarchy`, `Link`, and `Remarks` detail. Uses current hub location if available; builds a unique `GeoChat.<identifier>-chat-<ts>-<suffix>` UID.
  - Keepalive: `send_keepalive()` emits `tak_pong()` from PyTAK to keep the TAK session alive.

## Runtime wiring
- The main hub (`reticulum_telemetry_hub/reticulum_server/__main__.py`) instantiates `TakConnector` with:
  - The active config manager’s `tak_config`
  - Live telemetry providers (`TelemeterManager`, `TelemetryController`)
  - An identity lookup used to render peer hashes as labels in CoT `callsign`s
- Telemetry fan-out:
  - `TelemetryController.register_listener` calls `_handle_telemetry_for_tak`, which invokes `TakConnector.send_telemetry_event(...)` for every inbound telemetry payload that contains location data.
  - The `tak_cot` daemon service runs `send_latest_location()` every `poll_interval_seconds` and dispatches a keepalive `takPong` every 60 seconds to maintain the session.
- Chat relay:
  - Inbound LXMF deliveries handled in `ReticulumTelemetryHub.delivery_callback` are mirrored into TAK via `TakConnector.send_chat_event(...)` when the message body is non-empty.

## Usage tips
- Ensure a location sensor is enabled (e.g., via `TelemeterManager` or the optional `gpsd` service); otherwise `send_latest_location()` and `send_telemetry_event()` no-op and log a warning.
- When pointing at a remote TAK server, set the TLS fields in `TakConnectionConfig`; PyTAK reads them directly from the generated `ConfigParser`.
- For debugging, you can inspect the `Event.to_xml()` output (see `tests/test_tak_connector.py` for expectations) to verify UID, contact endpoint, group, track, and takv metadata before sending.
