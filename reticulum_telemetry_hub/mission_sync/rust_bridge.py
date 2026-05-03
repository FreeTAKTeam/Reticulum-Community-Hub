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
class RustMissionSyncBridge:
    """Invoke ``r3akt-rch-bridge`` for selected mission-sync commands."""

    binary_path: str
    db_path: str
    field_results: int
    field_event: int
    field_group: int
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

    def set_authorization_required(self, required: bool) -> None:
        """Enable or disable Rust-side capability enforcement."""

        self._expect_state_updated(
            self._request({"type": "set_authorization", "required": required})
        )

    def _request(self, request: dict[str, object]) -> dict[str, Any]:
        completed = self.runner(
            [self.binary_path, "--db", self.db_path],
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
    )
