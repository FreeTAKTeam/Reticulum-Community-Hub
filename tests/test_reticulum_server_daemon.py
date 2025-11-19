import time

import LXMF
import RNS
import pytest

from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.reticulum_server import services
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub


class DummyService(services.HubService):
    def __init__(self, *, supported: bool):
        super().__init__(name="dummy")
        self._supported = supported
        self.started = False

    def is_supported(self) -> bool:
        return self._supported

    def _run(self) -> None:
        self.started = True
        self._stop_event.wait(0.1)


def test_daemon_sampler_collects_local_telemetry(tmp_path):
    hub = ReticulumTelemetryHub(
        "Daemon",
        str(tmp_path),
        tmp_path / "identity",
        hub_telemetry_interval=0.01,
    )

    try:
        hub.start_daemon_workers()
        time.sleep(0.05)
        hub.stop_daemon_workers()
        stored = hub.tel_controller.get_telemetry()
        assert stored, "Sampler did not persist telemetry in daemon mode"
    finally:
        hub.shutdown()


def test_daemon_service_gating(monkeypatch, tmp_path):
    hub = ReticulumTelemetryHub(
        "Daemon",
        str(tmp_path),
        tmp_path / "identity",
        hub_telemetry_interval=0.01,
    )

    unsupported = DummyService(supported=False)
    supported = DummyService(supported=True)

    monkeypatch.setitem(
        services.SERVICE_FACTORIES,
        "unsupported",
        lambda hub: unsupported,
    )
    monkeypatch.setitem(
        services.SERVICE_FACTORIES,
        "supported",
        lambda hub: supported,
    )

    try:
        hub.start_daemon_workers(services=["unsupported", "supported"])
        assert "supported" in hub._active_services
        assert supported.started
        assert "unsupported" not in hub._active_services
    finally:
        hub.stop_daemon_workers()
        hub.shutdown()


def test_subscriber_cache_refresh_after_subscribe(tmp_path):
    hub = ReticulumTelemetryHub(
        "Daemon",
        str(tmp_path),
        tmp_path / "identity",
    )

    topic_id = "topic-dynamic"
    dest_one = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dest_two = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    class DummyAPI:
        def __init__(self) -> None:
            self.subscribers = [
                Subscriber(
                    destination=dest_one.identity.hash.hex(),
                    topic_id=topic_id,
                    metadata={"tag": "alpha"},
                )
            ]

        def list_subscribers(self):
            return list(self.subscribers)

        def subscribe_topic(self, topic_id: str, destination: str, **_: dict):
            subscriber = Subscriber(
                destination=destination,
                topic_id=topic_id,
                metadata={"tag": "beta"},
            )
            self.subscribers.append(subscriber)
            return subscriber

    dummy_api = DummyAPI()
    hub.api = dummy_api
    hub.command_manager.api = dummy_api
    hub.connections = {
        dest_one.identity.hash: dest_one,
        dest_two.identity.hash: dest_two,
    }
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    try:
        hub._refresh_topic_registry()
        hub.send_message("Hello", topic=topic_id)

        assert {msg.destination_hash for msg in sent} == {dest_one.identity.hash}

        subscribe_command = {
            PLUGIN_COMMAND: CommandManager.CMD_SUBSCRIBE_TOPIC,
            "TopicID": topic_id,
        }
        subscribe_message = LXMF.LXMessage(
            hub.my_lxmf_dest,
            dest_two,
            fields={LXMF.FIELD_COMMANDS: [subscribe_command]},
            desired_method=LXMF.LXMessage.DIRECT,
        )
        subscribe_message.pack()
        subscribe_message.signature_validated = True

        sent.clear()
        hub.delivery_callback(subscribe_message)
        hub.send_message("Hello again", topic=topic_id)

        destinations = {msg.destination_hash for msg in sent}
        assert dest_two.identity.hash in destinations
        topic_hexes = hub.topic_subscribers.get(topic_id, set())
        assert dest_two.identity.hash.hex().lower() in topic_hexes
    finally:
        hub.shutdown()
