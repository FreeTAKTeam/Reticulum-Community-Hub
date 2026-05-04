import threading
from datetime import datetime
from datetime import timezone
from pathlib import Path
import subprocess
import uuid

import pytest
from sqlalchemy.exc import OperationalError

from reticulum_telemetry_hub.api import Client
from reticulum_telemetry_hub.api import IdentityStatus
from reticulum_telemetry_hub.api import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api import ReticulumInfo
from reticulum_telemetry_hub.api import Subscriber
from reticulum_telemetry_hub.api import Topic
from reticulum_telemetry_hub.api.storage import TopicRecord
from reticulum_telemetry_hub.api.storage_models import IdentityAnnounceRecord
from reticulum_telemetry_hub.api.storage_models import IdentityCapabilityGrantRecord
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.mission_sync.rust_bridge import RustMissionSyncBridge
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope
from reticulum_telemetry_hub.api.rights_policy import MISSION_ROLE_BUNDLES
from reticulum_telemetry_hub.api.rights_policy import SUPPORTED_OPERATIONS


FIELD_RESULTS = 10
FIELD_GROUP = 11
FIELD_EVENT = 13


class RustRightsApi:
    """Static rights metadata exposed through the Rust-backed API adapter."""

    @staticmethod
    def operation_definitions() -> dict[str, object]:
        return {
            "subject_types": ["identity", "team_member"],
            "scope_types": ["global", "mission"],
            "operations": list(SUPPORTED_OPERATIONS),
            "mission_role_bundles": {
                role: sorted(operations)
                for role, operations in sorted(MISSION_ROLE_BUNDLES.items())
            },
        }


def make_config_manager(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "config.ini").write_text(
        "[app]\n"
        "name = TestHub\n"
        "version = 9.9.9\n"
        "description = Test hub instance\n"
    )
    reticulum_cfg = tmp_path / "reticulum.ini"
    reticulum_cfg.write_text(
        "[reticulum]\n"
        "enable_transport = true\n"
        "share_instance = yes\n"
        "[interfaces]\n"
        "listen_ip = 127.0.0.1\n"
        "listen_port = 9999\n"
    )
    lxmf_cfg = tmp_path / "lxmf.ini"
    lxmf_cfg.write_text(
        "[propagation]\n"
        "enable_node = yes\n"
        "announce_interval = 5\n"
        "[lxmf]\n"
        "display_name = TestRouter\n"
    )
    return HubConfigurationManager(
        storage_path=storage,
        reticulum_config_path=reticulum_cfg,
        lxmf_router_config_path=lxmf_cfg,
    )


class RustTopicSubscriberApi:
    """Minimal ReticulumTelemetryHubAPI topic/subscriber subset backed by Rust."""

    def __init__(self, tmp_path: Path) -> None:
        self._tmp_path = tmp_path
        self._storage_path = tmp_path / "storage"
        self._storage_path.mkdir(exist_ok=True)
        self._reticulum_destination: str | None = None
        self._bridge = _bridge(tmp_path / "r3akt-api.sqlite")
        self.rights = RustRightsApi()

    def create_topic(self, topic: Topic) -> Topic:
        self._command(
            "topic.create",
            {
                "topic_name": topic.topic_name,
                "topic_path": topic.topic_path,
                "topic_description": topic.topic_description,
            },
        )
        return self.retrieve_topic(topic.topic_path)

    def get_app_info(self) -> ReticulumInfo:
        return ReticulumInfo(
            is_transport_enabled=True,
            is_connected_to_shared_instance=True,
            reticulum_config_path=str(self._tmp_path / "reticulum.ini"),
            database_path=str(self._storage_path / "hub.sqlite"),
            storage_path=str(self._storage_path),
            file_storage_path=str(self._storage_path / "files"),
            image_storage_path=str(self._storage_path / "images"),
            app_name="TestHub",
            rns_version="test-rns",
            lxmf_version="test-lxmf",
            app_version="9.9.9",
            app_description="Test hub instance",
            reticulum_destination=self._reticulum_destination,
        )

    def set_reticulum_destination(self, destination: str | None) -> None:
        if destination is None:
            self._reticulum_destination = None
            return
        cleaned = destination.strip()
        if not cleaned:
            self._reticulum_destination = None
            return
        if any(char not in "0123456789abcdefABCDEF" for char in cleaned):
            raise ValueError("destination must be a hex string")
        if len(cleaned) % 2 != 0:
            raise ValueError("destination must contain an even number of hex characters")
        self._reticulum_destination = cleaned.lower()

    def retrieve_topic(self, topic_id: str | None) -> Topic:
        for topic in self.list_topics():
            if topic.topic_id == topic_id:
                return topic
        raise KeyError(f"Topic '{topic_id}' not found")

    def patch_topic(
        self,
        topic_id: str | None,
        *,
        topic_name: str | None = None,
        topic_path: str | None = None,
        topic_description: str | None = None,
    ) -> Topic:
        result = self._command(
            "topic.patch",
            {
                "topic_id": topic_id,
                "topic_name": topic_name,
                "topic_path": topic_path,
                "topic_description": topic_description,
            },
        )
        return _topic_from_payload(result)

    def list_topics(self) -> list[Topic]:
        return [_topic_from_payload(topic.payload) for topic in self._bridge.list_topics()]

    def delete_topic(self, topic_id: str | None) -> Topic:
        result = self._command("topic.delete", {"topic_id": topic_id})
        return _topic_from_payload(result)

    def subscribe_topic(
        self,
        topic_id: str | None,
        *,
        destination: str,
        reject_tests: int | None = None,
        metadata: dict | None = None,
    ) -> Subscriber:
        result = self._command(
            "topic.subscribe",
            {
                "topic_id": topic_id,
                "destination": destination,
                "reject_tests": reject_tests,
                "metadata": metadata or {},
            },
        )
        return Subscriber(
            destination=str(result.get("subscriber_id") or result.get("Destination") or ""),
            topic_id=str(result.get("topic_id") or result.get("TopicID") or ""),
            reject_tests=result.get("reject_tests")
            if isinstance(result.get("reject_tests"), int)
            else None,
            metadata=metadata or {},
            subscriber_id=str(result.get("subscriber_id") or result.get("Destination") or ""),
        )

    def create_subscriber(self, subscriber: Subscriber) -> Subscriber:
        if not subscriber.destination:
            raise ValueError("Subscriber destination is required")
        result = self._command(
            "topic.subscribe",
            {
                "topic_id": subscriber.topic_id,
                "destination": subscriber.destination,
                "reject_tests": subscriber.reject_tests,
                "metadata": subscriber.metadata or {},
            },
        )
        return _subscriber_from_payload(result)

    def retrieve_subscriber(self, subscriber_id: str | None) -> Subscriber:
        for subscriber in self.list_subscribers():
            if subscriber.subscriber_id == subscriber_id:
                return subscriber
        raise KeyError(f"Subscriber '{subscriber_id}' not found")

    def patch_subscriber(
        self,
        subscriber_id: str | None,
        *,
        destination: str | None = None,
        topic_id: str | None = None,
        reject_tests: int | None = None,
        metadata: dict | None = None,
        **extra: object,
    ) -> Subscriber:
        if metadata is None and isinstance(extra.get("Metadata"), dict):
            metadata = extra["Metadata"]
        result = self._command(
            "topic.subscriber.patch",
            {
                "subscriber_id": subscriber_id,
                "destination": destination,
                "topic_id": topic_id,
                "reject_tests": reject_tests,
                "metadata": metadata,
            },
        )
        return _subscriber_from_payload(result)

    def list_subscribers(self) -> list[Subscriber]:
        return [
            _subscriber_from_payload(subscriber.payload)
            for subscriber in self._bridge.list_subscribers()
        ]

    def delete_subscriber(self, subscriber_id: str | None) -> Subscriber:
        result = self._command("topic.subscriber.delete", {"subscriber_id": subscriber_id})
        return _subscriber_from_payload(result)

    def join(self, identity: str) -> bool:
        self._command("mission.join", {}, source_identity=identity)
        return True

    def leave(self, identity: str) -> bool:
        self._command("mission.leave", {}, source_identity=identity)
        return True

    def list_clients(self) -> list[Client]:
        snapshot = self._bridge.state_snapshot()
        clients = snapshot.get("clients")
        assert isinstance(clients, list)
        announces = _identity_announces_by_identity(snapshot)
        records: list[Client] = []
        for client in clients:
            if not isinstance(client, dict):
                continue
            identity = str(client.get("identity") or "")
            announce = announces.get(identity.lower())
            display_name = _announce_display_name(announce)
            metadata = {"display_name": display_name} if display_name else {}
            records.append(
                Client(
                    identity=identity,
                    display_name=display_name,
                    metadata=metadata,
                    client_type=str(
                        (announce or {}).get("client_type") or "generic_lxmf"
                    ),
                    announce_capabilities=_announce_capabilities(announce),
                    rem_mode=_rem_mode_for_identity(snapshot, identity)
                    if str((announce or {}).get("client_type") or "generic_lxmf") == "rem"
                    else None,
                    is_rem_capable=str(
                        (announce or {}).get("client_type") or "generic_lxmf"
                    )
                    == "rem",
                )
            )
        return records

    def record_identity_announce(
        self,
        identity: str,
        *,
        announced_identity_hash: str | None = None,
        display_name: str | None = None,
        source_interface: str | None = None,
        announce_capabilities: object = None,
    ) -> None:
        self._bridge.record_identity_announce(
            identity,
            announced_identity_hash=announced_identity_hash,
            display_name=display_name,
            source_interface=source_interface,
            announce_capabilities=announce_capabilities,
        )

    def resolve_identity_display_name(self, identity: str) -> str | None:
        announces = _identity_announces_by_identity(self._bridge.state_snapshot())
        return _announce_display_name(announces.get(identity.lower()))

    def resolve_identity_display_names_bulk(
        self, identities: list[str]
    ) -> dict[str, str | None]:
        announces = _identity_announces_by_identity(self._bridge.state_snapshot())
        return {
            identity: _announce_display_name(announces.get(identity.lower()))
            for identity in identities
        }

    def ban_identity(self, identity: str) -> IdentityStatus:
        self._bridge.set_identity_state(
            identity, is_banned=True, is_blackholed=False
        )
        return self._identity_status(identity)

    def unban_identity(self, identity: str) -> IdentityStatus:
        state = _identity_states_by_identity(self._bridge.state_snapshot()).get(
            identity.lower(), {}
        )
        if state.get("is_blackholed"):
            return self._identity_status(identity)
        self._bridge.set_identity_state(
            identity, is_banned=False, is_blackholed=False
        )
        return self._identity_status(identity)

    def blackhole_identity(self, identity: str) -> IdentityStatus:
        self._bridge.set_identity_state(
            identity, is_banned=False, is_blackholed=True
        )
        return self._identity_status(identity)

    def get_rem_mode(self, identity: str) -> str:
        return _rem_mode_for_identity(self._bridge.state_snapshot(), identity)

    def set_rem_mode(self, identity: str, mode: str) -> dict[str, object]:
        self._bridge.set_rem_mode(identity, mode)
        snapshot = self._bridge.state_snapshot()
        return {
            "identity": identity.lower(),
            "mode": _rem_mode_for_identity(snapshot, identity),
            "effective_connected_mode": self.effective_rem_connected_mode(),
        }

    def effective_rem_connected_mode(self) -> bool:
        return any(
            str(mode.get("mode") or "").lower() == "connected"
            for mode in _identity_rem_modes(self._bridge.state_snapshot()).values()
        )

    def rem_peer_registry(self) -> dict[str, object]:
        snapshot = self._bridge.state_snapshot()
        states = _identity_states_by_identity(snapshot)
        candidates: dict[str, dict[str, object]] = {}
        for announce in _raw_identity_announces(snapshot):
            identity = str(
                announce.get("announced_identity_hash")
                or announce.get("destination_hash")
                or ""
            ).lower()
            if not identity or str(announce.get("client_type") or "") != "rem":
                continue
            existing = candidates.get(identity)
            if existing is None or str(announce.get("source_interface") or "") == "destination":
                candidates[identity] = _merge_announce_records(
                    announce,
                    _identity_announces_by_identity(snapshot).get(identity),
                )
        peers: list[dict[str, object]] = []
        for identity, announce in sorted(candidates.items()):
            state = states.get(identity, {})
            if state.get("is_banned") or state.get("is_blackholed"):
                continue
            peers.append(
                {
                    "identity": identity,
                    "destination_hash": str(
                        announce.get("destination_hash") or identity
                    ),
                    "display_name": _announce_display_name(announce),
                    "announce_capabilities": _announce_capabilities(announce),
                    "client_type": "rem",
                    "registered_mode": _rem_mode_for_identity(snapshot, identity),
                    "status": "active",
                }
            )
        return {
            "effective_connected_mode": self.effective_rem_connected_mode(),
            "items": peers,
        }

    def list_identity_statuses(self) -> list[IdentityStatus]:
        snapshot = self._bridge.state_snapshot()
        states = _identity_states_by_identity(snapshot)
        clients = {client.identity.lower(): client for client in self.list_clients()}
        announces = _identity_announces_by_identity(snapshot)
        identities = sorted(set(states) | set(clients) | set(announces))
        statuses = [
            self._identity_status(
                clients[identity].identity if identity in clients else identity,
                snapshot=snapshot,
            )
            for identity in identities
        ]
        return _dedupe_identity_statuses(statuses, client_keys=set(clients))

    def _identity_status(
        self, identity: str, *, snapshot: dict[str, object] | None = None
    ) -> IdentityStatus:
        snapshot = snapshot or self._bridge.state_snapshot()
        normalized = identity.lower()
        state = _identity_states_by_identity(snapshot).get(normalized, {})
        announce = _identity_announces_by_identity(snapshot).get(normalized)
        display_name = _announce_display_name(announce)
        is_banned = bool(state.get("is_banned"))
        is_blackholed = bool(state.get("is_blackholed"))
        status = "blackholed" if is_blackholed else "banned" if is_banned else "inactive"
        return IdentityStatus(
            identity=identity,
            status=status,
            display_name=display_name,
            metadata={"display_name": display_name} if display_name else {},
            is_banned=is_banned,
            is_blackholed=is_blackholed,
            client_type=str((announce or {}).get("client_type") or "generic_lxmf"),
            announce_capabilities=_announce_capabilities(announce),
            rem_mode=_rem_mode_for_identity(snapshot, identity)
            if str((announce or {}).get("client_type") or "generic_lxmf") == "rem"
            else None,
            is_rem_capable=str((announce or {}).get("client_type") or "generic_lxmf")
            == "rem",
        )

    def list_identity_capabilities(self, identity: str) -> list[str]:
        normalized = identity.lower()
        grants = self._bridge.state_snapshot().get("identity_capabilities")
        assert isinstance(grants, list)
        return sorted(
            str(grant.get("capability"))
            for grant in grants
            if isinstance(grant, dict)
            and str(grant.get("identity") or "").lower() == normalized
            and grant.get("capability")
        )

    def grant_identity_capability(
        self, identity: str, capability: str
    ) -> dict[str, object]:
        self._bridge.grant_capability(identity, capability)
        return {"identity": identity, "capability": capability, "granted": True}

    def revoke_identity_capability(
        self, identity: str, capability: str
    ) -> dict[str, object]:
        self._bridge.revoke_capability(identity, capability)
        return {"identity": identity, "capability": capability, "granted": False}

    def _command(
        self,
        command_type: str,
        args: dict[str, object],
        *,
        source_identity: str = "peer-a",
    ) -> dict[str, object]:
        responses = self._bridge.handle_command(
            MissionCommandEnvelope.model_validate(
                {
                    "command_id": f"cmd-rust-api-{command_type}",
                    "source": {"rns_identity": source_identity},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "command_type": command_type,
                    "args": args,
                }
            ),
            source_identity=source_identity,
        )
        payload = responses[-1].fields[FIELD_RESULTS]
        if not isinstance(payload, dict):
            raise RuntimeError(f"Rust command returned malformed payload: {command_type}")
        if payload.get("status") == "rejected":
            reason_code = str(payload.get("reason_code") or "")
            reason = str(payload.get("reason") or payload.get("detail") or command_type)
            if reason_code in {"not_found", "not_found_error"} or "not found" in reason:
                raise KeyError(reason)
            raise ValueError(reason)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"Rust command returned non-object result: {command_type}")
        return result


def _api(tmp_path: Path, backend: str) -> ReticulumTelemetryHubAPI | RustTopicSubscriberApi:
    if backend == "rust":
        return RustTopicSubscriberApi(tmp_path)
    return ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))


def _runtime_root() -> Path:
    candidates = [
        Path(__file__).resolve().parents[3] / "New project" / "R3AKT-Runtime",
        Path(r"C:\Users\broth\Documents\New project\R3AKT-Runtime"),
    ]
    for candidate in candidates:
        if (candidate / "Cargo.toml").exists():
            return candidate
    pytest.fail("R3AKT-Runtime workspace not found for Rust API parity tests")


def _bridge(db_path: Path) -> RustMissionSyncBridge:
    runtime_root = _runtime_root()

    def runner(args, **kwargs):  # type: ignore[no-untyped-def]
        request_db_path = args[args.index("--db") + 1]
        return subprocess.run(
            ["cargo", "run", "-q", "-p", "r3akt-rch-bridge", "--", "--db", request_db_path],
            cwd=runtime_root,
            input=kwargs["input"],
            text=True,
            capture_output=True,
            check=False,
        )

    return RustMissionSyncBridge(
        binary_path="cargo-run-r3akt-rch-bridge",
        db_path=str(db_path),
        field_results=FIELD_RESULTS,
        field_event=FIELD_EVENT,
        field_group=FIELD_GROUP,
        runner=runner,
    )


def _topic_from_payload(payload: dict[str, object]) -> Topic:
    return Topic(
        topic_id=str(payload.get("topic_id") or payload.get("TopicID") or ""),
        topic_name=str(payload.get("topic_name") or payload.get("TopicName") or ""),
        topic_path=str(payload.get("topic_path") or payload.get("TopicPath") or ""),
        topic_description=str(
            payload.get("topic_description") or payload.get("TopicDescription") or ""
        ),
    )


def _subscriber_from_payload(payload: dict[str, object]) -> Subscriber:
    return Subscriber(
        destination=str(
            payload.get("destination")
            or payload.get("Destination")
            or payload.get("node_id")
            or payload.get("subscriber_id")
            or ""
        ),
        topic_id=str(payload.get("topic_id") or payload.get("TopicID") or ""),
        reject_tests=payload.get("reject_tests")
        if isinstance(payload.get("reject_tests"), int)
        else payload.get("RejectTests")
        if isinstance(payload.get("RejectTests"), int)
        else None,
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        subscriber_id=str(
            payload.get("subscriber_id")
            or payload.get("SubscriberID")
            or payload.get("node_id")
            or payload.get("destination")
            or ""
        ),
    )


def _identity_announces_by_identity(
    snapshot: dict[str, object],
) -> dict[str, dict[str, object]]:
    records = _raw_identity_announces(snapshot)
    by_destination = {
        str(record.get("destination_hash") or "").lower(): record
        for record in records
        if record.get("destination_hash")
    }
    result: dict[str, dict[str, object]] = {}
    for record in records:
        destination = str(record.get("destination_hash") or "").lower()
        announced = str(record.get("announced_identity_hash") or "").lower()
        canonical = by_destination.get(announced)
        display_record = _merge_announce_records(record, canonical)
        if destination:
            result[destination] = display_record
        if announced:
            existing = result.get(announced)
            if existing is None or _announce_prefer(display_record, existing):
                result[announced] = display_record
    return result


def _raw_identity_announces(snapshot: dict[str, object]) -> list[dict[str, object]]:
    announces = snapshot.get("identity_announces")
    assert isinstance(announces, list)
    return [dict(record) for record in announces if isinstance(record, dict)]


def _merge_announce_records(
    record: dict[str, object],
    canonical: dict[str, object] | None,
) -> dict[str, object]:
    if not canonical:
        return record
    merged = dict(record)
    if not _announce_display_name(merged) and _announce_display_name(canonical):
        merged["display_name"] = canonical["display_name"]
    if str(merged.get("client_type") or "generic_lxmf") != "rem" and str(
        canonical.get("client_type") or "generic_lxmf"
    ) == "rem":
        merged["client_type"] = "rem"
        merged["announce_capabilities"] = canonical.get("announce_capabilities") or []
    return merged


def _announce_prefer(
    candidate: dict[str, object],
    existing: dict[str, object],
) -> bool:
    if str(candidate.get("client_type") or "") == "rem" and str(
        existing.get("client_type") or ""
    ) != "rem":
        return True
    return bool(_announce_display_name(candidate)) and not _announce_display_name(existing)


def _identity_states_by_identity(snapshot: dict[str, object]) -> dict[str, dict[str, object]]:
    states = snapshot.get("identity_states")
    assert isinstance(states, list)
    return {
        str(state.get("identity") or "").lower(): dict(state)
        for state in states
        if isinstance(state, dict) and state.get("identity")
    }


def _identity_rem_modes(snapshot: dict[str, object]) -> dict[str, dict[str, object]]:
    modes = snapshot.get("identity_rem_modes")
    assert isinstance(modes, list)
    return {
        str(mode.get("identity") or "").lower(): dict(mode)
        for mode in modes
        if isinstance(mode, dict) and mode.get("identity")
    }


def _rem_mode_for_identity(snapshot: dict[str, object], identity: str) -> str:
    mode = _identity_rem_modes(snapshot).get(identity.lower(), {}).get("mode")
    return str(mode or "autonomous").lower()


def _announce_display_name(announce: dict[str, object] | None) -> str | None:
    if not announce:
        return None
    display_name = announce.get("display_name")
    return str(display_name) if display_name else None


def _announce_capabilities(announce: dict[str, object] | None) -> list[str]:
    if not announce:
        return []
    capabilities = announce.get("announce_capabilities")
    if not isinstance(capabilities, list):
        return []
    return [str(capability) for capability in capabilities]


def _dedupe_identity_statuses(
    statuses: list[IdentityStatus],
    *,
    client_keys: set[str],
) -> list[IdentityStatus]:
    results: dict[tuple[str, str], IdentityStatus] = {}
    for status in statuses:
        key = (
            "display",
            status.display_name.lower(),
        ) if status.display_name else ("identity", status.identity.lower())
        existing = results.get(key)
        if existing is None or (
            status.identity.lower() in client_keys
            and existing.identity.lower() not in client_keys
        ):
            results[key] = status
    return list(results.values())


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_topic_crud(tmp_path, backend):
    api = _api(tmp_path, backend)
    topic = api.create_topic(Topic(topic_name="Status", topic_path="/status"))
    assert topic.topic_id
    assert api.retrieve_topic(topic.topic_id).topic_name == "Status"
    updated = api.patch_topic(topic.topic_id, topic_description="System status")
    assert updated.topic_description == "System status"
    topics = api.list_topics()
    assert len(topics) == 1
    deleted = api.delete_topic(topic.topic_id)
    assert deleted.topic_id == topic.topic_id


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_patch_topic_allows_clearing_description(tmp_path, backend):
    api = _api(tmp_path, backend)
    topic = api.create_topic(
        Topic(
            topic_name="Status", topic_path="/status", topic_description="System status"
        )
    )

    api.patch_topic(topic.topic_id, topic_description="")
    updated = api.retrieve_topic(topic.topic_id)

    assert updated.topic_description == ""


def test_assign_attachment_to_topic_updates_existing_record(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Status", topic_path="/status"))
    file_path = api._config_manager.config.file_storage_path / "linked.txt"  # pylint: disable=protected-access
    file_path.write_text("linked")
    image_path = api._config_manager.config.image_storage_path / "linked.jpg"  # pylint: disable=protected-access
    image_path.write_bytes(b"image")

    file_record = api.store_file(file_path, media_type="text/plain")
    image_record = api.store_image(image_path, media_type="image/jpeg")

    updated_file = api.assign_file_to_topic(file_record.file_id, topic.topic_id)
    updated_image = api.assign_image_to_topic(image_record.file_id, topic.topic_id)

    assert updated_file.topic_id == topic.topic_id
    assert updated_image.topic_id == topic.topic_id
    assert api.retrieve_file(file_record.file_id).topic_id == topic.topic_id
    assert api.retrieve_image(image_record.file_id).topic_id == topic.topic_id


def test_assign_attachment_to_topic_allows_clearing_association(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Status", topic_path="/status"))
    file_path = api._config_manager.config.file_storage_path / "clear.txt"  # pylint: disable=protected-access
    file_path.write_text("linked")
    file_record = api.store_file(file_path, media_type="text/plain", topic_id=topic.topic_id)

    updated_file = api.assign_file_to_topic(file_record.file_id, "")

    assert updated_file.topic_id is None
    assert api.retrieve_file(file_record.file_id).topic_id is None


def test_delete_topic_clears_attachment_associations(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Status", topic_path="/status"))
    file_path = api._config_manager.config.file_storage_path / "delete-linked.txt"  # pylint: disable=protected-access
    file_path.write_text("linked")
    file_record = api.store_file(file_path, media_type="text/plain", topic_id=topic.topic_id)

    api.delete_topic(topic.topic_id)

    assert api.retrieve_file(file_record.file_id).topic_id is None


def test_delete_topic_clears_legacy_raw_attachment_associations(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Status", topic_path="/status"))
    raw_topic_id = f" {str(uuid.UUID(topic.topic_id)).upper()} "
    file_path = api._config_manager.config.file_storage_path / "delete-legacy-linked.txt"  # pylint: disable=protected-access
    file_path.write_text("linked")
    file_record = api.store_file(file_path, media_type="text/plain", topic_id=raw_topic_id)

    assert api.retrieve_file(file_record.file_id).topic_id == raw_topic_id

    api.delete_topic(topic.topic_id)

    assert api.retrieve_file(file_record.file_id).topic_id is None


def test_delete_topic_preserves_case_distinct_attachment_associations(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(
        Topic(topic_id="Ops", topic_name="Operations", topic_path="/ops")
    )
    file_path = api._config_manager.config.file_storage_path / "case-linked.txt"  # pylint: disable=protected-access
    file_path.write_text("linked")
    file_record = api.store_file(file_path, media_type="text/plain", topic_id="ops")

    api.delete_topic(topic.topic_id)

    assert api.retrieve_file(file_record.file_id).topic_id == "ops"


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_subscriber_management(tmp_path, backend):
    api = _api(tmp_path, backend)
    topic = api.create_topic(Topic(topic_name="Alerts", topic_path="/alerts"))
    subscriber = api.subscribe_topic(topic.topic_id, destination="abc123")
    assert subscriber.subscriber_id
    retrieved = api.retrieve_subscriber(subscriber.subscriber_id)
    assert retrieved.destination == "abc123"
    api.patch_subscriber(subscriber.subscriber_id, metadata={"level": "high"})
    assert api.retrieve_subscriber(subscriber.subscriber_id).metadata == {
        "level": "high"
    }
    api.patch_subscriber(subscriber.subscriber_id, metadata={})
    assert api.retrieve_subscriber(subscriber.subscriber_id).metadata == {}
    all_subs = api.list_subscribers()
    assert len(all_subs) == 1
    api.delete_subscriber(subscriber.subscriber_id)
    assert api.list_subscribers() == []


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_patch_subscriber_allows_zero_reject_tests(tmp_path, backend):
    api = _api(tmp_path, backend)
    topic = api.create_topic(Topic(topic_name="Zero", topic_path="/zero"))
    subscriber = api.subscribe_topic(
        topic.topic_id, destination="abc123", reject_tests=3
    )

    api.patch_subscriber(subscriber.subscriber_id, reject_tests=0)
    updated = api.retrieve_subscriber(subscriber.subscriber_id)

    assert updated.reject_tests == 0


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_client_join_leave(tmp_path, backend):
    api = _api(tmp_path, backend)
    assert api.join("identity1")
    assert len(api.list_clients()) == 1
    assert api.leave("identity1")
    assert api.list_clients() == []


def test_concurrent_client_join_and_leave(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))

    worker_count = 20
    iterations = 4
    barrier = threading.Barrier(worker_count)
    errors: list[Exception] = []

    def worker(idx: int):
        identity = f"identity-{idx}"
        try:
            barrier.wait()
            for _ in range(iterations):
                api.join(identity)
            if idx % 2 == 0:
                api.leave(identity)
        except Exception as exc:  # pragma: no cover - defensive capture
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(worker_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    expected_clients = worker_count // 2
    assert len(api.list_clients()) == expected_clients


def test_storage_session_retries_close_failed_sessions(tmp_path, monkeypatch):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    storage = api._storage
    storage._session_retries = 2
    storage._session_backoff = 0

    closed_sessions: list[bool] = []

    class FailingSession:
        def execute(self, _):
            raise OperationalError("SELECT 1", {}, Exception("locked"))

        def close(self):
            closed_sessions.append(True)

    monkeypatch.setattr(storage, "_session_factory", lambda: FailingSession())

    with pytest.raises(OperationalError):
        storage._acquire_session_with_retry()

    assert len(closed_sessions) == storage._session_retries


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_get_app_info(tmp_path, backend):
    api = _api(tmp_path, backend)
    info = api.get_app_info()
    assert info.storage_path.endswith("storage")
    assert info.file_storage_path.endswith("files")
    assert info.image_storage_path.endswith("images")
    assert info.app_name == "TestHub"
    assert info.app_version == "9.9.9"
    assert info.app_description == "Test hub instance"
    assert info.reticulum_destination is None


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_get_app_info_includes_reticulum_destination(tmp_path, backend):
    api = _api(tmp_path, backend)

    api.set_reticulum_destination("DeAdBeEf")

    info = api.get_app_info()

    assert info.reticulum_destination == "deadbeef"


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_reticulum_destination_clears_on_blank_value(tmp_path, backend):
    api = _api(tmp_path, backend)

    api.set_reticulum_destination("deadbeef")
    api.set_reticulum_destination(" ")

    info = api.get_app_info()

    assert info.reticulum_destination is None


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_reticulum_destination_clears_on_none(tmp_path, backend):
    api = _api(tmp_path, backend)

    api.set_reticulum_destination("deadbeef")
    api.set_reticulum_destination(None)

    info = api.get_app_info()

    assert info.reticulum_destination is None


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_reticulum_destination_rejects_non_hex(tmp_path, backend):
    api = _api(tmp_path, backend)

    with pytest.raises(ValueError):
        api.set_reticulum_destination("not-hex")


def test_config_apply_and_rollback(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))

    new_config = "[app]\nname = UpdatedHub\n"
    apply_result = api.apply_config_text(new_config)
    assert apply_result["applied"]

    current = api.get_config_text()
    assert "UpdatedHub" in current

    rollback_result = api.rollback_config_text()
    assert rollback_result["rolled_back"]


def test_config_apply_rejects_invalid_payload(tmp_path):
    """Reject invalid config payloads without overwriting the current file."""

    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    original = api.get_config_text()

    with pytest.raises(ValueError) as exc_info:
        api.apply_config_text("hub]\nname = Broken\n")

    assert "Invalid configuration payload" in str(exc_info.value)
    assert api.get_config_text() == original


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_identity_status_crud(tmp_path, backend):
    api = _api(tmp_path, backend)
    api.join("identity-1")
    banned = api.ban_identity("identity-1")
    assert banned.is_banned

    blackholed = api.blackhole_identity("identity-2")
    assert blackholed.is_blackholed

    statuses = api.list_identity_statuses()
    identity_map = {status.identity: status for status in statuses}
    assert identity_map["identity-1"].status == "banned"
    assert identity_map["identity-2"].status == "blackholed"


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_persistence_between_instances(tmp_path, backend):
    cfg = make_config_manager(tmp_path)
    api1 = (
        RustTopicSubscriberApi(tmp_path)
        if backend == "rust"
        else ReticulumTelemetryHubAPI(config_manager=cfg)
    )
    topic = api1.create_topic(Topic(topic_name="Ops", topic_path="/ops"))
    api1.join("identity42")
    api1.record_identity_announce("identity42", display_name="Sideband-Alice")

    # Recreate API with same configuration/DB path
    api2 = (
        RustTopicSubscriberApi(tmp_path)
        if backend == "rust"
        else ReticulumTelemetryHubAPI(config_manager=cfg)
    )
    assert api2.retrieve_topic(topic.topic_id).topic_name == "Ops"
    clients = api2.list_clients()
    assert any(c.identity == "identity42" and c.display_name == "Sideband-Alice" for c in clients)
    assert api2.resolve_identity_display_name("identity42") == "Sideband-Alice"


def test_patch_topic_preserves_created_at(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Status", topic_path="/status"))

    with api._storage._Session() as session:
        original_record = session.get(TopicRecord, topic.topic_id)
        original_created_at = original_record.created_at

    api.patch_topic(topic.topic_id, topic_description="Updated status")

    with api._storage._Session() as session:
        updated_record = session.get(TopicRecord, topic.topic_id)
        assert updated_record.description == "Updated status"
        assert updated_record.created_at == original_created_at


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_join_and_leave_require_identity(tmp_path, backend):
    api = _api(tmp_path, backend)

    with pytest.raises(ValueError):
        api.join("")

    with pytest.raises(ValueError):
        api.leave("")


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_identity_announce_merges_display_name(tmp_path, backend):
    api = _api(tmp_path, backend)
    api.record_identity_announce(
        "deadbeef",
        display_name="Sideband-Alice",
        announce_capabilities=["R3AKT", "EMergencyMessages"],
    )
    api.join("deadbeef")
    api.set_rem_mode("deadbeef", "semi_autonomous")

    clients = api.list_clients()
    assert len(clients) == 1
    client = clients[0]
    assert client.display_name == "Sideband-Alice"
    assert client.metadata.get("display_name") == "Sideband-Alice"
    assert client.client_type == "rem"
    assert client.announce_capabilities == ["r3akt", "emergencymessages"]
    assert client.rem_mode == "semi_autonomous"
    assert client.is_rem_capable is True

    statuses = api.list_identity_statuses()
    status = next(item for item in statuses if item.identity == "deadbeef")
    assert status.display_name == "Sideband-Alice"
    assert status.metadata.get("display_name") == "Sideband-Alice"
    assert status.client_type == "rem"
    assert status.rem_mode == "semi_autonomous"
    assert status.is_rem_capable is True


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_rem_mode_and_peer_registry_persist_between_instances(tmp_path, backend):
    cfg = make_config_manager(tmp_path)
    api1 = (
        RustTopicSubscriberApi(tmp_path)
        if backend == "rust"
        else ReticulumTelemetryHubAPI(config_manager=cfg)
    )
    api1.record_identity_announce(
        "deadbeef-destination",
        announced_identity_hash="deadbeef",
        display_name="REM Alpha",
        source_interface="destination",
        announce_capabilities="R3AKT,EMergencyMessages,Telemetry",
    )
    api1.record_identity_announce(
        "deadbeef",
        announced_identity_hash="deadbeef",
        display_name="REM Alpha",
        source_interface="identity",
        announce_capabilities="R3AKT,EMergencyMessages,Telemetry",
    )
    api1.record_identity_announce(
        "cafebabe",
        display_name="Generic Bravo",
        source_interface="identity",
        announce_capabilities=["telemetry"],
    )
    api1.set_rem_mode("deadbeef", "connected")

    api2 = (
        RustTopicSubscriberApi(tmp_path)
        if backend == "rust"
        else ReticulumTelemetryHubAPI(config_manager=cfg)
    )
    payload = api2.rem_peer_registry()

    assert api2.get_rem_mode("deadbeef") == "connected"
    assert api2.effective_rem_connected_mode() is True
    assert payload["effective_connected_mode"] is True
    assert len(payload["items"]) == 1
    assert payload["items"][0]["identity"] == "deadbeef"
    assert payload["items"][0]["destination_hash"] == "deadbeef-destination"
    assert payload["items"][0]["client_type"] == "rem"
    assert payload["items"][0]["registered_mode"] == "connected"


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_generic_clients_do_not_report_rem_mode(tmp_path, backend):
    api = _api(tmp_path, backend)
    api.record_identity_announce(
        "cafebabe",
        display_name="Generic Bravo",
        source_interface="identity",
        announce_capabilities=["telemetry"],
    )
    api.join("cafebabe")

    client = next(item for item in api.list_clients() if item.identity == "cafebabe")
    status = next(item for item in api.list_identity_statuses() if item.identity == "cafebabe")

    assert client.client_type == "generic_lxmf"
    assert client.rem_mode is None
    assert client.is_rem_capable is False
    assert status.client_type == "generic_lxmf"
    assert status.rem_mode is None
    assert status.is_rem_capable is False


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_delivery_announce_display_name_does_not_strip_rem_classification(tmp_path, backend):
    api = _api(tmp_path, backend)
    api.record_identity_announce(
        "pixel-app-destination",
        announced_identity_hash="0a92e053b7e6ba49f0a045e9cc55eaa2",
        source_interface="destination",
        announce_capabilities="R3AKT,EMergencyMessages,Telemetry",
    )
    api.record_identity_announce(
        "0a92e053b7e6ba49f0a045e9cc55eaa2",
        announced_identity_hash="0a92e053b7e6ba49f0a045e9cc55eaa2",
        display_name="Pixel",
        source_interface="identity",
    )

    status = next(
        item
        for item in api.list_identity_statuses()
        if item.identity == "0a92e053b7e6ba49f0a045e9cc55eaa2"
    )

    assert status.display_name == "Pixel"
    assert status.client_type == "rem"
    assert status.is_rem_capable is True
    assert "r3akt" in status.announce_capabilities
    assert "emergencymessages" in status.announce_capabilities


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_identity_announce_ignores_missing_name(tmp_path, backend):
    api = _api(tmp_path, backend)
    api.record_identity_announce("deadbeef", display_name="Sideband-Alice")
    api.record_identity_announce("deadbeef", display_name=None)

    assert api.resolve_identity_display_name("deadbeef") == "Sideband-Alice"


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_resolve_identity_display_names_bulk(tmp_path, backend):
    """Ensure bulk identity display-name resolution returns merged announce view."""

    api = _api(tmp_path, backend)
    api.record_identity_announce("deadbeef-destination", announced_identity_hash="deadbeef")
    api.record_identity_announce("deadbeef", display_name="Sideband-Alice")

    resolved = api.resolve_identity_display_names_bulk(
        ["deadbeef", "deadbeef-destination", "missing"]
    )

    assert resolved["deadbeef"] == "Sideband-Alice"
    assert resolved["deadbeef-destination"] == "Sideband-Alice"
    assert resolved["missing"] is None


def test_identity_announce_concurrent_upserts_do_not_duplicate_records(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    errors: list[Exception] = []

    def _record(display_name: str) -> None:
        try:
            api.record_identity_announce("deadbeef", display_name=display_name)
        except Exception as exc:  # pragma: no cover - defensive capture
            errors.append(exc)

    threads = [
        threading.Thread(target=_record, args=("Sideband-Alice",), daemon=True)
        for _ in range(10)
    ] + [
        threading.Thread(target=_record, args=("Sideband-Bob",), daemon=True)
        for _ in range(10)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert api.resolve_identity_display_name("deadbeef") in {
        "Sideband-Alice",
        "Sideband-Bob",
    }
    records = [
        record
        for record in api._storage.list_identity_announces()
        if record.destination_hash == "deadbeef"
    ]
    assert len(records) == 1


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_identity_statuses_dedupe_case_insensitive(tmp_path, backend):
    api = _api(tmp_path, backend)
    api.join("DeAdBeEf")
    api.record_identity_announce("deadbeef", display_name="Sideband-Alice")

    statuses = api.list_identity_statuses()

    matches = [status for status in statuses if status.identity.lower() == "deadbeef"]
    assert len(matches) == 1
    assert matches[0].identity == "DeAdBeEf"
    assert matches[0].display_name == "Sideband-Alice"


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_identity_statuses_dedupe_with_announce_only(tmp_path, backend):
    api = _api(tmp_path, backend)
    api.record_identity_announce("deadbeef", display_name="Sideband-Alice")

    statuses = api.list_identity_statuses()

    matches = [status for status in statuses if status.identity.lower() == "deadbeef"]
    assert len(matches) == 1
    assert matches[0].identity == "deadbeef"


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_identity_statuses_dedupe_preserves_blackhole(tmp_path, backend):
    api = _api(tmp_path, backend)
    api.blackhole_identity("deadbeef")
    api.unban_identity("DEADBEEF")

    statuses = api.list_identity_statuses()

    match = next(status for status in statuses if status.identity.lower() == "deadbeef")
    assert match.is_blackholed
    assert match.status == "blackholed"


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_identity_statuses_dedupe_display_name_collapses_duplicates(tmp_path, backend):
    api = _api(tmp_path, backend)
    api.record_identity_announce("deadbeef", display_name="Sideband-Alice")
    api.record_identity_announce("cafebabe", display_name="Sideband-Alice")

    if backend == "python":
        now = datetime.now(timezone.utc)
        with api._storage._Session() as session:
            records = session.query(IdentityAnnounceRecord).all()
            for record in records:
                record.last_seen = now
            session.commit()

    statuses = api.list_identity_statuses()

    matches = [status for status in statuses if status.display_name == "Sideband-Alice"]
    assert len(matches) == 1


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_identity_statuses_dedupe_prefers_joined_identity(tmp_path, backend):
    api = _api(tmp_path, backend)
    api.record_identity_announce("deadbeef", display_name="Sideband-Alice")
    api.record_identity_announce("cafebabe", display_name="Sideband-Alice")
    api.join("deadbeef")

    if backend == "python":
        now = datetime.now(timezone.utc)
        with api._storage._Session() as session:
            records = session.query(IdentityAnnounceRecord).all()
            for record in records:
                record.last_seen = now
            session.commit()

    statuses = api.list_identity_statuses()

    match = next(status for status in statuses if status.display_name == "Sideband-Alice")
    assert match.identity == "deadbeef"


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_identity_capability_grants_round_trip(tmp_path, backend):
    api = _api(tmp_path, backend)

    assert api.list_identity_capabilities("deadbeef") == []

    granted = api.grant_identity_capability("deadbeef", "mission.join")
    assert granted["identity"] == "deadbeef"
    assert granted["capability"] == "mission.join"
    assert granted["granted"] is True

    assert api.list_identity_capabilities("deadbeef") == ["mission.join"]

    revoked = api.revoke_identity_capability("deadbeef", "mission.join")
    assert revoked["granted"] is False
    assert api.list_identity_capabilities("deadbeef") == []


def test_subject_rights_backfill_legacy_identity_capabilities(tmp_path):
    cfg = make_config_manager(tmp_path)
    api = ReticulumTelemetryHubAPI(config_manager=cfg)

    with api._storage._Session() as session:
        session.add(
            IdentityCapabilityGrantRecord(
                grant_uid=uuid.uuid4().hex,
                identity="legacy-peer",
                capability="mission.join",
                granted=True,
            )
        )
        session.commit()

    reloaded_api = ReticulumTelemetryHubAPI(config_manager=cfg)

    assert reloaded_api.list_identity_capabilities("legacy-peer") == ["mission.join"]
    grants = reloaded_api.list_capability_grants(identity="legacy-peer")
    assert grants[0]["capability"] == "mission.join"


def test_mission_access_roles_grant_effective_operations(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    domain = MissionDomainService(api._config_manager.config.hub_database_path)  # pylint: disable=protected-access

    domain.upsert_mission({"uid": "mission-1", "mission_name": "Mission One"})
    domain.upsert_team({"uid": "team-1", "team_name": "Ops", "mission_uid": "mission-1"})
    domain.upsert_team_member(
        {
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "peer-a",
            "display_name": "Peer A",
        }
    )

    api.assign_mission_access_role(
        "mission-1",
        "team_member",
        "member-1",
        role="MISSION_SUBSCRIBER",
    )

    assert api.authorize("peer-a", "mission.message.send", mission_uid="mission-1") is True
    assert api.authorize("peer-a", "mission.registry.status.read", mission_uid="mission-1") is True
    assert api.authorize("peer-a", "mission.registry.status.write", mission_uid="mission-1") is True
    assert api.authorize("peer-a", "topic.delete", mission_uid="mission-1") is False


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_operation_definitions_include_status_rights_and_bundles(tmp_path, backend):
    api = _api(tmp_path, backend)

    definitions = api.rights.operation_definitions()

    assert "mission.registry.status.read" in definitions["operations"]
    assert "mission.registry.status.write" in definitions["operations"]
    assert "mission.registry.status.read" in definitions["mission_role_bundles"]["MISSION_READONLY_SUBSCRIBER"]
    assert "mission.registry.status.write" in definitions["mission_role_bundles"]["MISSION_SUBSCRIBER"]
    assert "mission.registry.status.write" in definitions["mission_role_bundles"]["MISSION_OWNER"]


def test_explicit_revoke_overrides_mission_access_bundle(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    domain = MissionDomainService(api._config_manager.config.hub_database_path)  # pylint: disable=protected-access

    domain.upsert_mission({"uid": "mission-1", "mission_name": "Mission One"})
    domain.upsert_team({"uid": "team-1", "team_name": "Ops", "mission_uid": "mission-1"})
    domain.upsert_team_member(
        {
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "peer-member",
            "display_name": "Peer Member",
        }
    )
    domain.link_team_member_client("member-1", "peer-client")

    api.assign_mission_access_role(
        "mission-1",
        "team_member",
        "member-1",
        role="MISSION_SUBSCRIBER",
    )
    assert api.authorize("peer-client", "mission.message.send", mission_uid="mission-1") is True

    api.revoke_operation_right(
        "team_member",
        "member-1",
        "mission.message.send",
        scope_type="mission",
        scope_id="mission-1",
    )

    assert api.authorize("peer-client", "mission.message.send", mission_uid="mission-1") is False


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_create_topic_requires_fields(tmp_path, backend):
    api = _api(tmp_path, backend)

    with pytest.raises(ValueError):
        api.create_topic(Topic(topic_name="", topic_path=""))


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_topic_operations_raise_when_missing(tmp_path, backend):
    api = _api(tmp_path, backend)

    with pytest.raises(KeyError):
        api.retrieve_topic("missing")

    with pytest.raises(KeyError):
        api.delete_topic("missing")


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_patch_topic_without_updates_returns_original(tmp_path, backend):
    api = _api(tmp_path, backend)
    topic = api.create_topic(Topic(topic_name="Status", topic_path="/status"))

    returned = api.patch_topic(topic.topic_id)

    assert returned.topic_id == topic.topic_id


def test_patch_topic_raises_when_storage_returns_none(tmp_path, monkeypatch):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Status", topic_path="/status"))

    monkeypatch.setattr(api._storage, "update_topic", lambda *_args, **_kwargs: None)

    with pytest.raises(KeyError):
        api.patch_topic(topic.topic_id, topic_name="New Name")


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_create_subscriber_requires_destination(tmp_path, backend):
    api = _api(tmp_path, backend)

    with pytest.raises(ValueError):
        api.create_subscriber(Subscriber(destination=""))


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_subscriber_operations_raise_when_missing(tmp_path, backend):
    api = _api(tmp_path, backend)

    with pytest.raises(KeyError):
        api.retrieve_subscriber("unknown")

    with pytest.raises(KeyError):
        api.delete_subscriber("unknown")


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_patch_subscriber_accepts_metadata_with_title_case(tmp_path, backend):
    api = _api(tmp_path, backend)
    topic = api.create_topic(Topic(topic_name="Alerts", topic_path="/alerts"))
    subscriber = api.subscribe_topic(topic.topic_id, destination="dest")

    api.patch_subscriber(subscriber.subscriber_id, Metadata={"priority": "high"})
    updated = api.retrieve_subscriber(subscriber.subscriber_id)

    assert updated.metadata == {"priority": "high"}
