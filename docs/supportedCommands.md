# Supported LXMF Southbound Commands

This document lists every command currently accepted by RCH over the LXMF
southbound interface.

Use this document for:

- legacy/plugin LXMF commands handled by `CommandManager`
- telemetry requests handled through the southbound LXMF path
- R3AKT mission-sync `command_type` envelopes carried in `FIELD_COMMANDS`
- R3AKT checklist `command_type` envelopes carried in `FIELD_COMMANDS`

Do not use this document as a list of every northbound HTTP route. Some
`/api/r3akt/*` routes are HTTP-only today and do not have an LXMF southbound
equivalent. Those are called out near the end.

## Transport formats

### Legacy / plugin commands

Legacy/plugin commands are sent in `FIELD_COMMANDS` (`0x09`) as objects that
use `Command`:

```json
[
  {
    "Command": "ListTopic"
  }
]
```

Telemetry requests use the numeric Sideband-compatible form:

```json
[
  {
    "1": 1700000000,
    "TopicID": "<optional topic id>"
  }
]
```

If a client cannot set `FIELD_COMMANDS`, RCH also accepts the escaped-body
fallback described in [southbound.md](southbound.md).

Topic-routing rules shared with the runtime and northbound API:

- `TopicID` values are normalized to one canonical string form before routing,
  persistence, and subscriber lookup.
- A send must choose exactly one routing mode: `topic_id` fan-out,
  `destination` unicast, or broadcast with neither.
- `topic_id` and `destination` together are rejected.
- Hub-originated outbound chat/messages attach an `RTHDelivery` envelope with
  `Message-ID`, content-type/schema, sender, TTL, priority, and UTC timestamps.

### Mission-sync and checklist envelopes

R3AKT mission and checklist commands use the mission envelope schema in
`FIELD_COMMANDS`. The command is selected by `command_type`.

```json
[
  {
    "command_id": "cmd-123",
    "source": {
      "rns_identity": "<sender identity>"
    },
    "timestamp": "2026-03-06T12:00:00Z",
    "command_type": "mission.registry.mission.list",
    "args": {},
    "correlation_id": "optional-correlation-id",
    "topics": []
  }
]
```

Checklist commands use the same envelope shape; only `command_type` changes:

```json
[
  {
    "command_id": "cmd-456",
    "source": {
      "rns_identity": "<sender identity>"
    },
    "timestamp": "2026-03-06T12:00:00Z",
    "command_type": "checklist.template.list",
    "args": {}
  }
]
```

## Legacy / plugin commands

### Public commands

| Command | Key fields | Description |
| --- | --- | --- |
| `Help` | none | Return a Markdown list of available legacy/plugin commands. |
| `Examples` | none | Return Markdown examples for legacy/plugin command payloads. |
| `join` | none | Register the sender LXMF destination with the hub connection list. |
| `leave` | none | Remove the sender LXMF destination from the hub connection list. |
| `ListTopic` | none | List registered topics. |
| `RetrieveTopic` | `TopicID` | Return one topic by ID. |
| `SubscribeTopic` | `TopicID`; optional `RejectTests`, `Metadata` | Subscribe the sender to a topic. |
| `ListFiles` | none | List stored file attachments. |
| `ListImages` | none | List stored image attachments. |
| `RetrieveFile` | `FileID` | Return a stored file via `FIELD_FILE_ATTACHMENTS`. |
| `RetrieveImage` | `FileID` | Return a stored image via `FIELD_IMAGE` and `FIELD_FILE_ATTACHMENTS`. |
| `getAppInfo` | none | Return app metadata such as name, version, and Reticulum destination. |
| `TelemetryRequest` (`1`) | `1` unix timestamp; optional `TopicID` | Return telemetry snapshots via `FIELD_TELEMETRY_STREAM`. |

### Protected / admin commands

| Command | Key fields | Description |
| --- | --- | --- |
| `GetStatus` | none | Return hub status, counts, uptime, and telemetry summary. |
| `ListEvents` | none | Return recent event log entries. |
| `ListClients` | none | List joined LXMF clients. |
| `ListIdentities` | none | List identity moderation state. |
| `BanIdentity` | `Identity` | Ban an identity. |
| `UnbanIdentity` | `Identity` | Remove ban or blackhole state from an identity. |
| `BlackholeIdentity` | `Identity` | Blackhole an identity. |
| `CreateTopic` | `TopicName`, `TopicPath` | Create a topic. |
| `PatchTopic` | `TopicID`; optional patch fields | Update a topic. |
| `DeleteTopic` | `TopicID` | Delete a topic. |
| `AssociateTopicID` | `TopicID` | Associate inbound attachments on the same LXMF message with a topic. |
| `ListSubscriber` | none | List subscriber entries. |
| `CreateSubscriber` | `TopicID`; optional `Destination` | Create a subscriber record. If `Destination` is omitted, the sender is used. |
| `AddSubscriber` | `TopicID`; optional `Destination` | Alias of `CreateSubscriber`. |
| `RetrieveSubscriber` | `SubscriberID` | Return one subscriber by ID. |
| `DeleteSubscriber` | `SubscriberID` | Delete a subscriber. |
| `RemoveSubscriber` | `SubscriberID` | Alias of `DeleteSubscriber`. |
| `PatchSubscriber` | `SubscriberID`; optional patch fields | Update subscriber metadata. |
| `GetConfig` | none | Return the current `config.ini` text. |
| `ValidateConfig` | `ConfigText` | Validate `config.ini` text without applying it. |
| `ApplyConfig` | `ConfigText` | Apply new `config.ini` text. |
| `RollbackConfig` | optional `BackupPath` | Roll back `config.ini` using the latest or specified backup. |
| `FlushTelemetry` | none | Delete stored telemetry snapshots. |
| `ReloadConfig` | none | Reload config from disk. |
| `DumpRouting` | none | Return connected destination hashes. |

## R3AKT mission-sync LXMF commands

Mission-sync commands are routed when `command_type` is present and does not
start with `checklist.`.

The `Required capability` column reflects the current capability gate enforced
by `mission_sync/capabilities.py`.

### Mission control and topic bridge

| `command_type` | Required capability | Key args | Description |
| --- | --- | --- | --- |
| `mission.join` | `mission.join` | optional `identity` | Join the mission transport identity. Defaults to the LXMF sender identity. |
| `mission.leave` | `mission.leave` | optional `identity` | Leave the mission transport identity. Defaults to the LXMF sender identity. |
| `mission.events.list` | `mission.audit.read` | none | Return recent hub event log entries. |
| `mission.message.send` | `mission.message.send` | `content`; optional `topic_id`, `destination` | Send a message via the hub from the mission-sync path. Provide at most one of `topic_id` or `destination`. |
| `topic.list` | `topic.read` | none | List topics through the mission-sync API. |
| `topic.create` | `topic.create` | topic payload | Create a topic through the mission-sync API. |
| `topic.patch` | `topic.write` | `topic_id`; optional patch fields | Patch a topic through the mission-sync API. |
| `topic.delete` | `topic.delete` | `topic_id` | Delete a topic through the mission-sync API. |
| `topic.subscribe` | `topic.subscribe` | `topic_id`; optional `destination`, `reject_tests`, `metadata` | Subscribe a destination to a topic through the mission-sync API. |

### Marker and zone content

| `command_type` | Required capability | Key args | Description |
| --- | --- | --- | --- |
| `mission.marker.list` | `mission.content.read` | none | List mission markers. |
| `mission.marker.create` | `mission.content.write` | `lat`, `lon`; optional `name`, `marker_type`, `symbol`, `category`, `notes`, `ttl_seconds` | Create a mission marker. |
| `mission.marker.position.patch` | `mission.content.write` | `object_destination_hash`, `lat`, `lon` | Update a mission marker position. |
| `mission.zone.list` | `mission.zone.read` | none | List zones. |
| `mission.zone.create` | `mission.zone.write` | `points`; optional `name` | Create a zone. |
| `mission.zone.patch` | `mission.zone.write` | `zone_id`; optional `name`, `points` | Update a zone. |
| `mission.zone.delete` | `mission.zone.delete` | `zone_id` | Delete a zone. |

### Mission registry and audit

| `command_type` | Required capability | Key args | Description |
| --- | --- | --- | --- |
| `mission.registry.mission.upsert` | `mission.registry.mission.write` | mission payload | Create or update a mission aggregate. |
| `mission.registry.mission.get` | `mission.registry.mission.read` | `mission_uid`; optional `expand`, `expand_topic` | Return one mission. |
| `mission.registry.mission.list` | `mission.registry.mission.read` | optional `expand`, `expand_topic` | List missions. |
| `mission.registry.mission.patch` | `mission.registry.mission.write` | `mission_uid`; optional `patch` or inline fields | Patch a mission. |
| `mission.registry.mission.delete` | `mission.registry.mission.write` | `mission_uid` | Delete a mission. |
| `mission.registry.mission.parent.set` | `mission.registry.mission.write` | `mission_uid`; optional `parent_uid` | Set or clear a mission parent relationship. |
| `mission.registry.mission.rde.set` | `mission.registry.mission.write` | `mission_uid`, `role` | Upsert the mission RDE role assignment. |
| `mission.registry.mission_change.upsert` | `mission.registry.log.write` | mission-change payload | Create or update a mission change record. |
| `mission.registry.mission_change.list` | `mission.registry.log.read` | optional `mission_uid` | List mission changes. |
| `mission.registry.log_entry.upsert` | `mission.registry.log.write` | log-entry payload | Create or update a log entry. |
| `mission.registry.log_entry.list` | `mission.registry.log.read` | optional `mission_uid`, `marker_ref` | List log entries. |

### Emergency Action Message status

| `command_type` | Required capability | Key args | Description |
| --- | --- | --- | --- |
| `mission.registry.eam.list` | `mission.registry.status.read` | optional `team_uid`, `overall_status` | List current EAM snapshots in the southbound LXMF shape. |
| `mission.registry.eam.upsert` | `mission.registry.status.write` | `callsign`, `team_member_uid`, `team_uid`; optional `reported_by`, `reported_at`, six `*_status` fields, `notes`, `confidence`, `ttl_seconds`, `source` | Create or update a member-scoped EAM snapshot. |
| `mission.registry.eam.get` | `mission.registry.status.read` | `callsign` | Retrieve the current EAM snapshot for a callsign. |
| `mission.registry.eam.latest` | `mission.registry.status.read` | `team_member_uid` | Retrieve the latest non-expired EAM snapshot for a team member. |
| `mission.registry.eam.delete` | `mission.registry.status.write` | `callsign` | Delete the current EAM snapshot for a callsign. |
| `mission.registry.eam.team.summary` | `mission.registry.status.read` | `team_uid` | Compute the current team summary using worst-of semantics across member snapshots. |

### Teams and memberships

| `command_type` | Required capability | Key args | Description |
| --- | --- | --- | --- |
| `mission.registry.team.upsert` | `mission.registry.team.write` | team payload | Create or update a team. |
| `mission.registry.team.get` | `mission.registry.team.read` | `team_uid` | Return one team. |
| `mission.registry.team.list` | `mission.registry.team.read` | optional `mission_uid` | List teams. |
| `mission.registry.team.delete` | `mission.registry.team.write` | `team_uid` | Delete a team. |
| `mission.registry.team.mission.link` | `mission.registry.team.write` | `team_uid`, `mission_uid` | Link a team to a mission. |
| `mission.registry.team.mission.unlink` | `mission.registry.team.write` | `team_uid`, `mission_uid` | Unlink a team from a mission. |
| `mission.registry.mission.zone.link` | `mission.zone.write` | `mission_uid`, `zone_id` | Link a mission to a zone. |
| `mission.registry.mission.zone.unlink` | `mission.zone.write` | `mission_uid`, `zone_id` | Unlink a mission from a zone. |
| `mission.registry.team_member.upsert` | `mission.registry.team.write` | team-member payload | Create or update a team member. |
| `mission.registry.team_member.get` | `mission.registry.team.read` | `team_member_uid` | Return one team member. |
| `mission.registry.team_member.list` | `mission.registry.team.read` | optional `team_uid` | List team members. |
| `mission.registry.team_member.delete` | `mission.registry.team.write` | `team_member_uid` | Delete a team member. |
| `mission.registry.team_member.client.link` | `mission.registry.team.write` | `team_member_uid`, `client_identity` | Link a team member to a client identity. |
| `mission.registry.team_member.client.unlink` | `mission.registry.team.write` | `team_member_uid`, `client_identity` | Unlink a team member from a client identity. |

### Assets, skills, and assignments

| `command_type` | Required capability | Key args | Description |
| --- | --- | --- | --- |
| `mission.registry.asset.upsert` | `mission.registry.asset.write` | asset payload | Create or update an asset. |
| `mission.registry.asset.get` | `mission.registry.asset.read` | `asset_uid` | Return one asset. |
| `mission.registry.asset.list` | `mission.registry.asset.read` | optional `team_member_uid` | List assets. |
| `mission.registry.asset.delete` | `mission.registry.asset.write` | `asset_uid` | Delete an asset. |
| `mission.registry.skill.upsert` | `mission.registry.skill.write` | skill payload | Create or update a skill. |
| `mission.registry.skill.list` | `mission.registry.skill.read` | none | List skills. |
| `mission.registry.team_member_skill.upsert` | `mission.registry.skill.write` | team-member-skill payload | Create or update a team-member skill record. |
| `mission.registry.team_member_skill.list` | `mission.registry.skill.read` | optional `team_member_rns_identity` | List team-member skill records. |
| `mission.registry.task_skill_requirement.upsert` | `mission.registry.skill.write` | task-skill-requirement payload | Create or update a task skill requirement. |
| `mission.registry.task_skill_requirement.list` | `mission.registry.skill.read` | optional `task_uid` | List task skill requirements. |
| `mission.registry.assignment.upsert` | `mission.registry.assignment.write` | assignment payload | Create or update an assignment. |
| `mission.registry.assignment.list` | `mission.registry.assignment.read` | optional `mission_uid`, `task_uid` | List assignments. |
| `mission.registry.assignment.asset.set` | `mission.registry.assignment.write` | `assignment_uid`, `assets[]` | Replace the assignment asset set. |
| `mission.registry.assignment.asset.link` | `mission.registry.assignment.write` | `assignment_uid`, `asset_uid` | Link one asset to an assignment. |
| `mission.registry.assignment.asset.unlink` | `mission.registry.assignment.write` | `assignment_uid`, `asset_uid` | Unlink one asset from an assignment. |

## R3AKT checklist LXMF commands

Checklist commands use the same envelope structure as mission-sync commands, but
their `command_type` starts with `checklist.`.

The `Required capability` column reflects the current capability gate enforced
by `checklist_sync/capabilities.py`.

### Template commands

| `command_type` | Required capability | Key args | Description |
| --- | --- | --- | --- |
| `checklist.template.list` | `checklist.template.read` | optional `search`, `sort_by` | List checklist templates. |
| `checklist.template.get` | `checklist.template.read` | `template_uid` | Return one checklist template. |
| `checklist.template.create` | `checklist.template.write` | `template` | Create a checklist template. |
| `checklist.template.update` | `checklist.template.write` | `template_uid`, `patch` | Update a checklist template. |
| `checklist.template.clone` | `checklist.template.write` | `source_template_uid`, `template_name`; optional `description` | Clone a checklist template. |
| `checklist.template.delete` | `checklist.template.delete` | `template_uid` | Delete a checklist template. |

### Checklist lifecycle commands

| `command_type` | Required capability | Key args | Description |
| --- | --- | --- | --- |
| `checklist.list.active` | `checklist.read` | optional `search`, `sort_by` | List active checklists. |
| `checklist.create.online` | `checklist.write` | checklist payload | Create an online checklist. |
| `checklist.create.offline` | `checklist.write` | checklist payload | Create an offline checklist. |
| `checklist.update` | `checklist.write` | `checklist_uid`, `patch` | Update a checklist. |
| `checklist.delete` | `checklist.write` | `checklist_uid` | Delete a checklist. |
| `checklist.import.csv` | `checklist.write` | import payload | Import a checklist from CSV-shaped payload data. |
| `checklist.join` | `checklist.join` | `checklist_uid` | Join a checklist as the sending identity. |
| `checklist.get` | `checklist.read` | `checklist_uid` | Return one checklist. |
| `checklist.upload` | `checklist.upload` | `checklist_uid` | Upload a checklist state snapshot. |
| `checklist.feed.publish` | `checklist.feed.publish` | `checklist_uid`, `mission_feed_uid` | Publish a checklist feed update. |

### Shared Excheck/task workflow

RCH Exchecks are shared by default through the checklist command family:

- create the shared run with `checklist.create.online`
- add rows with `checklist.task.row.add`
- update row cells with `checklist.task.cell.set`
- change completion state with `checklist.task.status.set`
- publish to a mission feed only when needed with `checklist.feed.publish`

Use `checklist.create.offline` only for explicit local drafts that should stay
`OFFLINE` / `LOCAL_ONLY` until they are uploaded.

### Checklist task editing commands

| `command_type` | Required capability | Key args | Description |
| --- | --- | --- | --- |
| `checklist.task.status.set` | `checklist.write` | `checklist_uid`, `task_uid`, status payload | Update task status. |
| `checklist.task.row.add` | `checklist.write` | `checklist_uid`, row payload | Add a checklist task row. |
| `checklist.task.row.delete` | `checklist.write` | `checklist_uid`, `task_uid` | Delete a checklist task row. |
| `checklist.task.row.style.set` | `checklist.write` | `checklist_uid`, `task_uid`, style payload | Update row styling. |
| `checklist.task.cell.set` | `checklist.write` | `checklist_uid`, `task_uid`, `column_uid`, cell payload | Update a single checklist task cell. |

## R3AKT northbound routes that are not LXMF commands

The following northbound R3AKT routes exist in HTTP, but do not currently have
their own southbound LXMF `command_type` in the mission/checklist routers:

- capability management: `/api/r3akt/capabilities/{identity}` and
  `/api/r3akt/capabilities/{identity}/{capability}`
- domain event and snapshot listing: `/api/r3akt/events` and
  `/api/r3akt/snapshots`
- mission-zone association listing:
  `/api/r3akt/missions/{mission_uid}/zones`
- mission-marker association listing and mutation:
  `/api/r3akt/missions/{mission_uid}/markers` and
  `/api/r3akt/missions/{mission_uid}/markers/{marker_id}`
- mission RDE read:
  `/api/r3akt/missions/{mission_uid}/rde`
- team mission association listing:
  `/api/r3akt/teams/{team_uid}/missions`
- team-member client association listing:
  `/api/r3akt/team-members/{team_member_uid}/clients`

Those routes may still overlap semantically with southbound commands, but they
are not separate LXMF commands unless listed above.

## Notes

- `FIELD_COMMANDS` (`0x09`) is ingress-only. RCH does not wrap replies in a
  second `FIELD_COMMANDS` envelope.
- Legacy/plugin command replies include `FIELD_RESULTS` (`0x0A`) in addition to
  human-readable message text.
- Mission-sync and checklist replies also use `FIELD_RESULTS` plus
  `FIELD_EVENT` when available.
- Telemetry replies use `FIELD_TELEMETRY_STREAM` (`0x03`) instead of
  `FIELD_RESULTS` as the primary payload field, and successful telemetry
  replies intentionally leave the text body empty.
- `TopicID` values accepted by southbound commands are canonicalized before the
  hub routes, persists, or subscribes against them.
- When relaying messages, RCH forwards `FIELD_THREAD` (`0x08`) and
  `FIELD_GROUP` (`0x0B`) so clients can keep conversation/group context.
- Command and relay responses include `FIELD_EVENT` (`0x0D`) with structured
  event metadata.
- When `RTHDelivery` is present on inbound traffic, the hub validates required
  fields, accepted content types, TTL, schema version, and clock skew.
- Outbound delivery state uses `Message-ID` plus persisted `delivery_metadata`
  so retries, acks, propagation fallback, and drop reasons stay visible to the
  UI/API.
- Help and Examples responses include `FIELD_RENDERER` (`0x0F`) set to
  `RENDERER_MARKDOWN` (`0x02`).
- Command names are normalized across common casing variants.
- `POST /RCH` and `PUT /RCH` are northbound HTTP endpoints, not LXMF commands.
  Their LXMF southbound equivalents are legacy `join` and `leave`, or the
  mission-sync `mission.join` and `mission.leave` command types.
- For the full field-level southbound contract, see [southbound.md](southbound.md).
