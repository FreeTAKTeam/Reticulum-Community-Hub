from __future__ import annotations

from datetime import datetime
from datetime import timezone

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.mission_domain import EmergencyActionMessageService
from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.mission_domain.canonical_teams import CANONICAL_COLOR_TEAM_UIDS
from reticulum_telemetry_hub.mission_sync.router import MissionSyncRouter
from tests.test_rth_api import make_config_manager


FIELD_RESULTS = 10
FIELD_GROUP = 11
FIELD_EVENT = 13


def _router(tmp_path):
    cfg = make_config_manager(tmp_path)
    api = ReticulumTelemetryHubAPI(config_manager=cfg)
    domain = MissionDomainService(cfg.config.hub_database_path)
    status_service = EmergencyActionMessageService(cfg.config.hub_database_path)

    router = MissionSyncRouter(
        api=api,
        send_message=lambda _content, _topic_id, _destination: True,
        marker_service=None,
        zone_service=None,
        domain_service=domain,
        emergency_action_message_service=status_service,
        event_log=None,
        hub_identity_resolver=lambda: "hub-1",
        field_results=FIELD_RESULTS,
        field_event=FIELD_EVENT,
        field_group=FIELD_GROUP,
    )
    return api, domain, router


def _command(command_type: str, args: dict[str, object], *, command_id: str) -> dict[str, object]:
    return {
        "command_id": command_id,
        "source": {"rns_identity": "peer-a"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command_type": command_type,
        "args": args,
    }


def _seed_member(
    domain: MissionDomainService,
    *,
    mission_uid: str | None = "mission-1",
    team_uid: str = "team-1",
    team_member_uid: str = "member-1",
    team_name: str = "Ops",
    callsign: str = "ORANGE-1",
) -> None:
    if mission_uid is not None:
        domain.upsert_mission({"uid": mission_uid, "mission_name": "Mission One"})
        domain.upsert_team(
            {
                "uid": team_uid,
                "team_name": team_name,
                "mission_uid": mission_uid,
            }
        )
    else:
        domain.upsert_team({"uid": team_uid, "team_name": team_name})
    domain.upsert_team_member(
        {
            "uid": team_member_uid,
            "team_uid": team_uid,
            "rns_identity": "peer-a",
            "display_name": "Peer A",
            "callsign": callsign,
        }
    )


def _grant_status_capabilities(api: ReticulumTelemetryHubAPI, identity: str = "peer-a") -> None:
    api.grant_identity_capability(identity, "mission.registry.status.read")
    api.grant_identity_capability(identity, "mission.registry.status.write")


def _terminal_result(responses: list) -> dict[str, object]:
    return responses[1].fields[FIELD_RESULTS]["result"]


def _terminal_event(responses: list) -> dict[str, object]:
    return responses[1].fields[FIELD_EVENT]


def test_eam_command_matrix_success_paths(tmp_path) -> None:
    api, _domain, router = _router(tmp_path)
    _grant_status_capabilities(api)

    team_uid = CANONICAL_COLOR_TEAM_UIDS["ORANGE"]
    reported_at = datetime.now(timezone.utc).isoformat()
    upsert = router.handle_commands(
        [
            _command(
                "mission.registry.eam.upsert",
                {
                    "callsign": "ORANGE-1",
                    "team_member_uid": "member-1",
                    "team_uid": team_uid,
                    "reported_by": "peer-a",
                    "reported_at": reported_at,
                    "security_status": "Green",
                    "capability_status": "Yellow",
                    "preparedness_status": "Green",
                    "medical_status": "Unknown",
                    "mobility_status": "Green",
                    "comms_status": "Red",
                    "notes": "Alternate comms required",
                    "confidence": 0.8,
                    "ttl_seconds": 3600,
                    "source": {"rns_identity": "peer-a", "display_name": "Peer A"},
                },
                command_id="cmd-eam-upsert",
            )
        ],
        source_identity="peer-a",
    )

    assert upsert[0].fields[FIELD_RESULTS]["status"] == "accepted"
    assert _terminal_event(upsert)["event_type"] == "mission.registry.eam.upserted"
    snapshot = _terminal_result(upsert)["eam"]
    assert snapshot["eam_uid"]
    assert snapshot["callsign"] == "ORANGE-1"
    assert snapshot["group_name"] == "ORANGE"
    assert snapshot["team_member_uid"] == "member-1"
    assert snapshot["team_uid"] == team_uid
    assert snapshot["reported_by"] == "peer-a"
    assert snapshot["overall_status"] == "Red"
    assert snapshot["source"] == {"rns_identity": "peer-a", "display_name": "Peer A"}
    assert _terminal_event(upsert)["payload"]["eam"]["group_name"] == "ORANGE"

    listed = router.handle_commands(
        [_command("mission.registry.eam.list", {"team_uid": team_uid}, command_id="cmd-eam-list")],
        source_identity="peer-a",
    )
    assert _terminal_event(listed)["event_type"] == "mission.registry.eam.listed"
    assert _terminal_result(listed)["eams"][0]["group_name"] == "ORANGE"
    assert _terminal_result(listed)["eams"][0]["source"] == {
        "rns_identity": "peer-a",
        "display_name": "Peer A",
    }

    fetched = router.handle_commands(
        [_command("mission.registry.eam.get", {"callsign": "ORANGE-1"}, command_id="cmd-eam-get")],
        source_identity="peer-a",
    )
    assert _terminal_event(fetched)["event_type"] == "mission.registry.eam.retrieved"
    assert _terminal_result(fetched)["eam"]["group_name"] == "ORANGE"

    latest = router.handle_commands(
        [
            _command(
                "mission.registry.eam.latest",
                {"team_member_uid": "member-1"},
                command_id="cmd-eam-latest",
            )
        ],
        source_identity="peer-a",
    )
    assert _terminal_event(latest)["event_type"] == "mission.registry.eam.latest_retrieved"
    assert _terminal_result(latest)["eam"]["team_member_uid"] == "member-1"
    assert _terminal_result(latest)["eam"]["group_name"] == "ORANGE"

    summary = router.handle_commands(
        [
            _command(
                "mission.registry.eam.team.summary",
                {"team_uid": team_uid},
                command_id="cmd-eam-summary",
            )
        ],
        source_identity="peer-a",
    )
    summary_payload = _terminal_result(summary)["summary"]
    assert summary_payload == {
        "team_uid": team_uid,
        "total": 1,
        "active_total": 1,
        "deleted_total": 0,
        "overall_status": "Red",
        "green_total": 0,
        "yellow_total": 0,
        "red_total": 1,
        "updated_at_ms": summary_payload["updated_at_ms"],
    }
    assert isinstance(summary_payload["updated_at_ms"], int)
    assert _terminal_event(summary)["event_type"] == "mission.registry.eam.team_summary.retrieved"

    deleted = router.handle_commands(
        [
            _command(
                "mission.registry.eam.delete",
                {"callsign": "ORANGE-1"},
                command_id="cmd-eam-delete",
            )
        ],
        source_identity="peer-a",
    )
    assert _terminal_event(deleted)["event_type"] == "mission.registry.eam.deleted"
    assert _terminal_result(deleted)["eam"]["callsign"] == "ORANGE-1"
    assert _terminal_result(deleted)["eam"]["group_name"] == "ORANGE"


def test_eam_command_rejects_http_shape_fields_and_aliases(tmp_path) -> None:
    api, _domain, router = _router(tmp_path)
    _grant_status_capabilities(api)

    for field_name, field_value in (
        ("securityCapability", "Yellow"),
        ("subjectId", "member-1"),
        ("groupName", "ORANGE"),
    ):
        responses = router.handle_commands(
            [
                _command(
                    "mission.registry.eam.upsert",
                    {
                        "callsign": "ORANGE-1",
                        "team_member_uid": "member-1",
                        "team_uid": CANONICAL_COLOR_TEAM_UIDS["ORANGE"],
                        field_name: field_value,
                    },
                    command_id=f"cmd-eam-bad-{field_name}",
                )
            ],
            source_identity="peer-a",
        )

        assert len(responses) == 2
        assert responses[1].fields[FIELD_RESULTS]["status"] == "rejected"
        assert responses[1].fields[FIELD_RESULTS]["reason_code"] == "invalid_payload"


def test_eam_command_accepts_mission_scoped_status_rights(tmp_path) -> None:
    api, domain, router = _router(tmp_path)
    _seed_member(domain, mission_uid="mission-1")
    api.assign_mission_access_role(
        "mission-1",
        "team_member",
        "member-1",
        role="MISSION_SUBSCRIBER",
    )

    responses = router.handle_commands(
        [
            _command(
                "mission.registry.eam.upsert",
                {
                    "callsign": "ORANGE-1",
                    "team_member_uid": "member-1",
                    "team_uid": "team-1",
                    "source": {"rns_identity": "peer-a", "display_name": "Peer A"},
                },
                command_id="cmd-eam-mission-scoped",
            )
        ],
        source_identity="peer-a",
    )

    assert len(responses) == 2
    assert _terminal_result(responses)["eam"]["team_member_uid"] == "member-1"
    assert _terminal_result(responses)["eam"]["group_name"] == "Ops"


def test_eam_command_falls_back_to_global_rights_without_mission_link(tmp_path) -> None:
    api, _domain, router = _router(tmp_path)
    _grant_status_capabilities(api)

    responses = router.handle_commands(
        [
            _command(
                "mission.registry.eam.upsert",
                {
                    "callsign": "ORANGE-1",
                    "team_member_uid": "member-1",
                    "team_uid": CANONICAL_COLOR_TEAM_UIDS["ORANGE"],
                    "source": {"rns_identity": "peer-a", "display_name": "Peer A"},
                },
                command_id="cmd-eam-global-fallback",
            )
        ],
        source_identity="peer-a",
    )

    assert len(responses) == 2
    assert _terminal_result(responses)["eam"]["team_uid"] == CANONICAL_COLOR_TEAM_UIDS["ORANGE"]
    assert _terminal_result(responses)["eam"]["group_name"] == "ORANGE"


def test_eam_command_maps_missing_records_to_not_found(tmp_path) -> None:
    api, _domain, router = _router(tmp_path)
    api.grant_identity_capability("peer-a", "mission.registry.status.read")

    responses = router.handle_commands(
        [
            _command(
                "mission.registry.eam.get",
                {"callsign": "MISSING"},
                command_id="cmd-eam-missing",
            )
        ],
        source_identity="peer-a",
    )

    assert len(responses) == 2
    assert responses[1].fields[FIELD_RESULTS]["status"] == "rejected"
    assert responses[1].fields[FIELD_RESULTS]["reason_code"] == "not_found"
