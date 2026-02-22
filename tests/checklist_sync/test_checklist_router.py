from __future__ import annotations

import base64
from datetime import datetime
from datetime import timezone

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.checklist_sync.capabilities import CHECKLIST_COMMAND_CAPABILITIES
from reticulum_telemetry_hub.checklist_sync.router import ChecklistSyncRouter
from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from tests.test_rth_api import make_config_manager


FIELD_RESULTS = 10
FIELD_GROUP = 11
FIELD_EVENT = 13


def _router(tmp_path, *, include_event_log: bool = False):
    cfg = make_config_manager(tmp_path)
    api = ReticulumTelemetryHubAPI(config_manager=cfg)
    domain = MissionDomainService(cfg.config.hub_database_path)
    event_log = EventLog() if include_event_log else None
    router = ChecklistSyncRouter(
        api=api,
        domain_service=domain,
        event_log=event_log,
        hub_identity_resolver=lambda: "hub-1",
        field_results=FIELD_RESULTS,
        field_event=FIELD_EVENT,
        field_group=FIELD_GROUP,
    )
    return api, domain, router, event_log


def _command(
    command_type: str,
    args: dict,
    *,
    command_id: str,
    correlation_id: str | None = None,
) -> dict:
    payload = {
        "command_id": command_id,
        "source": {"rns_identity": "peer-a"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command_type": command_type,
        "args": args,
    }
    if correlation_id is not None:
        payload["correlation_id"] = correlation_id
    return payload


def _grant_all_checklist_capabilities(api: ReticulumTelemetryHubAPI, identity: str) -> None:
    for capability in sorted(set(CHECKLIST_COMMAND_CAPABILITIES.values())):
        api.grant_identity_capability(identity, capability)


def _result(responses: list) -> dict:
    return responses[1].fields[FIELD_RESULTS]["result"]


def test_checklist_command_rejects_without_capability(tmp_path) -> None:
    _api, _domain, router, _log = _router(tmp_path)

    responses = router.handle_commands(
        [
            _command(
                "checklist.create.offline",
                {
                    "origin_type": "BLANK_TEMPLATE",
                    "name": "offline",
                    "description": "test",
                    "start_time": datetime.now(timezone.utc).isoformat(),
                },
                command_id="cmd-1",
            )
        ],
        source_identity="peer-a",
    )

    assert len(responses) == 1
    payload = responses[0].fields[FIELD_RESULTS]
    assert payload["status"] == "rejected"
    assert payload["reason_code"] == "unauthorized"


def test_checklist_command_accepts_with_capability(tmp_path) -> None:
    api, _domain, router, _log = _router(tmp_path)
    api.grant_identity_capability("peer-a", "checklist.write")

    responses = router.handle_commands(
        [
            _command(
                "checklist.create.offline",
                {
                    "origin_type": "BLANK_TEMPLATE",
                    "name": "offline",
                    "description": "test",
                    "start_time": datetime.now(timezone.utc).isoformat(),
                },
                command_id="cmd-2",
                correlation_id="corr-1",
            )
        ],
        source_identity="peer-a",
    )

    assert len(responses) == 2
    accepted = responses[0].fields[FIELD_RESULTS]
    result = responses[1].fields[FIELD_RESULTS]
    event = responses[1].fields[FIELD_EVENT]
    assert accepted["status"] == "accepted"
    assert result["status"] == "result"
    assert result["result"]["uid"]
    assert event["event_type"] == "checklist.created"


def test_checklist_command_matrix_success_paths(tmp_path) -> None:
    api, _domain, router, event_log = _router(tmp_path, include_event_log=True)
    _grant_all_checklist_capabilities(api, "peer-a")
    assert event_log is not None
    event_log.add_event("seed", "seed event")

    create_template = router.handle_commands(
        [
            _command(
                "checklist.template.create",
                {
                    "template": {
                        "template_name": "Template Alpha",
                        "description": "Template description",
                        "created_by_team_member_rns_identity": "peer-a",
                        "columns": [
                            {
                                "column_name": "Due",
                                "display_order": 1,
                                "column_type": "RELATIVE_TIME",
                                "column_editable": False,
                                "is_removable": False,
                                "system_key": "DUE_RELATIVE_DTG",
                            },
                            {
                                "column_name": "Task",
                                "display_order": 2,
                                "column_type": "SHORT_STRING",
                                "column_editable": True,
                                "is_removable": True,
                            },
                        ],
                    }
                },
                command_id="cmd-template-create",
            )
        ],
        source_identity="peer-a",
        group="checklist-group",
    )
    assert create_template[0].fields[FIELD_RESULTS]["status"] == "accepted"
    assert create_template[1].fields[FIELD_GROUP] == "checklist-group"
    template_uid = _result(create_template)["uid"]

    template_list = router.handle_commands(
        [_command("checklist.template.list", {}, command_id="cmd-template-list")],
        source_identity="peer-a",
    )
    assert _result(template_list)["templates"]

    template_update = router.handle_commands(
        [
            _command(
                "checklist.template.update",
                {
                    "template_uid": template_uid,
                    "patch": {
                        "template_name": "Template Beta",
                        "description": "Updated template",
                    },
                },
                command_id="cmd-template-update",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(template_update)["template_name"] == "Template Beta"

    template_clone = router.handle_commands(
        [
            _command(
                "checklist.template.clone",
                {
                    "source_template_uid": template_uid,
                    "template_name": "Template Clone",
                    "description": "Clone",
                },
                command_id="cmd-template-clone",
            )
        ],
        source_identity="peer-a",
    )
    clone_uid = _result(template_clone)["uid"]

    create_online = router.handle_commands(
        [
            _command(
                "checklist.create.online",
                {
                    "template_uid": template_uid,
                    "name": "Checklist Online",
                    "description": "Online checklist",
                    "start_time": datetime.now(timezone.utc).isoformat(),
                },
                command_id="cmd-checklist-online",
            )
        ],
        source_identity="peer-a",
    )
    checklist_uid = _result(create_online)["uid"]

    create_offline = router.handle_commands(
        [
            _command(
                "checklist.create.offline",
                {
                    "origin_type": "BLANK_TEMPLATE",
                    "name": "Checklist Offline",
                    "description": "Offline checklist",
                },
                command_id="cmd-checklist-offline",
            )
        ],
        source_identity="peer-a",
    )
    offline_uid = _result(create_offline)["uid"]

    checklist_update = router.handle_commands(
        [
            _command(
                "checklist.update",
                {
                    "checklist_uid": offline_uid,
                    "patch": {
                        "name": "Checklist Offline Updated",
                        "description": "Updated offline checklist",
                    },
                },
                command_id="cmd-checklist-update",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(checklist_update)["name"] == "Checklist Offline Updated"

    list_active = router.handle_commands(
        [_command("checklist.list.active", {}, command_id="cmd-checklist-list")],
        source_identity="peer-a",
    )
    assert _result(list_active)["checklists"]

    add_row = router.handle_commands(
        [
            _command(
                "checklist.task.row.add",
                {
                    "checklist_uid": checklist_uid,
                    "number": 1,
                    "due_relative_minutes": 10,
                },
                command_id="cmd-task-add",
            )
        ],
        source_identity="peer-a",
    )
    task_uid = _result(add_row)["tasks"][0]["task_uid"]
    short_text_column = next(
        col for col in _result(add_row)["columns"] if col["column_type"] == "SHORT_STRING"
    )

    cell_set = router.handle_commands(
        [
            _command(
                "checklist.task.cell.set",
                {
                    "checklist_uid": checklist_uid,
                    "task_uid": task_uid,
                    "column_uid": short_text_column["column_uid"],
                    "value": "Inspect area",
                    "updated_by_team_member_rns_identity": "peer-a",
                },
                command_id="cmd-task-cell-set",
            )
        ],
        source_identity="peer-a",
    )
    cells = _result(cell_set)["tasks"][0]["cells"]
    value = next(
        item["value"] for item in cells if item["column_uid"] == short_text_column["column_uid"]
    )
    assert value == "Inspect area"

    row_style = router.handle_commands(
        [
            _command(
                "checklist.task.row.style.set",
                {
                    "checklist_uid": checklist_uid,
                    "task_uid": task_uid,
                    "row_background_color": "#abc123",
                    "line_break_enabled": True,
                },
                command_id="cmd-task-style",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(row_style)["tasks"][0]["line_break_enabled"] is True

    status_set = router.handle_commands(
        [
            _command(
                "checklist.task.status.set",
                {
                    "checklist_uid": checklist_uid,
                    "task_uid": task_uid,
                    "user_status": "COMPLETE",
                    "changed_by_team_member_rns_identity": "peer-a",
                },
                command_id="cmd-task-status",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(status_set)["counts"]["complete_count"] == 1

    checklist_get = router.handle_commands(
        [
            _command(
                "checklist.get",
                {
                    "checklist_uid": checklist_uid,
                },
                command_id="cmd-checklist-get",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(checklist_get)["uid"] == checklist_uid

    checklist_join = router.handle_commands(
        [
            _command(
                "checklist.join",
                {
                    "checklist_uid": checklist_uid,
                },
                command_id="cmd-checklist-join",
            )
        ],
        source_identity="peer-a",
    )
    assert checklist_join[1].fields[FIELD_EVENT]["event_type"] == "checklist.joined"

    checklist_upload = router.handle_commands(
        [
            _command(
                "checklist.upload",
                {
                    "checklist_uid": offline_uid,
                },
                command_id="cmd-checklist-upload",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(checklist_upload)["sync_state"] == "SYNCED"

    feed_publish = router.handle_commands(
        [
            _command(
                "checklist.feed.publish",
                {
                    "checklist_uid": offline_uid,
                    "mission_feed_uid": "feed-1",
                },
                command_id="cmd-feed-publish",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(feed_publish)["mission_feed_uid"] == "feed-1"

    checklist_delete = router.handle_commands(
        [
            _command(
                "checklist.delete",
                {"checklist_uid": offline_uid},
                command_id="cmd-checklist-delete",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(checklist_delete)["uid"] == offline_uid

    delete_row = router.handle_commands(
        [
            _command(
                "checklist.task.row.delete",
                {
                    "checklist_uid": checklist_uid,
                    "task_uid": task_uid,
                },
                command_id="cmd-task-delete",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(delete_row)["tasks"] == []

    csv_payload = base64.b64encode(b"10,Task 1\n20,Task 2\n").decode("ascii")
    import_csv = router.handle_commands(
        [
            _command(
                "checklist.import.csv",
                {
                    "csv_filename": "import.csv",
                    "csv_base64": csv_payload,
                },
                command_id="cmd-import-csv",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(import_csv)["origin_type"] == "CSV_IMPORT"

    template_delete = router.handle_commands(
        [
            _command(
                "checklist.template.delete",
                {
                    "template_uid": clone_uid,
                },
                command_id="cmd-template-delete",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(template_delete)["uid"] == clone_uid


def test_checklist_command_error_paths(tmp_path) -> None:
    api, _domain, router, _log = _router(tmp_path, include_event_log=True)
    _grant_all_checklist_capabilities(api, "peer-a")

    invalid_payload = router.handle_commands(
        [{"command_id": 123, "command_type": "checklist.create.offline", "args": {}}],
        source_identity="peer-a",
    )
    assert invalid_payload[0].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    unknown_command = router.handle_commands(
        [
            _command(
                "checklist.unknown",
                {},
                command_id="cmd-unknown",
            )
        ],
        source_identity="peer-a",
    )
    assert unknown_command[0].fields[FIELD_RESULTS]["reason_code"] == "unknown_command"

    no_identity = router.handle_commands(
        [_command("checklist.template.list", {}, command_id="cmd-no-identity")],
        source_identity=None,
    )
    assert no_identity[0].fields[FIELD_RESULTS]["reason_code"] == "unauthorized"

    missing_template = router.handle_commands(
        [_command("checklist.template.create", {}, command_id="cmd-template-missing")],
        source_identity="peer-a",
    )
    assert missing_template[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    missing_template_uid = router.handle_commands(
        [
            _command(
                "checklist.template.update",
                {"patch": {}},
                command_id="cmd-template-update-missing",
            )
        ],
        source_identity="peer-a",
    )
    assert missing_template_uid[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    missing_clone_name = router.handle_commands(
        [
            _command(
                "checklist.template.clone",
                {"source_template_uid": "x"},
                command_id="cmd-template-clone-missing",
            )
        ],
        source_identity="peer-a",
    )
    assert missing_clone_name[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    missing_checklist_id = router.handle_commands(
        [_command("checklist.get", {}, command_id="cmd-checklist-get-missing")],
        source_identity="peer-a",
    )
    assert missing_checklist_id[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    unknown_checklist_id = router.handle_commands(
        [
            _command(
                "checklist.get",
                {"checklist_uid": "missing"},
                command_id="cmd-checklist-get-unknown",
            )
        ],
        source_identity="peer-a",
    )
    assert unknown_checklist_id[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    missing_publish_fields = router.handle_commands(
        [
            _command(
                "checklist.feed.publish",
                {"checklist_uid": "x"},
                command_id="cmd-feed-missing",
            )
        ],
        source_identity="peer-a",
    )
    assert missing_publish_fields[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    missing_task_fields = router.handle_commands(
        [
            _command(
                "checklist.task.status.set",
                {"checklist_uid": "x"},
                command_id="cmd-task-status-missing",
            )
        ],
        source_identity="peer-a",
    )
    assert missing_task_fields[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    missing_row_add = router.handle_commands(
        [
            _command(
                "checklist.task.row.add",
                {},
                command_id="cmd-task-add-missing",
            )
        ],
        source_identity="peer-a",
    )
    assert missing_row_add[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    missing_update_fields = router.handle_commands(
        [
            _command(
                "checklist.update",
                {"checklist_uid": "x"},
                command_id="cmd-checklist-update-missing",
            )
        ],
        source_identity="peer-a",
    )
    assert missing_update_fields[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"


def test_checklist_command_rejects_source_identity_mismatch(tmp_path) -> None:
    api, _domain, router, _log = _router(tmp_path)
    api.grant_identity_capability("peer-a", "checklist.template.read")
    responses = router.handle_commands(
        [_command("checklist.template.list", {}, command_id="cmd-source-mismatch")],
        source_identity="peer-b",
    )
    assert responses[0].fields[FIELD_RESULTS]["reason_code"] == "unauthorized"
