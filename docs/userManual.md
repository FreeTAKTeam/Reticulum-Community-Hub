# Reticulum Community Hub (RCH) User Manual

This manual is for:
- Operators running an RCH node
- LXMF users interacting with a hub
- Admin UI users

## What is RCH?

RCH is a hub that connects LXMF messaging clients. It forwards messages between
people, keeps topic-based groups, stores telemetry snapshots, and can relay
location and chat updates into TAK when that service is enabled.

## Client support matrix

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

## Operator quickstart

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
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

### Start the hub

```bash
python -m reticulum_telemetry_hub.reticulum_server \
    --storage_dir ./RCH_Store \
    --display_name "RCH"
```

### Storage layout

The storage directory (default `./RCH_Store`) contains:

- `config.ini` (runtime configuration)
- `identity` (hub identity)
- `telemetry.db` (telemetry snapshots)
- `reticulum.db` (client and topic state)
- `rch_api.sqlite` (northbound API state)
- `events.jsonl` (event log)
- `files/` (stored file attachments)
- `images/` (stored image attachments)

### Configuration (`config.ini`)

RCH reads defaults from a unified `config.ini` file in the storage directory.
CLI flags override values from the file.

Example configuration:

```ini
[app]
name = Reticulum Community Hub
version = 0.0.0
description = Public-facing hub for the mesh network

[hub]
display_name = RCH
announce_interval = 60
hub_telemetry_interval = 600
service_telemetry_interval = 900
log_level = info
embedded_lxmd = false
services = gpsd, tak_cot
reticulum_config_path = ~/.reticulum/config
lxmf_router_config_path = ~/.lxmd/config
telemetry_filename = telemetry.ini

[reticulum]
enable_transport = true
share_instance = true

[interfaces]
type = TCPServerInterface
interface_enabled = true
listen_ip = 0.0.0.0
listen_port = 4242

[propagation]
enable_node = yes
announce_interval = 10
propagation_transfer_max_accepted_size = 1024

[lxmf]
display_name = RCH_router

[gpsd]
host = 127.0.0.1
port = 2947

[files]
# path = /var/lib/rth/files

[images]
# directory = /var/lib/rth/images

[TAK]
cot_url = tcp://127.0.0.1:8087
callsign = RCH
poll_interval_seconds = 30
keepalive_interval_seconds = 60
# tls_client_cert = /path/to/cert.pem
# tls_client_key = /path/to/key.pem
# tls_ca = /path/to/ca.pem
# tls_insecure = true
tak_proto = 0
fts_compat = 1
```

Notes:
- `services` is a comma-separated list of daemon services to start by default.
- `reticulum_config_path` and `lxmf_router_config_path` point to external configs
  when you run against existing Reticulum/LXMF daemons.
- File and image storage directories default to `<storage_dir>/files` and
  `<storage_dir>/images` when not set.

### Command-line options

| Flag | Description |
| --- | --- |
| `--config` | Path to `config.ini` (defaults to `<storage_dir>/config.ini`). |
| `--storage_dir` | Storage directory path (defaults to `./RCH_Store`). |
| `--display_name` | Display name for the hub identity (defaults to `[hub].display_name`). |
| `--announce-interval` | Seconds between LXMF announces (defaults to `[hub].announce_interval`). |
| `--hub-telemetry-interval` | Seconds between local telemetry snapshots. |
| `--service-telemetry-interval` | Seconds between service telemetry polls. |
| `--log-level` | Log level to emit (`error`, `warning`, `info`, `debug`). |
| `--embedded` / `--no-embedded` | Run the LXMF daemon in-process (default from `[hub].embedded_lxmd`). |
| `--daemon` | Start telemetry collectors and optional services. |
| `--service NAME` | Enable an optional service (repeat for multiple). |

### Running as a service (systemd)

Create `/etc/systemd/system/RCH.service`:

```ini
[Unit]
Description=Reticulum Community Hub
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/RCH
Restart=on-failure
User=root
WorkingDirectory=/usr/local/bin
ExecReload=/bin/kill -HUP $MAINPID

[Install]
WantedBy=multi-user.target
```

Enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable RCH.service
sudo systemctl start RCH.service
```

## Using RCH with LXMF clients

### Join the hub

1. Add or select the RCH identity in your LXMF client.
2. Start a chat and send `join`:
   - If your client supports the `Commands` field (numeric field ID `9`):
     ```json
     [{"Command": "join"}]
     ```
   - If your client does not support `Commands`, prefix the message body with
     `\\\` so the hub treats it as a command:
     ```
     \\\join
     ```

If a sender has not joined yet, RCH automatically replies with `getAppInfo`
so the client can identify the hub.

### Sending commands

Commands are JSON objects inside the `Commands` field. The command name may be
supplied as `Command` or numeric key `0`. Supported shapes:

```json
[{"Command": "CreateTopic", "TopicName": "Weather", "TopicPath": "environment/weather"}]
```

```json
["{\"Command\":\"CreateTopic\",\"TopicName\":\"Weather\",\"TopicPath\":\"environment/weather\"}"]
```

```json
[{"0": "{\"Command\":\"CreateTopic\",\"TopicName\":\"Weather\",\"TopicPath\":\"environment/weather\"}"}]
```

If a required field is missing, the hub replies with a prompt and merges the
follow-up payload. You can respond with only the missing fields.

Use `Help` for a short list of commands and `Examples` for example payloads.
The full list of commands is in `docs/supportedCommands.md`.

### Topic-targeted messages

Create a topic and subscribe:

```json
[{"Command": "CreateTopic", "TopicName": "Weather", "TopicPath": "environment/weather"}]
```

```json
[{"Command": "SubscribeTopic", "TopicID": "<TopicID>"}]
```

Any message with a `TopicID` in the command payload (or LXMF fields) is only
forwarded to subscribers of that topic.

### Telemetry requests (Sideband)

Send `TelemetryRequest` using numeric key `1` with a unix timestamp:

```json
[{"1": 1700000000}]
```

If you include `TopicID`, the hub filters telemetry to that topic and denies
requests from senders who are not subscribed to it.

### Attachments

- List stored items: `ListFiles`, `ListImages`
- Retrieve items: `RetrieveFile`, `RetrieveImage` (by ID)
- Associate stored attachments with a topic: `AssociateTopicID`

Attachments are delivered in LXMF fields (`FIELD_FILE_ATTACHMENTS` and
`FIELD_IMAGE`) so clients like Sideband can save them directly. Incoming
attachments sent in those fields are persisted automatically to the configured
storage directories.

## Northbound API and admin UI

The northbound API is a FastAPI service that maps REST to LXMF commands and
streams telemetry/events over WebSocket.

Run it alongside the hub (recommended for chat/message sending):

```bash
python -m reticulum_telemetry_hub.northbound.gateway \
    --storage_dir ./RCH_Store \
    --api-host 0.0.0.0 \
    --api-port 8000
```

Run only the API server (read-only unless you provide a message dispatcher):

```bash
uvicorn reticulum_telemetry_hub.northbound.app:app --host 0.0.0.0 --port 8000
```

Set `RCH_API_KEY` to require auth on protected endpoints. The API accepts
either the `X-API-Key` header or a bearer token in `Authorization`.

If you run the API separately from the hub process, set `RCH_STORAGE_DIR` to
the same storage directory so the API reads the correct config and databases.

The OpenAPI spec is in `API/ReticulumCommunityHub-OAS.yaml` and is exposed at
`/openapi.yaml` when the repo is available on disk.

The admin UI lives in `ui/`. See `ui/README.md` for dev and build steps.

## Daemon mode and services

Use `--daemon` to enable telemetry sampling and optional services. Services can
be provided via `--service` flags or the `[hub].services` config value.

Available services:
- `gpsd` (requires gpsd + gpsdclient)
- `tak_cot` (bridges telemetry and chat into a TAK endpoint)

RCH can run the LXMF router in-process with `--embedded` or connect to an
external `lxmd` daemon (default). Use `reticulum_config_path` and
`lxmf_router_config_path` to point at existing Reticulum/LXMF configs when
running against external daemons.

## Python API (attachments)

The API service exposes helpers for recording attachments stored on disk:

- `ReticulumCommunityHubAPI.store_file(path, name=None, media_type=None, topic_id=None)`
- `ReticulumCommunityHubAPI.store_image(path, name=None, media_type=None, topic_id=None)`
- `list_files()` / `list_images()` return stored metadata.
- `retrieve_file(id)` / `retrieve_image(id)` return a single record by ID.

## Troubleshooting

### I cannot see the hub or other users

- Confirm the client is talking to the correct hub identity.
- Verify the client is subscribed to the right topic.
- Check that the hub process is running and reachable.

### Commands do not work

- Ensure you are sending valid JSON in the `Commands` field or using the `\\\`
  escape prefix.
- Run `Help` or `Examples` to confirm the hub is responding.

### Telemetry is missing

- Telemetry is only supported in Sideband.
- Ensure telemetry is enabled in the Sideband settings.
- Confirm the hub is running with telemetry sampling enabled if you expect
  fresh telemetry snapshots.

### Attachments are not stored

- Confirm file/image storage paths in `config.ini`.
- Ensure the hub process has write access to those directories.

## Getting help

If you need help:

- Open an issue on GitHub: https://github.com/FreeTAKTeam/Reticulum-Community-Hub
- Include your client name (Sideband, MeshChat, or Columba).
- Share the time and a short description of the issue.
