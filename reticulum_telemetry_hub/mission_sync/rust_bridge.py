"""Optional subprocess bridge to the Rust R3AKT RCH core."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any
from typing import Callable

from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope


Runner = Callable[..., subprocess.CompletedProcess[str]]
DEFAULT_RUST_RUNTIME_DB_FILENAME = "r3akt-rch-core.sqlite"


class RustMissionBridgeError(RuntimeError):
    """Raised when the Rust bridge cannot execute a command."""


@dataclass(frozen=True)
class RustMissionSyncBridgeResponse:
    """Mission-sync response returned by the Rust bridge."""

    content: str
    fields: dict[int | str, object]


@dataclass(frozen=True)
class RustMissionSyncTopic:
    """Topic state returned by the Rust RCH bridge."""

    topic_id: str
    topic_name: str
    topic_path: str
    payload: dict[str, object]


@dataclass(frozen=True)
class RustMissionSyncSubscriber:
    """Subscriber state returned by the Rust RCH bridge."""

    node_id: str
    topic_id: str
    payload: dict[str, object]


@dataclass(frozen=True)
class RustMissionSyncMarker:
    """Marker state returned by the Rust RCH bridge."""

    object_destination_hash: str
    name: str
    payload: dict[str, object]


@dataclass(frozen=True)
class RustMissionSyncZone:
    """Zone state returned by the Rust RCH bridge."""

    zone_id: str
    name: str
    payload: dict[str, object]


@dataclass(frozen=True)
class RustMissionSyncBridge:
    """Invoke ``r3akt-rch-bridge`` for selected mission-sync commands."""

    binary_path: str
    db_path: str
    field_results: int
    field_event: int
    field_group: int
    reticulumd_rpc_endpoint: str | None = None
    runner: Runner = subprocess.run

    def handle_command(
        self,
        envelope: MissionCommandEnvelope,
        *,
        group: object | None = None,
        source_identity: str | None = None,
    ) -> list[RustMissionSyncBridgeResponse]:
        """Execute one mission command through the Rust RCH bridge."""

        request = {
            "type": "mission_command",
            "command": envelope.model_dump(mode="json"),
        }
        if source_identity is not None:
            request["source_identity"] = source_identity
        payload = self._request(request)
        if payload.get("type") != "mission_command":
            raise RustMissionBridgeError("Rust bridge returned an unexpected response type")
        responses = payload.get("responses")
        if not isinstance(responses, list):
            raise RustMissionBridgeError("Rust bridge response is missing responses[]")
        return [
            RustMissionSyncBridgeResponse(
                content=str(response.get("content") or "mission-sync"),
                fields=self._normalize_fields(response.get("fields"), group=group),
            )
            for response in responses
            if isinstance(response, dict)
        ]

    def handle_checklist_command(
        self,
        envelope: MissionCommandEnvelope,
        *,
        group: object | None = None,
        source_identity: str | None = None,
    ) -> list[RustMissionSyncBridgeResponse]:
        """Execute one checklist-sync command through the Rust RCH bridge."""

        request = {
            "type": "checklist_command",
            "command": envelope.model_dump(mode="json"),
        }
        if source_identity is not None:
            request["source_identity"] = source_identity
        payload = self._request(request)
        if payload.get("type") != "checklist_command":
            raise RustMissionBridgeError("Rust bridge returned an unexpected response type")
        responses = payload.get("responses")
        if not isinstance(responses, list):
            raise RustMissionBridgeError("Rust bridge response is missing responses[]")
        return [
            RustMissionSyncBridgeResponse(
                content=str(response.get("content") or "mission-sync"),
                fields=self._normalize_fields(response.get("fields"), group=group),
            )
            for response in responses
            if isinstance(response, dict)
        ]

    def list_topics(self) -> list[RustMissionSyncTopic]:
        """Return topics currently persisted in the Rust RCH bridge state."""

        payload = self._request({"type": "list_topics"})
        if payload.get("type") != "list_topics":
            raise RustMissionBridgeError("Rust bridge returned an unexpected response type")
        topics = payload.get("topics")
        if not isinstance(topics, list):
            raise RustMissionBridgeError("Rust bridge response is missing topics[]")
        return [
            RustMissionSyncTopic(
                topic_id=str(topic.get("topic_id") or ""),
                topic_name=str(topic.get("topic_name") or ""),
                topic_path=str(topic.get("topic_path") or ""),
                payload=dict(topic),
            )
            for topic in topics
            if isinstance(topic, dict)
        ]

    def list_subscribers(self) -> list[RustMissionSyncSubscriber]:
        """Return subscribers currently persisted in the Rust RCH bridge state."""

        payload = self._request({"type": "list_subscribers"})
        if payload.get("type") != "list_subscribers":
            raise RustMissionBridgeError("Rust bridge returned an unexpected response type")
        subscribers = payload.get("subscribers")
        if not isinstance(subscribers, list):
            raise RustMissionBridgeError("Rust bridge response is missing subscribers[]")
        return [
            RustMissionSyncSubscriber(
                node_id=str(subscriber.get("node_id") or ""),
                topic_id=str(subscriber.get("topic_id") or ""),
                payload=dict(subscriber),
            )
            for subscriber in subscribers
            if isinstance(subscriber, dict)
        ]

    def list_markers(self) -> list[RustMissionSyncMarker]:
        """Return markers currently persisted in the Rust RCH bridge state."""

        payload = self._request({"type": "list_markers"})
        if payload.get("type") != "list_markers":
            raise RustMissionBridgeError("Rust bridge returned an unexpected response type")
        markers = payload.get("markers")
        if not isinstance(markers, list):
            raise RustMissionBridgeError("Rust bridge response is missing markers[]")
        return [
            RustMissionSyncMarker(
                object_destination_hash=str(marker.get("object_destination_hash") or ""),
                name=str(marker.get("name") or ""),
                payload=dict(marker),
            )
            for marker in markers
            if isinstance(marker, dict)
        ]

    def list_zones(self) -> list[RustMissionSyncZone]:
        """Return zones currently persisted in the Rust RCH bridge state."""

        payload = self._request({"type": "list_zones"})
        if payload.get("type") != "list_zones":
            raise RustMissionBridgeError("Rust bridge returned an unexpected response type")
        zones = payload.get("zones")
        if not isinstance(zones, list):
            raise RustMissionBridgeError("Rust bridge response is missing zones[]")
        return [
            RustMissionSyncZone(
                zone_id=str(zone.get("zone_id") or ""),
                name=str(zone.get("name") or ""),
                payload=dict(zone),
            )
            for zone in zones
            if isinstance(zone, dict)
        ]

    def state_snapshot(self) -> dict[str, object]:
        """Return the full Rust RCH bridge state snapshot."""

        payload = self._request({"type": "state_snapshot"})
        if payload.get("type") != "state_snapshot":
            raise RustMissionBridgeError("Rust bridge returned an unexpected response type")
        snapshot = payload.get("snapshot")
        if not isinstance(snapshot, dict):
            raise RustMissionBridgeError("Rust bridge response is missing snapshot{}")
        return snapshot

    def grant_capability(self, identity: str, capability: str) -> None:
        """Grant one Rust-side mission-sync capability to an identity."""

        self._expect_state_updated(
            self._request(
                {
                    "type": "grant_capability",
                    "identity": identity,
                    "capability": capability,
                }
            )
        )

    def revoke_capability(self, identity: str, capability: str) -> None:
        """Revoke one Rust-side mission-sync capability from an identity."""

        self._expect_state_updated(
            self._request(
                {
                    "type": "revoke_capability",
                    "identity": identity,
                    "capability": capability,
                }
            )
        )

    def record_identity_announce(
        self,
        identity: str,
        *,
        announced_identity_hash: str | None = None,
        display_name: str | None = None,
        source_interface: str | None = None,
        announce_capabilities: object = None,
    ) -> None:
        """Persist one Rust-side identity announce record."""

        capabilities: list[str]
        if isinstance(announce_capabilities, str):
            capabilities = [
                item.strip()
                for item in announce_capabilities.split(",")
                if item.strip()
            ]
        elif isinstance(announce_capabilities, list):
            capabilities = [str(item) for item in announce_capabilities if str(item).strip()]
        else:
            capabilities = []
        self._expect_state_updated(
            self._request(
                {
                    "type": "record_identity_announce",
                    "identity": identity,
                    "announced_identity_hash": announced_identity_hash,
                    "display_name": display_name,
                    "source_interface": source_interface,
                    "announce_capabilities": capabilities,
                }
            )
        )

    def set_identity_state(
        self,
        identity: str,
        *,
        is_banned: bool,
        is_blackholed: bool,
    ) -> None:
        """Persist one Rust-side identity moderation state."""

        self._expect_state_updated(
            self._request(
                {
                    "type": "set_identity_state",
                    "identity": identity,
                    "is_banned": is_banned,
                    "is_blackholed": is_blackholed,
                }
            )
        )

    def set_rem_mode(self, identity: str, mode: str) -> None:
        """Persist one Rust-side REM operating mode."""

        self._expect_state_updated(
            self._request(
                {
                    "type": "set_rem_mode",
                    "identity": identity,
                    "mode": mode,
                }
            )
        )

    def assign_mission_access_role(
        self,
        mission_uid: str,
        subject_type: str,
        subject_id: str,
        role: str,
    ) -> None:
        """Assign one Rust-side mission access role."""

        self._expect_state_updated(
            self._request(
                {
                    "type": "assign_mission_access_role",
                    "mission_uid": mission_uid,
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "role": role,
                }
            )
        )

    def grant_operation_right(
        self,
        subject_type: str,
        subject_id: str,
        operation: str,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> None:
        """Grant one Rust-side subject operation right."""

        self._expect_state_updated(
            self._request(
                {
                    "type": "grant_operation_right",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "operation": operation,
                    "scope_type": scope_type or "global",
                    "scope_id": scope_id or "",
                }
            )
        )

    def revoke_operation_right(
        self,
        subject_type: str,
        subject_id: str,
        operation: str,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> None:
        """Revoke one Rust-side subject operation right."""

        self._expect_state_updated(
            self._request(
                {
                    "type": "revoke_operation_right",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "operation": operation,
                    "scope_type": scope_type or "global",
                    "scope_id": scope_id or "",
                }
            )
        )

    def set_authorization_required(self, required: bool) -> None:
        """Enable or disable Rust-side capability enforcement."""

        self._expect_state_updated(
            self._request({"type": "set_authorization", "required": required})
        )

    def send_outbound(
        self,
        *,
        message_id: str,
        source: str,
        destination: str,
        title: str,
        content: str,
        fields: dict | None,
        method: str,
    ) -> dict[str, Any]:
        """Send one outbound LXMF payload through the Rust Reticulum bridge."""

        if not self.reticulumd_rpc_endpoint:
            raise RustMissionBridgeError("Rust outbound bridge requires reticulumd RPC endpoint")
        request = {
            "type": "outbound_send",
            "message_id": message_id,
            "source": source,
            "destination": destination,
            "title": title,
            "content": content,
            "fields": self._stringify_field_keys(fields),
            "method": method,
        }
        payload = self._request(request)
        if payload.get("type") != "outbound_send" or payload.get("ok") is not True:
            raise RustMissionBridgeError("Rust bridge did not confirm outbound send")
        return payload

    def _request(self, request: dict[str, object]) -> dict[str, Any]:
        command = [self.binary_path, "--db", self.db_path]
        if request.get("type") == "outbound_send" and self.reticulumd_rpc_endpoint:
            command.extend(["--reticulumd-rpc", self.reticulumd_rpc_endpoint])
        completed = self.runner(
            command,
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RustMissionBridgeError(completed.stderr.strip() or "Rust bridge failed")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RustMissionBridgeError("Rust bridge returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RustMissionBridgeError("Rust bridge returned a non-object response")
        return payload

    @staticmethod
    def _expect_state_updated(payload: dict[str, Any]) -> None:
        if payload.get("type") != "state_updated" or payload.get("ok") is not True:
            raise RustMissionBridgeError("Rust bridge did not confirm state update")

    def _normalize_fields(
        self,
        fields: object,
        *,
        group: object | None,
    ) -> dict[int | str, object]:
        if not isinstance(fields, dict):
            raise RustMissionBridgeError("Rust bridge response fields must be an object")
        normalized: dict[int | str, object] = {}
        for raw_key, value in fields.items():
            key: int | str
            if str(raw_key).isdigit():
                key = int(str(raw_key))
            else:
                key = str(raw_key)
            normalized[key] = value
        if group is not None:
            normalized[self.field_group] = group
        if self.field_results not in normalized:
            raise RustMissionBridgeError("Rust bridge response missing FIELD_RESULTS")
        return normalized

    @staticmethod
    def _stringify_field_keys(fields: dict | None) -> dict[str, object] | None:
        if fields is None:
            return None
        return {str(key): value for key, value in fields.items()}


def build_rust_bridge_from_runtime_config(
    runtime_config: Any,
    *,
    storage_path: Path,
    field_results: int,
    field_event: int,
    field_group: int,
) -> RustMissionSyncBridge | None:
    """Build the optional Rust mission-sync bridge from hub runtime config."""

    if not bool(getattr(runtime_config, "rust_runtime_enabled", False)):
        return None
    bridge_path = getattr(runtime_config, "rust_runtime_bridge_path", None)
    if bridge_path is None:
        return None
    db_path = getattr(runtime_config, "rust_runtime_db_path", None)
    if db_path is None:
        db_path = Path(storage_path) / DEFAULT_RUST_RUNTIME_DB_FILENAME
    return RustMissionSyncBridge(
        binary_path=str(bridge_path),
        db_path=str(db_path),
        field_results=field_results,
        field_event=field_event,
        field_group=field_group,
        reticulumd_rpc_endpoint=getattr(
            runtime_config,
            "rust_runtime_reticulumd_rpc_endpoint",
            None,
        ),
    )
