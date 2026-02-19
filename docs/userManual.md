# Reticulum Community Hub (RCH) User Manual

This manual is for:
- Operators running an RCH node
- LXMF users interacting with a hub
- Admin UI users

## What is RCH?

RCH is a Reticulum/LXMF hub for mesh coordination. It can relay and persist chat,
maintain topic subscriptions, store telemetry and attachments, manage map markers
and zones, and expose REST/WebSocket interfaces for operators and UI clients.

## Current Functionality Summary

RCH currently provides:
- LXMF message fan-out (broadcast, topic-scoped, and direct destination sends)
- Topic and subscriber management
- Public and protected LXMF command handling (with flexible payload key aliases)
- Telemetry ingest, storage, query, and stream updates
- File/image attachment persistence, retrieval, raw download, and delete
- Chat history and outbound chat dispatch with file/image attachments
- Operator marker CRUD with symbol registry support and marker telemetry events
- Zone (polygon) CRUD with geometry validation
- Identity moderation (ban, unban, blackhole) and routing snapshots
- Config management for both hub `config.ini` and Reticulum config file
- Reticulum discovery and interface capability reporting
- Gateway control endpoints (status, start, stop, immediate announce)
- Admin UI with Dashboard, WebMap, Topics, Files, Chat, Users, Configure, About, and Connect pages

## Client Support Matrix

### Sideband

Supported:
- Group chat
- Commands
- Telemetry
- TAK integration (chat and position)

### MeshChat

Supported:
- Group chat
- TAK integration (chat)

Not supported:
- Telemetry

### Columba

Supported:
- Group chat
- TAK integration (chat)

Not supported:
- Telemetry

## Operator Quickstart

### Install from PyPI

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install ReticulumCommunityHub
```

### Install from source

```bash
git clone https://github.com/FreeTAKTeam/Reticulum-Community-Hub.git
cd Reticulum-Community-Hub
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

### Start hub only (LXMF runtime)

```bash
python -m reticulum_telemetry_hub.reticulum_server \
    --storage_dir ./RTH_Store \
    --display_name "RCH"
```

### Start hub + API gateway in one process

```bash
python -m reticulum_telemetry_hub.northbound.gateway \
    --data-dir ./RTH_Store \
    --api-host 0.0.0.0 \
    --port 8000
```

### Run API server only (standalone app)

```bash
uvicorn reticulum_telemetry_hub.northbound.app:app --host 0.0.0.0 --port 8000
```

Notes:
- This mode is read-only unless you provide a message dispatcher in-process.
- Set `RTH_STORAGE_DIR` so the API reads the same storage/config as your hub runtime.

### Use the `rch` runtime controller

`rch` manages a background gateway process and writes runtime state/log files.

```bash
rch --data-dir ./RTH_Store --port 8000 start --log-level info
rch --data-dir ./RTH_Store --port 8000 status
rch --data-dir ./RTH_Store --port 8000 stop
```

Notes:
- `rch` global options (`--data-dir`, `--port`) must appear before the subcommand.
- The `rch start` workflow runs the API on `127.0.0.1` (local-only bind).
- For LAN/WAN API binds, run `reticulum_telemetry_hub.northbound.gateway` directly with `--api-host`.

## Storage Layout

Default storage directory is `./RTH_Store`.

Typical contents:
- `config.ini` (hub runtime configuration)
- `identity` (hub identity)
- `telemetry.db` (telemetry snapshots)
- `rth_api.sqlite` (topics/subscribers/files/images/chat/identity state)
- `events.jsonl` (shared event log)
- `files/` (stored file attachments)
- `images/` (stored image attachments)

When using `rch start`, you also get:
- `rch_state.json` (runtime PID/port metadata)
- `rch.log` (gateway stdout/stderr log)

## Configuration (`config.ini`)

RCH loads defaults from `<storage_dir>/config.ini`. If missing, it is bootstrapped
from `reticulum_telemetry_hub/config/default_config.ini`.

CLI flags override config file values.

Current config template supports these sections:
- `[app]`
- `[hub]`
- `[announce.capabilities]`
- `[reticulum]`
- `[interfaces]`
- `[propagation]`
- `[lxmf]`
- `[gpsd]`
- `[files]`
- `[images]`
- `[TAK]`
- `[telemetry]`

Useful runtime keys include:
- `announce_interval`
- `marker_announce_interval_minutes`
- `hub_telemetry_interval`
- `service_telemetry_interval`
- `embedded_lxmd`
- `services`
- `reticulum_config_path`
- `lxmf_router_config_path`

Config apply/rollback endpoints create and use backup files (`*.bak.*`).

## LXMF Command and Messaging Functionality

### Join and leave

- Send `join` to register your destination with the hub.
- Send `leave` to remove it.

For clients without command field support, prefix the body with `\\\`.

Examples:
```text
\\\join
```

```text
\\\{"Command":"SubscribeTopic","TopicID":"<TopicID>"}
```

### Command payload formats

Commands are accepted in multiple forms (object, stringified JSON, alias keys).
Required-field prompts are supported and follow-up payloads are merged.

Use:
- `Help` for available command names
- `Examples` for payload examples
- `docs/supportedCommands.md` for full public/protected command coverage

### Topic-targeted messages

- Create topic: `CreateTopic`
- Subscribe: `SubscribeTopic`
- Include `TopicID` in command fields/LXMF fields to scope delivery

### Telemetry request

Use numeric key `1` (`TelemetryRequest`) with a Unix timestamp:

```json
[{"1": 1700000000, "TopicID": "<TopicID>"}]
```

### Attachments

- Incoming LXMF file/image fields are persisted automatically.
- List/retrieve via commands: `ListFiles`, `ListImages`, `RetrieveFile`, `RetrieveImage`.
- Topic-tag attachments with `TopicID` or `AssociateTopicID`.
- API also supports raw download and delete operations.

## Northbound API Functionality

RCH exposes REST endpoints through FastAPI.

### Core routes

- `/Help`, `/Examples`
- `/Status` (protected)
- `/Events` (protected)
- `/Telemetry?since=<unix>&topic_id=<optional>`
- `/Message` (protected)
- `/Command/FlushTelemetry` (protected)
- `/Command/ReloadConfig` (protected)
- `/Command/DumpRouting` (protected)
- `/api/v1/app/info`
- `/openapi.yaml`

### Topic and subscriber routes

- `/Topic` (list/create/patch/delete)
- `/Topic/{topic_id}`
- `/Topic/Subscribe`
- `/Topic/Associate`
- `/Subscriber` (list/create/patch/delete, protected)
- `/Subscriber/Add` (protected)
- `/Subscriber/{subscriber_id}` (protected)

### Identity and client routes

- `/Client` (protected)
- `/Identities` (protected)
- `/Client/{identity}/Ban` (protected)
- `/Client/{identity}/Unban` (protected)
- `/Client/{identity}/Blackhole` (protected)
- `/RTH` (POST join, PUT leave)

### Config routes

Hub config:
- `GET /Config` (protected)
- `PUT /Config` (protected)
- `POST /Config/Validate` (protected)
- `POST /Config/Rollback` (protected)

Reticulum config:
- `GET /Reticulum/Config` (protected)
- `PUT /Reticulum/Config` (protected)
- `POST /Reticulum/Config/Validate` (protected)
- `POST /Reticulum/Config/Rollback` (protected)

Reticulum runtime insight:
- `GET /Reticulum/Interfaces/Capabilities` (protected)
- `GET /Reticulum/Discovery` (protected)

### File and image routes

- `/File`, `/File/{id}`, `/File/{id}/raw`, `DELETE /File/{id}`
- `/Image`, `/Image/{id}`, `/Image/{id}/raw`, `DELETE /Image/{id}`

### Chat routes

- `GET /Chat/Messages` (protected)
- `POST /Chat/Message` (protected)
- `POST /Chat/Attachment` (protected)

Attachment upload notes:
- `category` must be `file` or `image`
- max payload is 8 MiB per upload
- optional `sha256` integrity check is supported

### Marker and zone routes

Markers (protected):
- `GET /api/markers`
- `GET /api/markers/symbols`
- `POST /api/markers`
- `PATCH /api/markers/{object_destination_hash}`
- `PATCH /api/markers/{object_destination_hash}/position`
- `DELETE /api/markers/{object_destination_hash}`

Zones (protected):
- `GET /api/zones`
- `POST /api/zones`
- `PATCH /api/zones/{zone_id}`
- `DELETE /api/zones/{zone_id}`

Zone validation includes polygon size/shape constraints (min/max points, no self-intersections).

### Control routes (gateway mode)

Only available when running the gateway process (not plain standalone app):
- `GET /Control/Status` (protected)
- `POST /Control/Start` (protected)
- `POST /Control/Stop` (protected)
- `POST /Control/Announce` (protected)

## WebSocket Functionality

Streams:
- `/events/system`
- `/telemetry/stream`
- `/messages/stream`

All streams expect an auth message first:

```json
{"type":"auth","ts":"<iso8601>","data":{"token":"<optional>","api_key":"<optional>"}}
```

Then subscribe/send:

System stream:
```json
{"type":"system.subscribe","ts":"<iso8601>","data":{"include_status":true,"include_events":true,"events_limit":50}}
```

Telemetry stream:
```json
{"type":"telemetry.subscribe","ts":"<iso8601>","data":{"since":1700000000,"topic_id":"<optional>","follow":true}}
```

Message stream:
```json
{"type":"message.subscribe","ts":"<iso8601>","data":{"topic_id":"<optional>","source_hash":"<optional>","follow":true}}
```

```json
{"type":"message.send","ts":"<iso8601>","data":{"content":"hello","topic_id":"<optional>","destination":"<optional>"}}
```

Ping/pong keepalive is supported (`ping` from server, `pong` from client).

## Authentication Model

- Use `RTH_API_KEY` to enable API-key auth (`RCH_API_KEY` remains a compatible alias).
- Protected HTTP routes and WebSocket auth accept:
  - `X-API-Key: <key>`
  - `Authorization: Bearer <key>`
- Local loopback access is allowed without credentials.
- Remote access to protected surfaces is denied unless valid credentials are provided.

## Admin UI Functionality

The UI (in `ui/`) currently includes:

- `Dashboard`:
  - status cards, event feed, telemetry trend graph
  - backend controls (start, stop, status, announce)
- `WebMap`:
  - telemetry markers + operator markers
  - marker create/move/rename/delete
  - zone draw/edit/rename/delete
  - live cursor latitude/longitude readout
  - marker symbol catalog from `rch-symbols.yaml`
- `Topics`:
  - topic CRUD
  - subscriber CRUD and branch filtering
- `Files`:
  - file/image listing
  - raw download
  - image preview
  - delete from metadata and disk
- `Chat`:
  - DM/topic/broadcast composer
  - attachment upload and send
  - live message feed via WebSocket
- `Users`:
  - clients and identities list
  - moderation (ban/unban/blackhole)
  - join/leave identity
  - routing snapshot view
- `Configure`:
  - load/validate/apply/rollback hub config
  - Reticulum config editor
  - Reticulum discovery snapshot and interface import
  - diagnostics tools (status, dump routing, list clients)
- `About`:
  - app/runtime versions
  - destination hash
  - storage path inventory
  - command docs and examples viewer
- `Connect`:
  - base URL + WS URL
  - auth mode and credential fields

Additional UI behavior:
- Sidebar collapse/pin state is persisted.
- WebMap marker label visibility is toggleable and persisted.
- Map view (lat/lon/zoom) is persisted locally.

## Daemon Mode and Optional Services

Use daemon mode for telemetry workers and optional integrations:

```bash
python -m reticulum_telemetry_hub.reticulum_server \
    --storage_dir ./RTH_Store \
    --daemon \
    --service gpsd \
    --service tak_cot
```

Available optional services:
- `gpsd`
- `tak_cot`

RCH can run with:
- embedded LXMF router (`--embedded`)
- external `lxmd` (`--no-embedded` or config default)

## Python API Helpers (Attachments)

The internal service exposes helpers:
- `ReticulumTelemetryHubAPI.store_file(path, name=None, media_type=None, topic_id=None)`
- `ReticulumTelemetryHubAPI.store_image(path, name=None, media_type=None, topic_id=None)`
- `list_files()` / `list_images()`
- `retrieve_file(id)` / `retrieve_image(id)`
- `delete_file(id)` / `delete_image(id)`

## Troubleshooting

### The UI cannot connect

- Verify base URL/WS URL in Connect page.
- If remote, verify `RTH_API_KEY` and client auth headers/token.
- Confirm API is reachable on the expected host/port.

### WebSocket never becomes live

- Ensure client sends the initial `auth` message first.
- Confirm credentials (or local loopback access) are valid.

### Marker or zone updates fail

- Check API credentials for protected routes.
- For zones, ensure at least 3 points and non-self-intersecting geometry.

### Reticulum config apply succeeds but runtime did not change

- Reticulum config changes take effect after hub restart.

### Attachments are missing

- Verify `[files]` and `[images]` paths in `config.ini`.
- Ensure the process has write permission to storage directories.

## Getting Help

If you need help:
- Open an issue: https://github.com/FreeTAKTeam/Reticulum-Community-Hub
- Include client type (Sideband, MeshChat, Columba, or API/UI)
- Include approximate time and a short reproduction summary
