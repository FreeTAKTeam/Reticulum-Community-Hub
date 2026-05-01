"""REM mission-change fanout helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

import uuid
from typing import Any

import LXMF
import RNS

from reticulum_telemetry_hub.message_delivery import utc_now_rfc3339
import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.mission_delta_markdown import MissionDeltaNameResolver
from reticulum_telemetry_hub.reticulum_server.mission_delta_markdown import render_mission_delta_markdown
from reticulum_telemetry_hub.reticulum_server.rem_checklist_commands import checklist_command_messages_for_mission_change
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeRemFanoutMixin:
    """REM mission-change fanout helpers."""

    def _render_generic_log_update_markdown(self, log_entry: dict[str, Any]) -> str:
        """Render a human-readable markdown summary for generic LXMF peers."""

        mission_uid = str(log_entry.get("mission_uid") or "").strip() or "unknown"
        callsign = str(log_entry.get("callsign") or "").strip() or "Unknown"
        content = str(log_entry.get("content") or "").strip() or "(empty)"
        return (
            "### Mission Log Update\n"
            f"Mission: {mission_uid}\n\n"
            f"From: {callsign}\n\n"
            f"{content}"
        )

    def _build_rem_log_event_fields(
        self,
        log_entry: dict[str, Any],
    ) -> dict[int | str, object]:
        """Build LXMF field-native mission log payloads for REM peers."""

        return {
            LXMF.FIELD_EVENT: {
                "event_type": "mission.registry.log_entry.upserted",
                "payload": dict(log_entry),
                "source": {"rns_identity": self._origin_rch_hex()},
            }
        }

    def _render_generic_eam_markdown(
        self,
        event_type: str,
        snapshot: dict[str, Any],
    ) -> str:
        """Render a human-readable emergency message summary for generic peers."""

        callsign = str(snapshot.get("callsign") or "").strip() or "Unknown"
        group_name = str(snapshot.get("group_name") or "").strip() or "Unknown"
        overall_status = str(snapshot.get("overall_status") or "Unknown").strip()
        notes = str(snapshot.get("notes") or "").strip()
        if event_type == "mission.registry.eam.deleted":
            return (
                "### Emergency Message Deleted\n"
                f"Callsign: {callsign}\n\n"
                f"Team: {group_name}"
            )
        body = (
            "### Emergency Message Updated\n"
            f"Callsign: {callsign}\n\n"
            f"Team: {group_name}\n\n"
            f"Overall: {overall_status}"
        )
        if notes:
            body += f"\n\nNotes: {notes}"
        return body

    def _build_rem_eam_command_fields(
        self,
        event_type: str,
        snapshot: dict[str, Any],
    ) -> dict[int | str, object]:
        """Build FIELD_COMMANDS payloads for REM EAM update delivery."""

        command_type = "mission.registry.eam.delete"
        args: dict[str, Any] = {"callsign": snapshot.get("callsign")}
        if event_type != "mission.registry.eam.deleted":
            command_type = "mission.registry.eam.upsert"
            args = dict(snapshot)
        return {
            LXMF.FIELD_COMMANDS: [
                {
                    "command_id": uuid.uuid4().hex,
                    "source": {"rns_identity": self._origin_rch_hex()},
                    "timestamp": utc_now_rfc3339(),
                    "command_type": command_type,
                    "args": args,
                }
            ]
        }

    def _fanout_log_update(self, log_entry: dict[str, Any]) -> None:
        """Deliver a mission log update according to REM connected-mode policy."""

        recipients = self._rem_fanout_recipients()
        if not recipients["rem"] and not recipients["generic"]:
            return
        concise_body = f"mission log update {log_entry.get('entry_uid') or ''}".strip()
        if recipients["rem"]:
            self.send_many(
                concise_body,
                recipients["rem"],
                fields=self._build_rem_log_event_fields(log_entry),
            )
        generic_fields = {MARKDOWN_RENDERER_FIELD: MARKDOWN_RENDERER_VALUE}
        markdown_body = self._render_generic_log_update_markdown(log_entry)
        if recipients["generic"]:
            self.send_many(
                markdown_body,
                recipients["generic"],
                fields=generic_fields,
            )

    def _handle_eam_status_update(
        self,
        event_type: str,
        snapshot: dict[str, Any],
    ) -> None:
        """Deliver EAM updates according to REM connected-mode policy."""

        recipients = self._rem_fanout_recipients()
        if not recipients["rem"] and not recipients["generic"]:
            return
        concise_body = f"eam update {snapshot.get('callsign') or ''}".strip()
        if recipients["rem"]:
            self.send_many(
                concise_body,
                recipients["rem"],
                fields=self._build_rem_eam_command_fields(event_type, snapshot),
            )
        generic_fields = {MARKDOWN_RENDERER_FIELD: MARKDOWN_RENDERER_VALUE}
        generic_body = self._render_generic_eam_markdown(event_type, snapshot)
        if recipients["generic"]:
            self.send_many(
                generic_body,
                recipients["generic"],
                fields=generic_fields,
            )

    def _fanout_mission_change_to_recipients(
        self, mission_change: dict[str, Any]
    ) -> None:
        if not isinstance(mission_change, dict):
            return
        mission_uid = str(
            mission_change.get("mission_uid")
            or mission_change.get("mission_id")
            or ""
        ).strip()
        mission_change_uid = str(mission_change.get("uid") or "").strip()
        if not mission_uid or not mission_change_uid:
            return
        if self._has_mission_change_been_fanned_out(mission_change_uid):
            return

        domain = getattr(self, "mission_domain_service", None)
        if domain is None:
            return
        try:
            destinations = domain.list_mission_team_member_identities(mission_uid)
        except (KeyError, ValueError):
            return
        if not destinations:
            return
        deduped_destinations = [
            value
            for value in dict.fromkeys(
                str(identity or "").strip().lower() for identity in destinations if identity
            )
            if value
        ]
        if not deduped_destinations:
            return

        delta = mission_change.get("delta")
        delta_payload = dict(delta) if isinstance(delta, dict) else {}
        source_event_type = str(delta_payload.get("source_event_type") or "").strip()
        if source_event_type == "mission.log_entry.upserted":
            log_items = delta_payload.get("logs")
            if isinstance(log_items, list) and log_items:
                first_log = log_items[0]
                if isinstance(first_log, dict):
                    self._fanout_log_update(dict(first_log))
                    self._mark_mission_change_fanned_out(mission_change_uid)
            return
        resolver = MissionDeltaNameResolver(domain)
        base_event_fields = {
            LXMF.FIELD_EVENT: self._build_mission_change_event_field(
                mission_uid=mission_uid,
                mission_change_uid=mission_change_uid,
                change_type=mission_change.get("change_type"),
            )
        }

        markdown_body = render_mission_delta_markdown(
            mission_uid=mission_uid,
            mission_change=mission_change,
            delta=delta_payload,
            resolver=resolver,
        )
        concise_body = (
            f"r3akt mission delta {mission_uid} {mission_change_uid}".strip()
        )
        rem_checklist_messages = checklist_command_messages_for_mission_change(
            mission_change,
            source_identity=self._origin_rch_hex(),
            source_display_name=getattr(self, "display_name", None),
            participant_rns_identities=deduped_destinations,
        )
        rem_connected_mode = False
        api = getattr(self, "api", None)
        if rem_checklist_messages and api is not None:
            try:
                rem_connected_mode = bool(api.effective_rem_connected_mode())
            except Exception as exc:  # pragma: no cover - defensive logging
                RNS.log(
                    f"Unable to resolve REM connected mode for checklist fanout: {exc}",
                    RNS.LOG_WARNING,
                )
                rem_connected_mode = False
        rem_checklist_destinations: list[str] = []
        r3akt_destinations: list[str] = []
        generic_destinations: list[str] = []
        for destination in deduped_destinations:
            if (
                rem_checklist_messages
                and rem_connected_mode
                and self._identity_is_rem(destination)
            ):
                rem_checklist_destinations.append(destination)
            elif self._identity_supports_r3akt(destination):
                r3akt_destinations.append(destination)
            else:
                generic_destinations.append(destination)

        if rem_checklist_destinations:
            for rem_message in rem_checklist_messages:
                self.send_many(
                    rem_message.body,
                    rem_checklist_destinations,
                    fields=rem_message.fields,
                )

        if r3akt_destinations:
            custom_fields = self._build_r3akt_delta_custom_fields(
                mission_uid=mission_uid,
                mission_change=mission_change,
                delta=delta_payload,
            )
            merged_fields = self._merge_standard_fields(
                source_fields=None,
                extra_fields={**base_event_fields, **custom_fields},
            )
            self.send_many(
                concise_body,
                r3akt_destinations,
                fields=merged_fields,
            )

        if generic_destinations:
            merged_fields = self._merge_standard_fields(
                source_fields=None,
                extra_fields={
                    **base_event_fields,
                    MARKDOWN_RENDERER_FIELD: MARKDOWN_RENDERER_VALUE,
                },
            )
            self.send_many(
                markdown_body,
                generic_destinations,
                fields=merged_fields,
            )

        self._mark_mission_change_fanned_out(mission_change_uid)

    def _fanout_mission_team_events(
        self,
        mission_replies: list[Any],
        *,
        source_fields: dict | None,
    ) -> None:
        if not mission_replies:
            return
        domain = getattr(self, "mission_domain_service", None)
        if domain is None:
            return
        for reply in mission_replies:
            fields = getattr(reply, "fields", None)
            if not isinstance(fields, dict):
                continue
            event_field = fields.get(LXMF.FIELD_EVENT)
            if not isinstance(event_field, dict):
                continue
            mission_uid = self._extract_mission_uid_from_response_fields(fields)
            if not mission_uid:
                continue
            try:
                destinations = domain.list_mission_team_member_identities(mission_uid)
            except (KeyError, ValueError):
                continue
            if not destinations:
                continue
            extra_fields = self._augment_r3akt_custom_fields(fields)
            outbound_fields = self._merge_standard_fields(
                source_fields=source_fields,
                extra_fields=extra_fields,
            )
            payload_text = f"r3akt mission event {event_field.get('event_type') or ''}".strip()
            explicit_destinations = [
                str(destination).strip().lower()
                for destination in destinations
                if destination
            ]
            if explicit_destinations:
                self.send_many(
                    payload_text,
                    explicit_destinations,
                    fields=outbound_fields,
                )

