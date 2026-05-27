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

## Migration Note

The old verbose southbound command envelope is intentionally unsupported for REM
fanout. Receivers should not expect RCH to provide command IDs, correlations,
source metadata, timestamps, topics, `snapshot_json`, or a second encoded field
copy for REM southbound commands.
