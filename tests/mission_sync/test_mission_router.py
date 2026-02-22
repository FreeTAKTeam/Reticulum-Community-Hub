from __future__ import annotations

from datetime import datetime
from datetime import timezone

from reticulum_telemetry_hub.api.storage_models import ClientRecord
from reticulum_telemetry_hub.api.storage_models import ZoneRecord
from reticulum_telemetry_hub.api.marker_service import MarkerService
from reticulum_telemetry_hub.api.marker_storage import MarkerStorage
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.zone_service import ZoneService
from reticulum_telemetry_hub.api.zone_storage import ZoneStorage
from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.mission_sync.capabilities import MISSION_COMMAND_CAPABILITIES
from reticulum_telemetry_hub.mission_sync.router import MissionSyncRouter
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from tests.test_rth_api import make_config_manager


FIELD_RESULTS = 10
FIELD_GROUP = 11
FIELD_EVENT = 13


def _router(
    tmp_path,
    *,
    include_marker: bool = False,
    include_zone: bool = False,
    include_event_log: bool = False,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = make_config_manager(tmp_path)
    api = ReticulumTelemetryHubAPI(config_manager=cfg)

    marker_service = (
        MarkerService(
            MarkerStorage(cfg.config.hub_database_path),
            identity_key_provider=lambda: b"\x11" * 32,
        )
        if include_marker
        else None
    )
    zone_service = ZoneService(ZoneStorage(cfg.config.hub_database_path)) if include_zone else None
    domain_service = MissionDomainService(cfg.config.hub_database_path)
    event_log = EventLog() if include_event_log else None
    sent_messages: list[tuple[str, str | None, str | None]] = []

    def _send_message(content: str, topic_id: str | None, destination: str | None) -> bool:
        sent_messages.append((content, topic_id, destination))
        return True

    router = MissionSyncRouter(
        api=api,
        send_message=_send_message,
        marker_service=marker_service,
        zone_service=zone_service,
        domain_service=domain_service,
        event_log=event_log,
        hub_identity_resolver=lambda: "hub-1",
        field_results=FIELD_RESULTS,
        field_event=FIELD_EVENT,
        field_group=FIELD_GROUP,
    )
    return api, router, sent_messages, event_log


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


def _grant_all_mission_capabilities(api: ReticulumTelemetryHubAPI, identity: str) -> None:
    for capability in sorted(set(MISSION_COMMAND_CAPABILITIES.values())):
        api.grant_identity_capability(identity, capability)


def _result(responses: list) -> dict:
    return responses[1].fields[FIELD_RESULTS]["result"]


def test_mission_command_rejects_without_capability(tmp_path) -> None:
    _api, router, _sent, _log = _router(tmp_path)

    responses = router.handle_commands(
        [
            _command(
                "mission.join",
                {"identity": "peer-a"},
                command_id="cmd-1",
            )
        ],
        source_identity="peer-a",
    )

    assert len(responses) == 1
    payload = responses[0].fields[FIELD_RESULTS]
    assert payload["status"] == "rejected"
    assert payload["reason_code"] == "unauthorized"


def test_mission_command_accepts_with_capability(tmp_path) -> None:
    api, router, _sent, _log = _router(tmp_path)
    api.grant_identity_capability("peer-a", "mission.join")

    responses = router.handle_commands(
        [
            _command(
                "mission.join",
                {"identity": "peer-a"},
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
    assert result["result"]["joined"] is True
    assert event["event_type"] == "mission.joined"


def test_mission_command_matrix_success_paths(tmp_path) -> None:
    api, router, sent_messages, event_log = _router(
        tmp_path,
        include_marker=True,
        include_zone=True,
        include_event_log=True,
    )
    _grant_all_mission_capabilities(api, "peer-a")
    assert event_log is not None
    event_log.add_event("seed", "seed event")

    join_result = router.handle_commands(
        [_command("mission.join", {"identity": "peer-a"}, command_id="cmd-join")],
        source_identity="peer-a",
    )
    assert _result(join_result)["joined"] is True

    create_topic = router.handle_commands(
        [
            _command(
                "topic.create",
                {
                    "topic_id": "topic-1",
                    "topic_name": "Ops",
                    "topic_path": "/ops",
                    "topic_description": "Operations topic",
                },
                command_id="cmd-topic-create",
            )
        ],
        source_identity="peer-a",
        group="grp-1",
    )
    assert create_topic[0].fields[FIELD_RESULTS]["status"] == "accepted"
    assert create_topic[1].fields[FIELD_RESULTS]["status"] == "result"
    assert create_topic[1].fields[FIELD_GROUP] == "grp-1"
    topic_id = _result(create_topic)["TopicID"]

    message_result = router.handle_commands(
        [
            _command(
                "mission.message.send",
                {"content": "hello", "topic_id": topic_id, "destination": "dest-1"},
                command_id="cmd-message-send",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(message_result)["sent"] is True
    assert sent_messages[-1] == ("hello", topic_id, "dest-1")

    events_result = router.handle_commands(
        [_command("mission.events.list", {}, command_id="cmd-events")],
        source_identity="peer-a",
    )
    assert _result(events_result)["events"]

    list_result = router.handle_commands(
        [_command("topic.list", {}, command_id="cmd-topic-list")],
        source_identity="peer-a",
    )
    assert _result(list_result)["topics"]

    patch_result = router.handle_commands(
        [
            _command(
                "topic.patch",
                {
                    "topic_id": topic_id,
                    "topic_name": "Ops Renamed",
                    "topic_path": "/ops-renamed",
                    "topic_description": "Updated",
                },
                command_id="cmd-topic-patch",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(patch_result)["TopicName"] == "Ops Renamed"

    subscribe_result = router.handle_commands(
        [
            _command(
                "topic.subscribe",
                {
                    "topic_id": topic_id,
                    "destination": "dest-2",
                    "reject_tests": "not-int",
                    "metadata": {"kind": "operator"},
                },
                command_id="cmd-topic-subscribe",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(subscribe_result)["Destination"] == "dest-2"

    marker_create_result = router.handle_commands(
        [
            _command(
                "mission.marker.create",
                {
                    "name": "Marker One",
                    "marker_type": "marker",
                    "symbol": "marker",
                    "category": "marker",
                    "lat": 45.0,
                    "lon": -93.0,
                    "notes": "hello",
                    "ttl_seconds": 120,
                },
                command_id="cmd-marker-create",
            )
        ],
        source_identity="peer-a",
    )
    marker_hash = _result(marker_create_result)["object_destination_hash"]

    marker_list_result = router.handle_commands(
        [_command("mission.marker.list", {}, command_id="cmd-marker-list")],
        source_identity="peer-a",
    )
    assert marker_list_result[1].fields[FIELD_EVENT]["event_type"] == "mission.marker.listed"
    assert _result(marker_list_result)["markers"]

    marker_patch_result = router.handle_commands(
        [
            _command(
                "mission.marker.position.patch",
                {
                    "object_destination_hash": marker_hash,
                    "lat": 45.1,
                    "lon": -93.1,
                },
                command_id="cmd-marker-patch",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(marker_patch_result)["object_destination_hash"] == marker_hash

    zone_create_result = router.handle_commands(
        [
            _command(
                "mission.zone.create",
                {
                    "name": "Zone One",
                    "points": [
                        {"lat": 10.0, "lon": 10.0},
                        {"lat": 10.0, "lon": 11.0},
                        {"lat": 11.0, "lon": 10.0},
                    ],
                },
                command_id="cmd-zone-create",
            )
        ],
        source_identity="peer-a",
    )
    zone_id = _result(zone_create_result)["zone_id"]

    zone_list_result = router.handle_commands(
        [_command("mission.zone.list", {}, command_id="cmd-zone-list")],
        source_identity="peer-a",
    )
    assert _result(zone_list_result)["zones"]

    zone_patch_result = router.handle_commands(
        [
            _command(
                "mission.zone.patch",
                {
                    "zone_id": zone_id,
                    "name": "Zone Two",
                    "points": [
                        {"lat": 20.0, "lon": 20.0},
                        {"lat": 20.0, "lon": 21.0},
                        {"lat": 21.0, "lon": 20.0},
                    ],
                },
                command_id="cmd-zone-patch",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(zone_patch_result)["name"] == "Zone Two"

    zone_delete_result = router.handle_commands(
        [_command("mission.zone.delete", {"zone_id": zone_id}, command_id="cmd-zone-delete")],
        source_identity="peer-a",
    )
    assert _result(zone_delete_result)["zone_id"] == zone_id

    topic_delete_result = router.handle_commands(
        [_command("topic.delete", {"topic_id": topic_id}, command_id="cmd-topic-delete")],
        source_identity="peer-a",
    )
    assert _result(topic_delete_result)["TopicID"] == topic_id

    leave_result = router.handle_commands(
        [_command("mission.leave", {"identity": "peer-a"}, command_id="cmd-leave")],
        source_identity="peer-a",
    )
    assert _result(leave_result)["left"] is True


def test_mission_command_error_paths(tmp_path) -> None:
    api, router, _sent, _log = _router(tmp_path, include_event_log=True)
    _grant_all_mission_capabilities(api, "peer-a")

    invalid_payload = router.handle_commands(
        [{"command_id": 123, "command_type": "mission.join", "args": {}}],
        source_identity="peer-a",
    )
    assert invalid_payload[0].fields[FIELD_RESULTS]["status"] == "rejected"
    assert invalid_payload[0].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    unknown_command = router.handle_commands(
        [
            _command(
                "mission.unknown",
                {},
                command_id="cmd-unknown",
            )
        ],
        source_identity="peer-a",
    )
    assert unknown_command[0].fields[FIELD_RESULTS]["reason_code"] == "unknown_command"

    no_identity = router.handle_commands(
        [_command("mission.join", {"identity": "peer-a"}, command_id="cmd-no-identity")],
        source_identity=None,
    )
    assert no_identity[0].fields[FIELD_RESULTS]["reason_code"] == "unauthorized"

    message_invalid = router.handle_commands(
        [_command("mission.message.send", {"content": " "}, command_id="cmd-msg-invalid")],
        source_identity="peer-a",
    )
    assert message_invalid[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    topic_create_invalid = router.handle_commands(
        [_command("topic.create", {}, command_id="cmd-topic-invalid")],
        source_identity="peer-a",
    )
    assert topic_create_invalid[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    topic_patch_invalid = router.handle_commands(
        [_command("topic.patch", {"topic_name": "x"}, command_id="cmd-topic-patch-invalid")],
        source_identity="peer-a",
    )
    assert topic_patch_invalid[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    topic_delete_invalid = router.handle_commands(
        [_command("topic.delete", {}, command_id="cmd-topic-delete-invalid")],
        source_identity="peer-a",
    )
    assert topic_delete_invalid[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    marker_without_service = router.handle_commands(
        [_command("mission.marker.list", {}, command_id="cmd-marker-no-service")],
        source_identity="peer-a",
    )
    assert marker_without_service[1].fields[FIELD_RESULTS]["reason_code"] == "unsupported_operation"

    zone_without_service = router.handle_commands(
        [_command("mission.zone.list", {}, command_id="cmd-zone-no-service")],
        source_identity="peer-a",
    )
    assert zone_without_service[1].fields[FIELD_RESULTS]["reason_code"] == "unsupported_operation"

    api_with_zone, router_with_zone, _sent2, _log2 = _router(tmp_path / "zones", include_zone=True)
    _grant_all_mission_capabilities(api_with_zone, "peer-a")
    zone_points_invalid = router_with_zone.handle_commands(
        [
            _command(
                "mission.zone.create",
                {"name": "Z", "points": "not-a-list"},
                command_id="cmd-zone-points-invalid",
            )
        ],
        source_identity="peer-a",
    )
    assert zone_points_invalid[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    zone_patch_invalid = router_with_zone.handle_commands(
        [_command("mission.zone.patch", {"name": "x"}, command_id="cmd-zone-patch-invalid")],
        source_identity="peer-a",
    )
    assert zone_patch_invalid[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    zone_patch_unknown = router_with_zone.handle_commands(
        [
            _command(
                "mission.zone.patch",
                {"zone_id": "missing-zone", "name": "x"},
                command_id="cmd-zone-patch-unknown",
            )
        ],
        source_identity="peer-a",
    )
    assert zone_patch_unknown[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    zone_delete_invalid = router_with_zone.handle_commands(
        [_command("mission.zone.delete", {}, command_id="cmd-zone-delete-invalid")],
        source_identity="peer-a",
    )
    assert zone_delete_invalid[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"

    api_with_marker, router_with_marker, _sent3, _log3 = _router(
        tmp_path / "markers", include_marker=True
    )
    _grant_all_mission_capabilities(api_with_marker, "peer-a")
    marker_patch_invalid = router_with_marker.handle_commands(
        [
            _command(
                "mission.marker.position.patch",
                {"lat": "bad", "lon": -1},
                command_id="cmd-marker-patch-invalid",
            )
        ],
        source_identity="peer-a",
    )
    assert marker_patch_invalid[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"


def test_mission_registry_command_paths(tmp_path) -> None:
    api, router, _sent, _log = _router(tmp_path, include_zone=True)
    _grant_all_mission_capabilities(api, "peer-a")
    domain = router._domain  # pylint: disable=protected-access
    assert domain is not None

    domain.upsert_mission({"uid": "mission-1", "mission_name": "Mission 1"})
    domain.upsert_mission({"uid": "mission-2", "mission_name": "Mission 2"})
    domain.upsert_team({"uid": "team-1", "mission_uid": "mission-1", "team_name": "Team"})
    domain.upsert_team_member(
        {
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "peer-a",
            "display_name": "Peer A",
        }
    )
    domain.upsert_asset(
        {
            "asset_uid": "asset-1",
            "team_member_uid": "member-1",
            "name": "Radio",
            "asset_type": "COMM",
        }
    )
    with domain._session() as session:  # pylint: disable=protected-access
        session.add(ClientRecord(identity="peer-a"))
        session.add(
            ZoneRecord(
                id="zone-1",
                name="Zone One",
                points_json=[
                    {"lat": 10.0, "lon": 10.0},
                    {"lat": 10.0, "lon": 11.0},
                    {"lat": 11.0, "lon": 10.0},
                ],
            )
        )

    mission_upsert = router.handle_commands(
        [
            _command(
                "mission.registry.mission.upsert",
                {"uid": "mission-3", "mission_name": "Mission 3"},
                command_id="cmd-registry-mission-upsert",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(mission_upsert)["uid"] == "mission-3"

    mission_get = router.handle_commands(
        [
            _command(
                "mission.registry.mission.get",
                {"mission_uid": "mission-1"},
                command_id="cmd-registry-mission-get",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(mission_get)["uid"] == "mission-1"

    mission_list = router.handle_commands(
        [
            _command(
                "mission.registry.mission.list",
                {"expand_topic": False},
                command_id="cmd-registry-mission-list",
            )
        ],
        source_identity="peer-a",
    )
    assert any(item["uid"] == "mission-1" for item in _result(mission_list)["missions"])

    mission_change_upsert = router.handle_commands(
        [
            _command(
                "mission.registry.mission_change.upsert",
                {
                    "uid": "change-1",
                    "mission_uid": "mission-1",
                    "name": "Updated objective",
                    "change_type": "ADD_CONTENT",
                },
                command_id="cmd-registry-change-upsert",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(mission_change_upsert)["uid"] == "change-1"

    mission_change_list = router.handle_commands(
        [
            _command(
                "mission.registry.mission_change.list",
                {"mission_uid": "mission-1"},
                command_id="cmd-registry-change-list",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(mission_change_list)["mission_changes"]

    log_entry_upsert = router.handle_commands(
        [
            _command(
                "mission.registry.log_entry.upsert",
                {
                    "entry_uid": "log-1",
                    "mission_uid": "mission-1",
                    "content": "Log event",
                },
                command_id="cmd-registry-log-upsert",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(log_entry_upsert)["entry_uid"] == "log-1"

    log_entry_list = router.handle_commands(
        [
            _command(
                "mission.registry.log_entry.list",
                {"mission_uid": "mission-1"},
                command_id="cmd-registry-log-list",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(log_entry_list)["log_entries"]

    team_upsert = router.handle_commands(
        [
            _command(
                "mission.registry.team.upsert",
                {
                    "uid": "team-2",
                    "team_name": "Bravo",
                    "mission_uid": "mission-1",
                },
                command_id="cmd-registry-team-upsert",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(team_upsert)["uid"] == "team-2"

    team_get = router.handle_commands(
        [
            _command(
                "mission.registry.team.get",
                {"team_uid": "team-2"},
                command_id="cmd-registry-team-get",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(team_get)["uid"] == "team-2"

    team_list = router.handle_commands(
        [
            _command(
                "mission.registry.team.list",
                {"mission_uid": "mission-1"},
                command_id="cmd-registry-team-list",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(team_list)["teams"]

    team_mission_link = router.handle_commands(
        [
            _command(
                "mission.registry.team.mission.link",
                {"team_uid": "team-1", "mission_uid": "mission-2"},
                command_id="cmd-registry-team-mission-link",
            )
        ],
        source_identity="peer-a",
    )
    assert "mission-2" in _result(team_mission_link)["mission_uids"]

    patch = router.handle_commands(
        [
            _command(
                "mission.registry.mission.patch",
                {"mission_uid": "mission-1", "mission_priority": 5},
                command_id="cmd-registry-patch",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(patch)["mission_priority"] == 5

    parent = router.handle_commands(
        [
            _command(
                "mission.registry.mission.parent.set",
                {"mission_uid": "mission-2", "parent_uid": "mission-1"},
                command_id="cmd-registry-parent",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(parent)["parent_uid"] == "mission-1"

    zone_link = router.handle_commands(
        [
            _command(
                "mission.registry.mission.zone.link",
                {"mission_uid": "mission-1", "zone_id": "zone-1"},
                command_id="cmd-registry-zone-link",
            )
        ],
        source_identity="peer-a",
    )
    assert "zone-1" in _result(zone_link)["zones"]

    rde = router.handle_commands(
        [
            _command(
                "mission.registry.mission.rde.set",
                {"mission_uid": "mission-1", "role": "MISSION_OWNER"},
                command_id="cmd-registry-rde",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(rde)["role"] == "MISSION_OWNER"

    member_upsert = router.handle_commands(
        [
            _command(
                "mission.registry.team_member.upsert",
                {
                    "uid": "member-2",
                    "team_uid": "team-1",
                    "rns_identity": "peer-b",
                    "display_name": "Peer B",
                },
                command_id="cmd-registry-member-upsert",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(member_upsert)["uid"] == "member-2"

    member_get = router.handle_commands(
        [
            _command(
                "mission.registry.team_member.get",
                {"team_member_uid": "member-2"},
                command_id="cmd-registry-member-get",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(member_get)["uid"] == "member-2"

    member_list = router.handle_commands(
        [
            _command(
                "mission.registry.team_member.list",
                {"team_uid": "team-1"},
                command_id="cmd-registry-member-list",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(member_list)["team_members"]

    member_link = router.handle_commands(
        [
            _command(
                "mission.registry.team_member.client.link",
                {"team_member_uid": "member-1", "client_identity": "peer-a"},
                command_id="cmd-registry-member-link",
            )
        ],
        source_identity="peer-a",
    )
    assert "peer-a" in _result(member_link)["client_identities"]

    asset_upsert = router.handle_commands(
        [
            _command(
                "mission.registry.asset.upsert",
                {
                    "asset_uid": "asset-2",
                    "team_member_uid": "member-1",
                    "name": "Battery Pack",
                    "asset_type": "POWER",
                },
                command_id="cmd-registry-asset-upsert",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(asset_upsert)["asset_uid"] == "asset-2"

    asset_get = router.handle_commands(
        [
            _command(
                "mission.registry.asset.get",
                {"asset_uid": "asset-2"},
                command_id="cmd-registry-asset-get",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(asset_get)["asset_uid"] == "asset-2"

    asset_list = router.handle_commands(
        [
            _command(
                "mission.registry.asset.list",
                {"team_member_uid": "member-1"},
                command_id="cmd-registry-asset-list",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(asset_list)["assets"]

    skill_upsert = router.handle_commands(
        [
            _command(
                "mission.registry.skill.upsert",
                {
                    "skill_uid": "skill-1",
                    "name": "Navigation",
                },
                command_id="cmd-registry-skill-upsert",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(skill_upsert)["skill_uid"] == "skill-1"

    skill_list = router.handle_commands(
        [
            _command(
                "mission.registry.skill.list",
                {},
                command_id="cmd-registry-skill-list",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(skill_list)["skills"]

    member_skill_upsert = router.handle_commands(
        [
            _command(
                "mission.registry.team_member_skill.upsert",
                {
                    "uid": "member-skill-1",
                    "team_member_rns_identity": "peer-a",
                    "skill_uid": "skill-1",
                    "level": 3,
                },
                command_id="cmd-registry-member-skill-upsert",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(member_skill_upsert)["uid"] == "member-skill-1"

    member_skill_list = router.handle_commands(
        [
            _command(
                "mission.registry.team_member_skill.list",
                {"team_member_rns_identity": "peer-a"},
                command_id="cmd-registry-member-skill-list",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(member_skill_list)["team_member_skills"]

    checklist = domain.create_checklist_offline(
        {
            "name": "Offline",
            "origin_type": "BLANK_TEMPLATE",
            "source_identity": "peer-a",
            "mission_uid": "mission-1",
        }
    )
    task_uid = domain.add_checklist_task_row(checklist["uid"], {"number": 1})["tasks"][0]["task_uid"]
    domain.upsert_assignment(
        {
            "assignment_uid": "assignment-1",
            "mission_uid": "mission-1",
            "task_uid": task_uid,
            "team_member_rns_identity": "peer-a",
            "assets": [],
        }
    )

    requirement_upsert = router.handle_commands(
        [
            _command(
                "mission.registry.task_skill_requirement.upsert",
                {
                    "uid": "requirement-1",
                    "task_uid": task_uid,
                    "skill_uid": "skill-1",
                    "minimum_level": 2,
                },
                command_id="cmd-registry-requirement-upsert",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(requirement_upsert)["uid"] == "requirement-1"

    requirement_list = router.handle_commands(
        [
            _command(
                "mission.registry.task_skill_requirement.list",
                {"task_uid": task_uid},
                command_id="cmd-registry-requirement-list",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(requirement_list)["task_skill_requirements"]

    assignment_upsert = router.handle_commands(
        [
            _command(
                "mission.registry.assignment.upsert",
                {
                    "assignment_uid": "assignment-2",
                    "mission_uid": "mission-1",
                    "task_uid": task_uid,
                    "team_member_rns_identity": "peer-a",
                },
                command_id="cmd-registry-assignment-upsert",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(assignment_upsert)["assignment_uid"] == "assignment-2"

    assignment_list = router.handle_commands(
        [
            _command(
                "mission.registry.assignment.list",
                {"mission_uid": "mission-1"},
                command_id="cmd-registry-assignment-list",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(assignment_list)["assignments"]

    mission_get_expanded = router.handle_commands(
        [
            _command(
                "mission.registry.mission.get",
                {
                    "mission_uid": "mission-1",
                    "expand": [
                        "teams",
                        "team_members",
                        "assets",
                        "mission_changes",
                        "log_entries",
                        "assignments",
                        "checklists",
                        "mission_rde",
                    ],
                },
                command_id="cmd-registry-mission-get-expanded",
            )
        ],
        source_identity="peer-a",
    )
    expanded_payload = _result(mission_get_expanded)
    assert expanded_payload["teams"]
    assert expanded_payload["team_members"]
    assert expanded_payload["assets"]
    assert expanded_payload["mission_changes"]
    assert expanded_payload["log_entries"]
    assert expanded_payload["assignments"]
    assert expanded_payload["checklists"]
    assert expanded_payload["mission_rde"]["role"] == "MISSION_OWNER"

    asset_set = router.handle_commands(
        [
            _command(
                "mission.registry.assignment.asset.set",
                {"assignment_uid": "assignment-1", "assets": ["asset-1"]},
                command_id="cmd-registry-asset-set",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(asset_set)["assets"] == ["asset-1"]

    asset_link = router.handle_commands(
        [
            _command(
                "mission.registry.assignment.asset.link",
                {"assignment_uid": "assignment-1", "asset_uid": "asset-1"},
                command_id="cmd-registry-asset-link",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(asset_link)["assets"] == ["asset-1"]

    asset_delete = router.handle_commands(
        [
            _command(
                "mission.registry.asset.delete",
                {"asset_uid": "asset-2"},
                command_id="cmd-registry-asset-delete",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(asset_delete)["asset_uid"] == "asset-2"

    member_delete = router.handle_commands(
        [
            _command(
                "mission.registry.team_member.delete",
                {"team_member_uid": "member-2"},
                command_id="cmd-registry-member-delete",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(member_delete)["uid"] == "member-2"

    team_delete = router.handle_commands(
        [
            _command(
                "mission.registry.team.delete",
                {"team_uid": "team-2"},
                command_id="cmd-registry-team-delete",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(team_delete)["uid"] == "team-2"

    team_mission_unlink = router.handle_commands(
        [
            _command(
                "mission.registry.team.mission.unlink",
                {"team_uid": "team-1", "mission_uid": "mission-2"},
                command_id="cmd-registry-team-mission-unlink",
            )
        ],
        source_identity="peer-a",
    )
    assert "mission-2" not in _result(team_mission_unlink)["mission_uids"]

    delete = router.handle_commands(
        [
            _command(
                "mission.registry.mission.delete",
                {"mission_uid": "mission-2"},
                command_id="cmd-registry-delete",
            )
        ],
        source_identity="peer-a",
    )
    assert _result(delete)["mission_status"] == "MISSION_DELETED"


def test_mission_command_rejects_source_identity_mismatch(tmp_path) -> None:
    api, router, _sent, _log = _router(tmp_path)
    api.grant_identity_capability("peer-a", "mission.join")
    responses = router.handle_commands(
        [_command("mission.join", {"identity": "peer-a"}, command_id="cmd-mismatch")],
        source_identity="peer-b",
    )
    assert responses[0].fields[FIELD_RESULTS]["reason_code"] == "unauthorized"
