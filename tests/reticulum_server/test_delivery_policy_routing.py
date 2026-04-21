from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
import threading
from types import SimpleNamespace

from reticulum_telemetry_hub.reticulum_server import __main__ as hub_module
from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub
from reticulum_telemetry_hub.reticulum_server.delivery_policy import (
    OutboundDeliveryPolicy,
)
from reticulum_telemetry_hub.reticulum_server.message_router import MessageRouter


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _connection(identity_hex: str, destination_hex: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        hash=bytes.fromhex(destination_hex or identity_hex),
        identity=SimpleNamespace(hash=bytes.fromhex(identity_hex)),
    )


class _ApiStub:
    def __init__(self) -> None:
        self.announce_last_seen: dict[str, datetime] = {}
        self.destination_hashes: dict[str, str] = {}

    def resolve_identity_announce_last_seen(self, identity: str) -> datetime | None:
        return self.announce_last_seen.get(identity)

    def resolve_identity_destination_hash(self, identity: str) -> str | None:
        return self.destination_hashes.get(identity)


class _HubStub:
    def __init__(self, connection_ids: list[str]) -> None:
        self.api = _ApiStub()
        self.connections = {bytes.fromhex(identity): _connection(identity) for identity in connection_ids}
        self.my_lxmf_dest = object()
        self.outbound_backoff = 0.5
        self.outbound_fanout_soft_max_recipients = 0
        self.outbound_delivery_policy = OutboundDeliveryPolicy(self)

    @staticmethod
    def _connection_hex(connection: SimpleNamespace) -> str:
        return connection.identity.hash.hex()

    @staticmethod
    def _subscribers_for_topic(topic_id: str | None) -> None:
        return None

    @staticmethod
    def _cached_destination(identity: str) -> None:
        return None

    @staticmethod
    def _ensure_reachable_identity_destination(identity: str) -> None:
        return None


def test_targeted_payload_uses_direct_when_runtime_presence_is_fresh() -> None:
    identity = "11" * 16
    hub = _HubStub([identity])
    hub.outbound_delivery_policy.mark_presence(identity)
    router = MessageRouter(hub)

    payloads, metrics = router.build_outbound_payloads(
        message="ping",
        route_type="targeted",
        topic_id=None,
        destination=identity,
        exclude=None,
        fields=None,
        sender=None,
        chat_message_id="chat-1",
        message_id="msg-1",
    )

    assert len(payloads) == 1
    assert payloads[0].delivery_mode == "direct"
    assert payloads[0].delivery_policy_reason == "fresh_presence"
    assert metrics["selected_direct_recipient_count"] == 1
    assert metrics["selected_propagated_recipient_count"] == 0


def test_targeted_payload_uses_direct_when_recent_announce_exists() -> None:
    identity = "22" * 16
    hub = _HubStub([identity])
    hub.api.announce_last_seen[identity] = _utcnow() - timedelta(minutes=30)
    router = MessageRouter(hub)

    payloads, metrics = router.build_outbound_payloads(
        message="ping",
        route_type="targeted",
        topic_id=None,
        destination=identity,
        exclude=None,
        fields=None,
        sender=None,
        chat_message_id="chat-2",
        message_id="msg-2",
    )

    assert payloads[0].delivery_mode == "direct"
    assert payloads[0].delivery_policy_reason == "fresh_presence"
    assert metrics["selected_direct_recipient_count"] == 1


def test_targeted_payload_uses_propagated_for_startup_loaded_cold_recipient() -> None:
    identity = "33" * 16
    hub = _HubStub([identity])
    router = MessageRouter(hub)

    payloads, metrics = router.build_outbound_payloads(
        message="ping",
        route_type="targeted",
        topic_id=None,
        destination=identity,
        exclude=None,
        fields=None,
        sender=None,
        chat_message_id="chat-3",
        message_id="msg-3",
    )

    assert payloads[0].delivery_mode == "propagated"
    assert payloads[0].delivery_policy_reason == "no_fresh_presence"
    assert metrics["selected_propagated_recipient_count"] == 1
    assert metrics["delivery_policy_reason_counts"] == {"no_fresh_presence": 1}


def test_targeted_payload_queues_recalled_cold_recipient_as_propagated() -> None:
    identity = "34" * 16
    destination_hash = "43" * 16
    hub = _HubStub([])
    cached: dict[str, SimpleNamespace] = {}

    def _cached_destination(key: str) -> SimpleNamespace | None:
        return cached.get(key)

    def _ensure_reachable_identity_destination(key: str) -> None:
        cached[key] = _connection(key, destination_hash)

    hub._cached_destination = _cached_destination
    hub._ensure_reachable_identity_destination = _ensure_reachable_identity_destination
    router = MessageRouter(hub)

    payloads, metrics = router.build_outbound_payloads(
        message="ping",
        route_type="targeted",
        topic_id=None,
        destination=identity,
        exclude=None,
        fields=None,
        sender=None,
        chat_message_id="chat-3b",
        message_id="msg-3b",
    )

    assert len(payloads) == 1
    assert payloads[0].delivery_mode == "propagated"
    assert payloads[0].delivery_policy_reason == "no_fresh_presence"
    assert payloads[0].destination_hash.hex() == destination_hash
    assert metrics["selected_propagated_recipient_count"] == 1


def test_targeted_payload_stays_propagated_until_fresh_presence_clears_cooldown() -> None:
    identity = "44" * 16
    hub = _HubStub([identity])
    router = MessageRouter(hub)
    earlier = _utcnow() - timedelta(minutes=5)
    later = _utcnow()

    hub.api.announce_last_seen[identity] = earlier
    hub.outbound_delivery_policy.mark_direct_failure(identity, failed_at=earlier + timedelta(minutes=1))
    cooled_payloads, _ = router.build_outbound_payloads(
        message="ping",
        route_type="targeted",
        topic_id=None,
        destination=identity,
        exclude=None,
        fields=None,
        sender=None,
        chat_message_id="chat-4",
        message_id="msg-4",
    )

    hub.api.announce_last_seen[identity] = later
    fresh_payloads, _ = router.build_outbound_payloads(
        message="ping",
        route_type="targeted",
        topic_id=None,
        destination=identity,
        exclude=None,
        fields=None,
        sender=None,
        chat_message_id="chat-5",
        message_id="msg-5",
    )

    assert cooled_payloads[0].delivery_mode == "propagated"
    assert cooled_payloads[0].delivery_policy_reason == "direct_cooldown"
    assert fresh_payloads[0].delivery_mode == "direct"
    assert fresh_payloads[0].delivery_policy_reason == "fresh_presence"


def test_stale_presence_callback_evidence_expires_back_to_propagated() -> None:
    identity = "45" * 16
    stale = _utcnow() - timedelta(hours=2)
    hub = _HubStub([identity])
    hub.api.announce_last_seen[identity] = stale
    hub.outbound_delivery_policy.mark_presence(identity, observed_at=stale)
    router = MessageRouter(hub)

    payloads, metrics = router.build_outbound_payloads(
        message="ping",
        route_type="targeted",
        topic_id=None,
        destination=identity,
        exclude=None,
        fields=None,
        sender=None,
        chat_message_id="chat-5b",
        message_id="msg-5b",
    )

    assert payloads[0].delivery_mode == "propagated"
    assert payloads[0].delivery_policy_reason == "no_fresh_presence"
    assert metrics["selected_propagated_recipient_count"] == 1


def test_fanout_payload_queues_recalled_cold_topic_subscriber_as_propagated() -> None:
    identity = "54" * 16
    destination_hash = "45" * 16
    hub = _HubStub([])
    cached: dict[str, SimpleNamespace] = {}

    def _cached_destination(key: str) -> SimpleNamespace | None:
        return cached.get(key)

    def _ensure_reachable_identity_destination(key: str) -> None:
        cached[key] = _connection(key, destination_hash)

    hub._cached_destination = _cached_destination
    hub._ensure_reachable_identity_destination = _ensure_reachable_identity_destination
    hub._subscribers_for_topic = lambda topic_id: {identity}
    router = MessageRouter(hub)

    payloads, metrics = router.build_outbound_payloads(
        message="fanout",
        route_type="fanout",
        topic_id="Ops.Bravo",
        destination=None,
        exclude=None,
        fields=None,
        sender=None,
        chat_message_id="chat-5c",
        message_id="msg-5c",
    )

    assert len(payloads) == 1
    assert payloads[0].delivery_mode == "propagated"
    assert payloads[0].delivery_policy_reason == "fanout_route"
    assert payloads[0].destination_hex == identity
    assert payloads[0].destination_hash.hex() == destination_hash
    assert metrics["selected_propagated_recipient_count"] == 1


def test_fanout_and_broadcast_always_use_propagation_first() -> None:
    identity = "55" * 16
    hub = _HubStub([identity])
    hub.outbound_delivery_policy.mark_presence(identity)
    hub.api.announce_last_seen[identity] = _utcnow()
    router = MessageRouter(hub)

    fanout_payloads, fanout_metrics = router.build_outbound_payloads(
        message="fanout",
        route_type="fanout",
        topic_id="Ops.Alpha",
        destination=None,
        exclude=None,
        fields=None,
        sender=None,
        chat_message_id="chat-6",
        message_id="msg-6",
    )
    broadcast_payloads, broadcast_metrics = router.build_outbound_payloads(
        message="broadcast",
        route_type="broadcast",
        topic_id=None,
        destination=None,
        exclude=None,
        fields=None,
        sender=None,
        chat_message_id="chat-7",
        message_id="msg-7",
    )

    assert fanout_payloads[0].delivery_mode == "propagated"
    assert fanout_payloads[0].delivery_policy_reason == "fanout_route"
    assert fanout_metrics["selected_propagated_recipient_count"] == 1
    assert broadcast_payloads[0].delivery_mode == "propagated"
    assert broadcast_payloads[0].delivery_policy_reason == "broadcast_route"
    assert broadcast_metrics["selected_propagated_recipient_count"] == 1


def test_send_many_applies_propagation_policy_and_new_route_metrics() -> None:
    identity = "66" * 16
    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    recorded_metrics: dict[str, object] = {}
    queued_payloads: list[object] = []

    class _QueueStub:
        @staticmethod
        def queue_messages(payloads: list[object]) -> list[bool]:
            queued_payloads.extend(payloads)
            return [True for _ in payloads]

        @staticmethod
        def stats() -> dict[str, int]:
            return {
                "queue_depth": 1,
                "active_dispatches": 0,
                "pending_receipts": 0,
            }

    class _MetricsStub:
        @staticmethod
        def increment(name: str, value: int) -> None:
            return None

    hub.outbound_delivery_policy = OutboundDeliveryPolicy(SimpleNamespace(api=_ApiStub()))
    hub.my_lxmf_dest = object()
    hub._ensure_outbound_queue = lambda: _QueueStub()
    hub._cached_destination = lambda key: _connection(key)
    hub._ensure_reachable_identity_destination = lambda identity: None
    hub._delivery_message_id = lambda fields, chat_message_id=None: "msg-send-many"
    hub._prepare_outbound_delivery_fields = lambda **kwargs: {}
    hub._runtime_metrics_store = lambda: _MetricsStub()
    hub.message_router = SimpleNamespace(
        record_outbound_route_metrics=lambda **kwargs: recorded_metrics.update(kwargs)
    )

    result = ReticulumTelemetryHub.send_many(
        hub,
        "fanout",
        [identity],
        fields={},
        chat_message_id="chat-send-many",
    )

    assert result is True
    assert len(queued_payloads) == 1
    assert queued_payloads[0].delivery_mode == "propagated"
    assert queued_payloads[0].delivery_policy_reason == "fanout_route"
    assert recorded_metrics["selected_direct_recipient_count"] == 0
    assert recorded_metrics["selected_propagated_recipient_count"] == 1
    assert recorded_metrics["delivery_policy_reason_counts"] == {"fanout_route": 1}


def test_send_many_queues_offline_identity_when_announce_destination_is_known(
    monkeypatch,
) -> None:
    identity = "77" * 16
    destination_hash = "88" * 16
    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    recorded_metrics: dict[str, object] = {}
    queued_payloads: list[object] = []
    api = _ApiStub()
    api.destination_hashes[identity] = destination_hash

    class _QueueStub:
        @staticmethod
        def queue_messages(payloads: list[object]) -> list[bool]:
            queued_payloads.extend(payloads)
            return [True for _ in payloads]

        @staticmethod
        def stats() -> dict[str, int]:
            return {
                "queue_depth": 1,
                "active_dispatches": 0,
                "pending_receipts": 0,
            }

    class _MetricsStub:
        @staticmethod
        def increment(name: str, value: int) -> None:
            return None

    class _FakeDestination:
        OUT = "out"
        SINGLE = "single"

        def __init__(self, identity_obj, *_args) -> None:
            self.identity = identity_obj
            self.hash = bytes.fromhex(destination_hash)

    def _fake_recall(raw_hash: bytes) -> SimpleNamespace | None:
        if bytes(raw_hash).hex() != destination_hash:
            return None
        return SimpleNamespace(hash=bytes.fromhex(identity))

    monkeypatch.setattr(
        hub_module,
        "RNS",
        SimpleNamespace(
            Identity=SimpleNamespace(recall=_fake_recall),
            Destination=_FakeDestination,
        ),
    )
    hub.api = api
    hub.connections = {}
    hub._destination_cache = {}
    hub._destination_cache_lock = threading.Lock()
    hub.outbound_delivery_policy = OutboundDeliveryPolicy(hub)
    hub.my_lxmf_dest = object()
    hub._ensure_outbound_queue = lambda: _QueueStub()
    hub._delivery_message_id = lambda fields, chat_message_id=None: "msg-offline-send-many"
    hub._prepare_outbound_delivery_fields = lambda **kwargs: {}
    hub._runtime_metrics_store = lambda: _MetricsStub()
    hub.message_router = SimpleNamespace(
        record_outbound_route_metrics=lambda **kwargs: recorded_metrics.update(kwargs)
    )

    result = ReticulumTelemetryHub.send_many(
        hub,
        "fanout",
        [identity],
        fields={},
        chat_message_id="chat-offline-send-many",
    )

    assert result is True
    assert len(queued_payloads) == 1
    assert queued_payloads[0].destination_hex == identity
    assert queued_payloads[0].destination_hash.hex() == destination_hash
    assert queued_payloads[0].connection.identity.hash.hex() == identity
    assert queued_payloads[0].delivery_mode == "propagated"
    assert recorded_metrics["selected_propagated_recipient_count"] == 1
