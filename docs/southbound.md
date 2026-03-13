# RCH Southbound LXMF Contract

This document describes the southbound side of Reticulum Community Hub (RCH):
the LXMF transport boundary between the hub runtime and Reticulum/LXMF clients
such as Sideband, MeshChat, and custom peers.

In short:

- Commands come in through `FIELD_COMMANDS` (`0x09`) when the client supports
  LXMF command fields.
- Clients without `FIELD_COMMANDS` support can send an escape-prefixed body
  starting with `\\\`.
- Replies do not use `FIELD_COMMANDS`.
- Standard command replies come back as a direct LXMF message with a text body,
  `FIELD_RESULTS` (`0x0A`), and `FIELD_EVENT` (`0x0D`).
- Specialized replies use their own fields:
  `FIELD_TELEMETRY_STREAM` (`0x03`) for telemetry responses and
  `FIELD_FILE_ATTACHMENTS` (`0x05`) / `FIELD_IMAGE` (`0x06`) for attachment
  retrieval.

## Scope

Southbound in RCH means the LXMF-facing runtime in:

- `reticulum_telemetry_hub/reticulum_server/__main__.py`
- `reticulum_telemetry_hub/reticulum_server/command_manager.py`
- `reticulum_telemetry_hub/lxmf_telemetry/telemetry_controller.py`
- `reticulum_telemetry_hub/mission_sync/router.py`
- `reticulum_telemetry_hub/checklist_sync/router.py`

This is distinct from the northbound REST/WebSocket API exposed by FastAPI.

## Field map

| Direction | LXMF field | Purpose | Notes |
| --- | --- | --- | --- |
| Inbound | `FIELD_COMMANDS` (`0x09`) | Primary command envelope | Expected to be a list of command objects. |
| Inbound | Message body with `\\\` prefix | Fallback command transport | Used only when `FIELD_COMMANDS` is absent. |
| Inbound | `FIELD_TELEMETRY` (`0x02`) | Single telemetry snapshot | Persisted by `TelemetryController`. |
| Inbound | `FIELD_TELEMETRY_STREAM` (`0x03`) | Batch telemetry stream | Also accepted inbound and persisted. |
| Inbound | `FIELD_FILE_ATTACHMENTS` (`0x05`) | File upload payloads | Persisted before command handling. |
| Inbound | `FIELD_IMAGE` (`0x06`) | Image upload payloads | Persisted before command handling. |
| Inbound/Outbound | `FIELD_THREAD` (`0x08`) | Conversation thread context | Echoed back in replies/telemetry when present. |
| Inbound/Outbound | `FIELD_GROUP` (`0x0B`) | Group/topic conversation context | Echoed back in replies/telemetry when present. |
| Outbound | `FIELD_RESULTS` (`0x0A`) | Structured command result payload | Standard command/mutation response field. |
| Outbound | `FIELD_TELEMETRY_STREAM` (`0x03`) | Telemetry query response payload | Used instead of `FIELD_RESULTS` for snapshot streams. |
| Outbound | `FIELD_FILE_ATTACHMENTS` (`0x05`) | File retrieval response payload | Images also include this field for compatibility. |
| Outbound | `FIELD_IMAGE` (`0x06`) | Image retrieval response payload | Present for image retrieval responses. |
| Outbound | `FIELD_EVENT` (`0x0D`) | Structured response/event metadata | Added to command, telemetry, relay, and outbound messages. |
| Outbound | `FIELD_RENDERER` (`0x0F`) | Markdown renderer hint | Used by `Help` and `Examples`. |

## Receive pipeline

Inbound LXMF processing currently works in this order:

1. The delivery callback validates the message signature and logs the delivery.
2. If `FIELD_COMMANDS` is present, that payload is used as the command list.
3. Otherwise, the hub checks for an escape-prefixed body beginning with `\\\`.
4. Before commands are executed, inbound `FIELD_FILE_ATTACHMENTS` and
   `FIELD_IMAGE` payloads are normalized, written to disk, and recorded in the
   API database.
5. Commands are split into three buckets:
   - mission-sync commands: entries with `command_type` not starting with
     `checklist.`
   - checklist-sync commands: entries with `command_type` starting with
     `checklist.`
   - legacy/plugin commands: entries using `Command` / `plugin_command`
6. Each bucket is routed to its handler and turned into direct LXMF replies.
7. If a reply carries attachments, the hub also emits a second text-only reply
   as a compatibility mirror.

## Command ingress

### Primary form: `FIELD_COMMANDS`

The primary southbound command path is `FIELD_COMMANDS` (`0x09`).

Legacy/plugin commands typically look like:

```json
[
  {
    "Command": "ListTopic"
  }
]
```

RCH also normalizes several client-specific variants inside that field:

- stringified JSON objects
- Sideband numeric-key wrappers
- positional numeric payloads for known commands
- common key aliases such as `topicId`, `topic_id`, and `TopicID`

Mission/checklist sync commands also use `FIELD_COMMANDS`, but they are routed
by `command_type` instead of `Command`:

```json
[
  {
    "command_id": "cmd-123",
    "command_type": "mission.registry.mission.list",
    "source": {
      "rns_identity": "<identity-hash>"
    },
    "args": {}
  }
]
```

### Fallback form: escape-prefixed body

If a client cannot set `FIELD_COMMANDS`, the hub accepts a body that starts
with `\\\`.

Examples:

```text
\\\join
```

```text
\\\{"Command":"SubscribeTopic","TopicID":"<TopicID>"}
```

```text
\\\[{"Command":"ListTopic"}]
```

The body may be:

- a bare command name such as `join`
- a JSON object
- a JSON list of objects

Malformed escape-prefixed payloads are rejected with a text error reply.

## Reply contract

### Standard command replies

Standard command replies are generated by `CommandManager._reply()` and then
finalized with command metadata.

Properties:

- Sent as a direct LXMF message (`desired_method = DIRECT`)
- Human-readable text remains in the LXMF body
- `FIELD_RESULTS` contains the structured result value
- `FIELD_EVENT` contains structured metadata such as:
  - `event_type`
  - `status`
  - `ts`
  - `source`
  - `command` for finalized command results
- `FIELD_THREAD` and `FIELD_GROUP` are copied from the inbound message when
  present

Important: RCH does not place responses inside `FIELD_COMMANDS`. `FIELD_COMMANDS`
is ingress-only in the current implementation.

### Result payload shape

`FIELD_RESULTS` is derived from the reply body:

- if the body is valid JSON, `FIELD_RESULTS` contains the parsed JSON object
- if the body is short plain text, `FIELD_RESULTS` contains that text
- if the body is long plain text, `FIELD_RESULTS` contains a truncated preview
  object

This means a client can read either the body or `FIELD_RESULTS`, but the
structured field is the reliable machine-oriented contract.

## Telemetry behavior

Telemetry uses the standard command ingress path, but the reply field is
different.

### Request form

The Sideband-compatible request is the numeric-key form:

```json
[
  {
    "1": 1700000000,
    "TopicID": "<TopicID>"
  }
]
```

Notes:

- Numeric key `1` is `TelemetryRequest`
- `TopicID` is optional and scopes results to a topic
- If the sender is not subscribed to the requested topic, the request is denied

### Response form

Telemetry replies are sent as direct LXMF messages with:

- `FIELD_TELEMETRY_STREAM` containing a plain list of entries
- `FIELD_EVENT` with `event_type = "rch.telemetry.response"`
- relayed `FIELD_THREAD` / `FIELD_GROUP` when present

Each telemetry entry is:

```text
[peer_hash_bytes, unix_timestamp, packed_payload, appearance]
```

Unlike standard command replies, the telemetry payload is returned in
`FIELD_TELEMETRY_STREAM`, not in `FIELD_COMMANDS`.

For success responses, the body is intentionally left empty. Error and denial
paths use text plus `FIELD_RESULTS`.

## Attachment behavior

### Inbound uploads

Inbound attachments are persisted automatically from:

- `FIELD_FILE_ATTACHMENTS`
- `FIELD_IMAGE`

If the same inbound message also carries an `AssociateTopicID` command, the
stored attachment records are tagged with that `TopicID`.

The hub sends acknowledgement replies such as:

- `Stored files:`
- `Stored images:`
- `Attachment errors:`

These acknowledgements are normal text replies built through `_reply_message()`,
so they carry `FIELD_EVENT` and any relayed thread/group context, but not a new
`FIELD_COMMANDS` wrapper.

### Retrieval replies

`RetrieveFile` and `RetrieveImage` produce direct replies with:

- human-readable body text
- `FIELD_RESULTS`
- attachment payload fields

Field usage:

- `RetrieveFile` -> `FIELD_FILE_ATTACHMENTS`
- `RetrieveImage` -> `FIELD_IMAGE` and `FIELD_FILE_ATTACHMENTS`

For compatibility, the hub also emits a second text-only mirror when a reply
contains attachment fields.

## Mission and checklist sync behavior

Mission-sync and checklist-sync commands still enter through `FIELD_COMMANDS`,
but they are detected by `command_type`.

Replies:

- do not use `FIELD_COMMANDS`
- use `FIELD_RESULTS` as the structured envelope
- preserve `FIELD_GROUP` when present
- optionally include `FIELD_EVENT`
- use text bodies of `mission-sync` or `checklist-sync`

This keeps the southbound response shape aligned with the rest of the hub:
commands in through `FIELD_COMMANDS`, results out through `FIELD_RESULTS`.

## Mission command specification

Mission commands are the R3AKT southbound control-plane envelopes handled by
`reticulum_telemetry_hub/mission_sync/router.py`.

### Mission command envelope

The LXMF `FIELD_COMMANDS` value is expected to be a list of mission envelope
objects matching this schema:

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `command_id` | yes | string | Client-generated command identifier. If omitted or blank, the hub synthesizes one for rejection/error paths. |
| `source.rns_identity` | yes | string | Must match the LXMF transport sender identity or the command is rejected as `unauthorized`. |
| `timestamp` | yes | ISO-8601 datetime | Client-side command creation time. |
| `command_type` | yes | string | Selects the mission operation. Values not starting with `checklist.` route to the mission-sync router. |
| `args` | yes | object | Command-specific arguments. |
| `correlation_id` | no | string | Optional client correlation token echoed into replies. |
| `topics` | no | string array | Optional logical mission/event topics copied into emitted event envelopes. |

Encoding rules:

- Mission command envelopes are JSON-compatible objects.
- Clients should send normal object/list values in `FIELD_COMMANDS`, not a
  MessagePack blob.
- The normative mission-sync contract declares `application/json` as the
  content type.
- This differs from telemetry payload fields, where packed sensor payloads are
  MessagePack-encoded.

Canonical example:

```json
[
  {
    "command_id": "cmd-123",
    "source": {
      "rns_identity": "<sender-identity>"
    },
    "timestamp": "2026-03-13T12:00:00Z",
    "command_type": "mission.registry.log_entry.upsert",
    "args": {
      "mission_uid": "mission-1",
      "content": "Operator note",
      "callsign": "EAGLE-1"
    },
    "correlation_id": "ui-save-42",
    "topics": ["mission-1", "audit"]
  }
]
```

### Routing and authorization rules

- Commands with `command_type` beginning with `checklist.` are not mission
  commands and are routed to `checklist_sync`.
- All other `command_type` values in `FIELD_COMMANDS` are treated as
  mission-sync commands.
- The envelope source identity must match the transport-derived sender
  identity.
- Each `command_type` is capability-gated. Authorization is mission-aware when
  the command payload carries a mission identifier.
- Supported mission `command_type` values are enumerated in
  [supportedCommands.md](supportedCommands.md) and in
  `docs/architecture/asyncapi/r3akt-mission-sync-lxmf.asyncapi.yaml`.

### Reply lifecycle

Mission command replies are emitted as direct LXMF messages with body text
`mission-sync`.

Reply sequencing:

- invalid payload or sender mismatch: one `rejected` reply only
- authorized command accepted for execution: one `accepted` reply, then one
  terminal `result` reply
- accepted command that fails during execution: one `accepted` reply, then one
  terminal `rejected` reply

`FIELD_RESULTS` payload shapes:

```json
{
  "command_id": "cmd-123",
  "status": "accepted",
  "accepted_at": "2026-03-13T12:00:01Z",
  "correlation_id": "ui-save-42",
  "by_identity": "<hub-identity>"
}
```

```json
{
  "command_id": "cmd-123",
  "status": "rejected",
  "reason_code": "unauthorized",
  "reason": "Capability 'mission.registry.log.write' is required",
  "correlation_id": "ui-save-42",
  "required_capabilities": ["mission.registry.log.write"]
}
```

```json
{
  "command_id": "cmd-123",
  "status": "result",
  "result": {
    "entry_uid": "log-1",
    "mission_uid": "mission-1",
    "content": "Operator note"
  },
  "correlation_id": "ui-save-42"
}
```

When present on the inbound LXMF message, `FIELD_THREAD` and `FIELD_GROUP` are
relayed onto mission replies by the runtime.

Encoding rules:

- `FIELD_RESULTS` payloads for mission commands are JSON-compatible objects,
  not MessagePack blobs.
- `FIELD_EVENT` payloads attached to mission command results are also
  JSON-compatible objects.
- `FIELD_CUSTOM_DATA` and `FIELD_CUSTOM_META` in the R3AKT mission profile are
  emitted as structured JSON-compatible objects, with
  `FIELD_CUSTOM_META.encoding = "json"`.

### Event envelope

Successful terminal mission replies may also carry `FIELD_EVENT`. The event
envelope uses this organization:

| Field | Type | Meaning |
| --- | --- | --- |
| `event_id` | string | Hub-generated unique event identifier. |
| `source.rns_identity` | string | The transport sender identity for the command. |
| `timestamp` | ISO-8601 datetime | Hub event creation time. |
| `event_type` | string | Operation outcome such as `mission.registry.log_entry.upserted`. |
| `topics` | string array | Copied from the inbound mission command envelope. |
| `payload` | object | Command-specific event payload. |

## LXMF organization for mission traffic

Mission southbound traffic is organized into three LXMF message classes.

### 1. Command ingress

- LXMF field: `FIELD_COMMANDS` (`0x09`)
- Payload class: mission command envelopes
- Optional context field: `FIELD_GROUP` (`0x0B`)
- Purpose: send a requested mission operation to the hub

### 2. Command outcomes

- LXMF field: `FIELD_RESULTS` (`0x0A`)
- Payload class: `accepted`, `rejected`, or `result`
- Optional companion field: `FIELD_EVENT` (`0x0D`) on successful terminal
  replies
- Optional relayed context: `FIELD_THREAD` (`0x08`), `FIELD_GROUP` (`0x0B`)
- Purpose: acknowledge, reject, or complete a mission command

### 3. Mission event and delta fan-out

- Primary LXMF field: `FIELD_EVENT` (`0x0D`)
- Optional group scope: `FIELD_GROUP` (`0x0B`)
- Markdown fallback: `FIELD_RENDERER` (`0x0F`) set to
  `RENDERER_MARKDOWN` (`0x02`) for generic LXMF clients
- R3AKT custom profile:
  - `FIELD_CUSTOM_TYPE` (`0xFB`) = `r3akt.mission.change.v1`
  - `FIELD_CUSTOM_DATA` (`0xFC`) = mission event payload object
  - `FIELD_CUSTOM_META` (`0xFD`) = mission event metadata

The runtime augments mission replies and mission-related fan-out with custom
R3AKT fields when a mission UID can be resolved from `FIELD_EVENT` /
`FIELD_RESULTS`.

Custom mission field organization:

```json
{
  "FIELD_CUSTOM_TYPE": "r3akt.mission.change.v1",
  "FIELD_CUSTOM_DATA": {
    "mission_uid": "mission-1",
    "event": {
      "event_type": "mission.registry.log_entry.upserted",
      "payload": {
        "entry_uid": "log-1"
      }
    }
  },
  "FIELD_CUSTOM_META": {
    "version": "1.0",
    "event_type": "mission.registry.log_entry.upserted",
    "mission_uid": "mission-1",
    "encoding": "json",
    "source": "rch"
  }
}
```

Operationally, this means:

- R3AKT-aware clients can consume structured mission delta fields directly.
- Generic markdown-oriented LXMF clients can still consume the human-readable
  body plus `FIELD_EVENT`.
- `FIELD_GROUP` remains routing/context metadata, not the command payload
  itself.

## Practical examples

### Example: `mission.registry.log_entry.upsert`

Inbound:

```json
{
  "FIELD_COMMANDS": [
    {
      "command_id": "cmd-log-001",
      "source": {
        "rns_identity": "<sender-identity>"
      },
      "timestamp": "2026-03-13T16:20:00Z",
      "command_type": "mission.registry.log_entry.upsert",
      "args": {
        "mission_uid": "mission-1",
        "callsign": "EAGLE-1",
        "client_time": "2026-03-13T16:19:42Z",
        "keywords": ["ops", "sitrep"],
        "content": "Reached checkpoint bravo. No contact."
      },
      "correlation_id": "ui-log-save-001",
      "topics": ["mission-1", "audit"]
    }
  ]
}
```

Outbound:

- body: `mission-sync`
- first `FIELD_RESULTS`: accepted envelope
- second `FIELD_RESULTS`: terminal `result` envelope with the saved log entry
- `FIELD_EVENT`: `mission.registry.log_entry.upserted`
- `FIELD_CUSTOM_TYPE`: `r3akt.mission.change.v1` when the mission UID is known
- `FIELD_CUSTOM_DATA` / `FIELD_CUSTOM_META`: JSON-compatible mission event
  objects, not MessagePack
- `FIELD_THREAD` / `FIELD_GROUP`: echoed if they were on the request

Example successful terminal reply fields:

```json
{
  "FIELD_RESULTS": {
    "command_id": "cmd-log-001",
    "status": "result",
    "result": {
      "entry_uid": "log-1",
      "mission_uid": "mission-1",
      "callsign": "EAGLE-1",
      "client_time": "2026-03-13T16:19:42Z",
      "server_time": "2026-03-13T16:20:01Z",
      "keywords": ["ops", "sitrep"],
      "content": "Reached checkpoint bravo. No contact."
    },
    "correlation_id": "ui-log-save-001"
  },
  "FIELD_EVENT": {
    "event_id": "<generated>",
    "source": {
      "rns_identity": "<sender-identity>"
    },
    "timestamp": "2026-03-13T16:20:01Z",
    "event_type": "mission.registry.log_entry.upserted",
    "topics": ["mission-1", "audit"],
    "payload": {
      "entry_uid": "log-1",
      "mission_uid": "mission-1",
      "callsign": "EAGLE-1",
      "content": "Reached checkpoint bravo. No contact."
    }
  },
  "FIELD_CUSTOM_TYPE": "r3akt.mission.change.v1",
  "FIELD_CUSTOM_DATA": {
    "mission_uid": "mission-1",
    "event": {
      "event_type": "mission.registry.log_entry.upserted",
      "payload": {
        "entry_uid": "log-1"
      }
    }
  },
  "FIELD_CUSTOM_META": {
    "version": "1.0",
    "event_type": "mission.registry.log_entry.upserted",
    "mission_uid": "mission-1",
    "encoding": "json",
    "source": "rch"
  }
}
```

### Example: `ListTopic`

Inbound:

```json
{
  "FIELD_COMMANDS": [
    {
      "Command": "ListTopic"
    }
  ]
}
```

Outbound:

- body: topic list text
- `FIELD_RESULTS`: same content, parsed/truncated as needed
- `FIELD_EVENT`: `rch.command.result`
- `FIELD_THREAD` / `FIELD_GROUP`: echoed if they were on the request

### Example: `TelemetryRequest`

Inbound:

```json
{
  "FIELD_COMMANDS": [
    {
      "1": 1700000000,
      "TopicID": "weather"
    }
  ]
}
```

Outbound:

- body: empty
- `FIELD_TELEMETRY_STREAM`: telemetry entries
- `FIELD_EVENT`: `rch.telemetry.response`
- `FIELD_THREAD` / `FIELD_GROUP`: echoed if they were on the request

### Example: `RetrieveImage`

Inbound:

```json
{
  "FIELD_COMMANDS": [
    {
      "Command": "RetrieveImage",
      "FileID": 7
    }
  ]
}
```

Outbound:

- body: image retrieval status text
- `FIELD_RESULTS`: status text or parsed payload
- `FIELD_IMAGE`: image payload
- `FIELD_FILE_ATTACHMENTS`: same payload for compatibility
- `FIELD_EVENT`: `rch.command.result`

## Current rule of thumb

If you need to integrate with the hub southbound interface, use this mental
model:

- send commands in `FIELD_COMMANDS`
- expect ordinary command replies in `FIELD_RESULTS`
- expect telemetry in `FIELD_TELEMETRY_STREAM`
- expect attachments in `FIELD_FILE_ATTACHMENTS` / `FIELD_IMAGE`
- do not expect the hub to answer with `FIELD_COMMANDS`
