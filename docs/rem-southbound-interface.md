# REM Southbound Interface

RCH emits REM-capable southbound messages as LXMF `FIELD_COMMANDS` (`0x09`)
payloads. Each command entry uses the reduced REM signature only:

```json
{
  "command_type": "checklist.task.status.set",
  "args": {
    "checklist_uid": "checklist-1",
    "task_uid": "task-1",
    "user_status": "COMPLETE"
  }
}
```

The southbound wire payload does not include legacy envelope metadata such as
`command_id`, `correlation_id`, `source`, `timestamp`, or `topics`. RCH also
does not emit an alternate encoded compatibility payload such as
`_lxmf_fields_msgpack_b64`. The Reticulum message body for REM commands is a
small placeholder (`cmd`), while the command data lives in `FIELD_COMMANDS`.
When the Rust server uses the LXMF-rs ZeroMQ SDK path, REM `auto` delivery is
submitted to the daemon as a propagated send so the reduced command payload is
queued through the selected propagation node instead of attempting a direct
link-first send.

## Common Shape

Every REM command is carried as:

```json
{
  "9": [
    {
      "command_type": "<operation>",
      "args": {}
    }
  ]
}
```

`args` contains only the operation data required by the receiving REM command.
Null values are omitted. IDs are sent as plain trimmed strings.

`checklist.upload` adds a native `snapshot` object beside `args`:

```json
{
  "command_type": "checklist.upload",
  "args": {
    "checklist_uid": "checklist-1",
    "mission_uid": "mission-1"
  },
  "snapshot": {}
}
```

## Command Inventory

Checklist commands:

- `checklist.create.online`
- `checklist.upload`
- `checklist.task.row.add`
- `checklist.task.row.delete`
- `checklist.task.row.style.set`
- `checklist.task.cell.set`
- `checklist.task.status.set`

Mission/log commands:

- `mission.registry.log_entry.upsert`

EAM commands:

- `mission.registry.eam.upsert`
- `mission.registry.eam.delete`

Telemetry and mission-content commands:

- `mission.registry.telemetry.upsert`
- `mission.registry.mission.marker.link`
- `mission.registry.mission.marker.unlink`
- `mission.registry.mission.zone.link`
- `mission.registry.mission.zone.unlink`

Some mission-content operations are ahead of current REM UI/runtime support.
They still use the same reduced signature so the southbound protocol has one
forward-compatible shape.

## Map Marker Replication

Point markers use one canonical `object_destination_hash` on every node and
the shared `r3akt-map-core` marker API representation as the replica payload.

REM to RCH: REM sends the standard mission command envelope in
`FIELD_COMMANDS` with `FIELD_GROUP` set to its active TEAM UID:

- `mission.marker.create` with `object_destination_hash` (32 hex characters,
  minted by REM), `marker_type`, `symbol`, `name`, `category`, `lat`, `lon`
  and optional `notes`. RCH keeps the supplied identifier; repeating the same
  create is an idempotent replay, and reusing the identifier for different
  fields is rejected. Without the field, RCH mints an identifier as before.
- `mission.marker.patch` (`object_destination_hash`, `name`),
  `mission.marker.position.patch` (`object_destination_hash`, `lat`, `lon`)
  and `mission.marker.delete` (`object_destination_hash`).

These commands require `mission.content.write`. Accepted team-scoped commands
are relayed to the TEAM's REM destinations with the resulting event.

RCH to REM: every replica arrives in `FIELD_EVENT` (`0x0D`) as

```json
{
  "13": {
    "event_type": "mission.marker.created",
    "payload": { "object_destination_hash": "...", "type": "fire", "symbol": "fire",
                 "name": "Ridge", "category": "incident", "notes": null,
                 "position": { "lat": 44.5, "lon": -1.25 }, "origin_rch": "...",
                 "created_at": "...", "updated_at": "...", "time": "...", "stale_at": "..." },
    "source": { "rns_identity": "<rch identity>" }
  }
}
```

`event_type` is `mission.marker.created`, `mission.marker.updated`,
`mission.marker.position.updated` or `mission.marker.deleted`. Relayed REM
commands use RCH's full event envelope (`event_id`, `timestamp`, `topics` in
addition); receivers read only `event_type` and `payload`. Marker changes
made through the RCH API to REM recipients also carry the legacy marker-as-telemetry
`mission.registry.telemetry.upsert` command for older REM builds; current REM
applies the event and ignores telemetry whose `object_type` is `marker`.

Receivers rebuild the marker with `r3akt_map_core::replica::from_api_value`
(the same validation as local creation) and keep the copy with the later
`updated_at` (`replica::supersedes`). Deletes remove the identifier; there
are no tombstones, so a delete can be undone by an older replica that
arrives later.

### Explicit delivery to Sideband, Columba and REM

In the Rust server's map, select a marker, choose **Send**, and enter the
recipient's LXMF delivery address. `POST /api/markers/{object_destination_hash}/share`
accepts `{"destination":"<32 hex characters>"}` and queues exactly that
destination through the existing durable outbound queue. API authentication,
outbound allowlists and identity bans still apply. A `202` response means
queued, not delivered; Messages tracks the subsequent delivery status.
Older backends without this endpoint cannot use this action; their other
marker operations are unchanged.

RCH API marker notifications, explicit shares and REM peer marker sends use
`r3akt_map_core::marker_wire`. Their upserts add standard numeric LXMF field
`0x03`, a plain list of `[object_hash_bytes, source_seconds,
packed_telemeter_bytes, [icon, foreground_bytes, background_bytes]]`.
Sideband is the reference implementation. This places the object separately
from the hub/sender's GPS position; field `0x02` is intentionally absent.
Name and notes are in the Information sensor; map labels are still chosen
by each receiving application. Sideband's telemetry trust setting must permit
the sender. RCH and REM still consume the full replica in field `0x0D`.

Marker creation and updates through the RCH API automatically reach current
non-REM roster clients using the same standard field `0x03` stream and field
`0x0D` replica as explicit sharing, without REM field `0x09` commands. The
message body is `Map marker: <name>`. Announced-only peers are not subscribed;
the existing runtime freshness gate, outbound allowlist, bans and blackholes
still apply. Paused and text-only clients are skipped. Marker notification
events report `skipped_reasons` counts and `skipped_recipients` with each
destination and reason for these policy exclusions.
Deletes and mission marker link/unlink commands remain REM-only, reported as
`standard_marker_delete_unsupported` and `rem_command_required` for non-REM
recipients. Delivery modes, retries and TEAM routing are unchanged. Explicit
sharing does not subscribe a contact to future updates.
Numeric collector command `1` still returns stored telemetry streams; this
action is a push and does not add map markers to collector history. Standard
streams have no marker-delete operation, so removal in Sideband/Columba is
not implied by R3AKT deletion. Pyxis marker support is out of scope.

## Migration Note

The old verbose southbound command envelope is intentionally unsupported for REM
fanout. Receivers should not expect RCH to provide command IDs, correlations,
source metadata, timestamps, topics, `snapshot_json`, or a second encoded field
copy for REM southbound commands.

## Team Peer Directory

REM clients operating in semi-autonomous mode request their authoritative peer
directory over LXMF with `rem.registry.team_peers.list`. The request uses the
normal mission-style command envelope in `FIELD_COMMANDS` (`0x09`):

```json
{
  "command_id": "hub-directory-123",
  "command_type": "rem.registry.team_peers.list",
  "timestamp": "2026-07-16T12:00:00Z",
  "source": { "rns_identity": "<requesting REM identity>" },
  "args": {}
}
```

RCH requires the caller to have REM announce capabilities and to be linked to a
TEAM member. Version 2 returns canonical shared TEAM records, caller
memberships, and durable REM-member destinations, including members whose last
validated announce is now offline. Non-REM, unverified, banned, blackholed, and
self entries are excluded. Primary TEAM member identities and explicitly linked
client identities are both eligible. The legacy `items` array remains recent
and active only so older REM clients retain their existing behavior.

The terminal `FIELD_RESULTS` (`0x0a`) result payload is:

```json
{
  "schema_version": 2,
  "scope": "shared_teams",
  "effective_connected_mode": false,
  "teams": [
    {
      "uid": "d6b6e188b910d6bdd24d04b7a7ec5444",
      "color": "YELLOW",
      "team_name": "Yellow"
    }
  ],
  "caller_memberships": [
    {
      "team_uid": "d6b6e188b910d6bdd24d04b7a7ec5444",
      "team_member_uid": "<caller TEAM member UID>"
    }
  ],
  "members": [
    {
      "team_uid": "d6b6e188b910d6bdd24d04b7a7ec5444",
      "team_member_uid": "<peer TEAM member UID>",
      "identity": "<TEAM member identity>",
      "destination_hash": "<last validated lxmf.delivery destination>",
      "display_name": "Field Phone",
      "announce_capabilities": ["r3akt", "emergencymessages", "telemetry"],
      "client_type": "rem",
      "registered_mode": "semi_autonomous",
      "last_seen": "2026-07-16T12:00:00Z",
      "status": "offline"
    }
  ],
  "items": [
    {
      "identity": "<TEAM member identity>",
      "destination_hash": "<lxmf.delivery destination>",
      "display_name": "Field Phone",
      "announce_capabilities": ["r3akt", "emergencymessages", "telemetry"],
      "client_type": "rem",
      "registered_mode": "semi_autonomous",
      "last_seen": "2026-07-16T12:00:00Z",
      "status": "active"
    }
  ]
}
```

REM team-scoped traffic carries the canonical TEAM UID in LXMF `FIELD_GROUP`
(`0x0B`). RCH rejects unknown TEAM UIDs and callers that do not belong to the
requested TEAM. In Connected mode, RCH fanout is restricted to the validated
TEAM's durable REM destinations. Commands without `FIELD_GROUP` remain accepted
for compatibility with older REM clients.

`rem.registry.peers.list` remains available as the legacy unscoped REM registry
command, and `GET /api/rem/peers` remains the operator-facing HTTP registry.
