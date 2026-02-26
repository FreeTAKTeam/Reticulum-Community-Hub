# Plan: Human-Readable, Low-Bandwidth Mission Delta Markdown for Non-R3AKT Clients

Replace the current count-only fallback body with operation-specific Markdown summaries that are understandable to humans, avoid raw IDs in message text, and stay within a hard `<=700` byte body budget for constrained links (including LoRa). Keep R3AKT-capable custom-field fanout unchanged.

## Scope

- In: Non-R3AKT fallback body formatting for existing auto-emitted mission deltas (`logs`, `assets`, `tasks` + task ops), name resolution from internal data, byte-budget enforcement, and docs/tests updates.
- Out: New mission delta types, R3AKT custom-field schema changes, capability detection changes, and any change to recipient selection/dedupe logic.

## Public APIs / Interfaces / Types

- External HTTP/LXMF API changes: none.
- Contract-doc update in `docs/architecture/asyncapi/r3akt-mission-sync-lxmf.asyncapi.yaml`: add normative `generic_lxmf` Markdown profile details.
- Contract-mapping update in `docs/architecture/contract-mapping.md`: document non-R3AKT message rules.
- Internal formatter interface (new module): `render_mission_delta_markdown(mission_uid, mission_change, delta, resolver, max_bytes=700) -> str`.
- Non-R3AKT fallback transport requirement: set `FIELD_RENDERER` (`0x0F`) to `RENDERER_MARKDOWN` (`0x02`) on outbound LXMF fields so compatible clients render markdown correctly.

## Markdown Message Catalog (Decision Complete)

### Global format rules

1. Always start with:

```md
### Mission {mission_name}
```

2. Body style: compact bullet lines only.
3. No raw identifiers in final body text.
4. Resolve IDs internally to human labels before rendering.
5. If a human label cannot be resolved, use generic target wording (no ID leak).
6. Hard cap: UTF-8 encoded body must be `<=700` bytes.
7. Trim order when over budget:

```md
1) Drop optional context lines (keywords/location/notes/time)
2) Shorten long text fields (content/value/name)
3) Collapse lists to counts (e.g., "3 assets")
4) Fallback to one-line generic bullet summary
```

8. Escape/normalize user text for markdown safety (flatten newlines, trim whitespace).

### Shared header block

```md
### Mission {mission_name}
- Update: {operation_summary}
```

### Element templates

1. `logs[].op = upsert`

```md
### Mission {mission_name}
- Update: Log added
- Detail: "{client_time}, {content_excerpt}"
- Tags: {keyword_list}   # optional
```

2. `assets[].op = upsert`

```md
### Mission {mission_name}
- Update: Asset updated
- Detail: {asset_name} ({asset_type}, {status})
- Assigned: {team_member_name}   # optional
- Location: {location_excerpt}   # optional
```

3. `assets[].op = delete`

```md
### Mission {mission_name}
- Update: Asset removed
- Detail: {asset_name} ({asset_type})
```

4. `tasks[].op = row_added`

```md
### Mission {mission_name}
- Update: Checklist task added
- Detail: {task_label}
- Due: {due_summary}   # optional
```

5. `tasks[].op = row_deleted`

```md
### Mission {mission_name}
- Update: Checklist task removed
- Detail: {task_label}
```

6. `tasks[].op = row_style_set`

```md
### Mission {mission_name}
- Update: Checklist task formatting changed
- Detail: {task_label}
- Style: {style_summary}
```

7. `tasks[].op = cell_set`

```md
### Mission {mission_name}
- Update: Checklist task updated
- Detail: {task_label}
- Field: {column_name} = {value_excerpt}
```

8. `tasks[].op = status_set`

```md
### Mission {mission_name}
- Update: task status {previous_status} -> {current_status}
- Detail: {task_label}
- Completed by: {completed_by_team_member_name}   # required when {current_status} is COMPLETE or COMPLETE_LATE
```

9. `tasks[].op = assignment_upsert`

```md
### Mission {mission_name}
- Update: Assignment updated
- Detail: {task_label} -> {assignee_name}
- Status: {status}
- Assets: {asset_name_list_or_count}   # optional
```

10. `tasks[].op = assignment_assets_set`

```md
### Mission {mission_name}
- Update: Assignment asset set replaced
- Detail: {task_label}
- Assets: {asset_name_list_or_count}
```

11. `tasks[].op = assignment_asset_linked`

```md
### Mission {mission_name}
- Update: Assignment asset linked
- Detail: {task_label}
- Asset: {asset_name}
```

12. `tasks[].op = assignment_asset_unlinked`

```md
### Mission {mission_name}
- Update: Assignment asset removed
- Detail: {task_label}
- Asset: {asset_name}
```

13. Unknown or unresolved operation fallback

```md
### Mission {mission_name}
- Update: Mission content updated
- Detail: Additional details unavailable on this link
```

## Name-Resolution Rules (No ID Output)

1. Mission name: resolve from `MissionDomainService.get_mission(mission_uid)`.
2. Team member names: resolve identity-to-display-name map from mission-linked members.
3. Task label resolution priority:

```md
1) Checklist task "legacy_value" if present
2) First SHORT_STRING cell value if present
3) "Checklist task" generic label
```

4. Column label: resolve `column_uid` to checklist column name.
5. Asset label: use delta `name`; if absent, resolve asset name via domain lookup; else generic "asset".
6. Assignment label: derive from related task label + assignee display name.
7. For checklist `status_set` updates where `current_status` is COMPLETE or COMPLETE_LATE, resolve and include `completed_by_team_member_name` from team-member identity lookup; if not resolvable, emit `Unknown team member` (no ID output).
8. Never render `mission_uid`, `task_uid`, `asset_uid`, `assignment_uid`, or `checklist_uid` in fallback body.

## Action items

- [ ] Add a dedicated formatter module at `reticulum_telemetry_hub/reticulum_server/mission_delta_markdown.py` with operation dispatch, text normalization, and byte-budget enforcement.
- [ ] Add a resolver helper in the same module for mission/member/task/column/asset human-label enrichment with per-message in-memory caching.
- [ ] Refactor `reticulum_telemetry_hub/reticulum_server/__main__.py` to replace `_format_generic_mission_delta_markdown` with the new formatter call while preserving existing R3AKT custom-field flow.
- [ ] For non-R3AKT mission-delta fanout, set `FIELD_RENDERER` to `RENDERER_MARKDOWN` in outbound LXMF fields alongside `FIELD_EVENT`.
- [ ] Switch fallback heading to `### Mission {mission_name}` and update generic LXMF integration assertions accordingly (no backward-compatibility guarantee for legacy regular LXMF body format).
- [ ] Add unit tests for each supported op template and fallback behavior in a new test module (for example `tests/test_mission_delta_markdown.py`).
- [ ] Extend `tests/test_reticulum_server_daemon.py` to assert non-R3AKT messages are human-readable, contain no IDs, and remain within the 700-byte cap.
- [ ] Add regression tests for unresolved lookups to verify generic-name fallback without leaking identifiers.
- [ ] Update AsyncAPI generic profile docs in `docs/architecture/asyncapi/r3akt-mission-sync-lxmf.asyncapi.yaml` with markdown-profile semantics and op coverage.
- [ ] Update implementation mapping docs in `docs/architecture/contract-mapping.md` to reflect no-ID human-readable fallback rules.

## Test cases and scenarios

1. `log upsert`: message includes mission name + log content excerpt; no IDs; `<=700` bytes.
2. `asset upsert/delete`: message includes asset human name and action verb; no IDs.
3. `task status_set`: message includes resolved task label and status transition; when marked COMPLETE/COMPLETE_LATE it must include completer team member name.
4. `task cell_set`: resolves column label and value excerpt; no `column_uid` in output.
5. `assignment_* ops`: resolves task label and asset/member names; falls back to generic words when unresolved.
6. Long values/notes/content: formatter trims to stay within `<=700` bytes and remains readable markdown.
7. Missing resolver data: emits generic target text and never leaks identifiers.
8. Integration: non-R3AKT recipients get markdown-only human body with `FIELD_RENDERER=RENDERER_MARKDOWN`; R3AKT recipients still receive custom fields; dedupe-by-change-uid remains unchanged.

## Assumptions and defaults

- Scope is limited to delta-backed mission updates (`logs/assets/tasks`), not all mission registry events.
- Hard fallback message limit is `<=700` bytes UTF-8.
- Style is compact bullet markdown.
- Body text must not include raw IDs.
- When names are missing, IDs may be used internally for lookup only; output remains human-readable with generic wording if lookup fails.
- R3AKT custom-field contract and semantics remain backward compatible; regular LXMF fallback body format is allowed to change.
- Existing delivery semantics, capability checks, and fanout recipient selection remain unchanged.