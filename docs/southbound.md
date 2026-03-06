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

## Practical examples

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
