import asyncio
import base64
import time
from pathlib import Path

import LXMF
import RNS

from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.reticulum_server import services
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub
from reticulum_telemetry_hub.reticulum_server.__main__ import _dispatch_coroutine


def test_dispatch_coroutine_runs_without_loop():
    ran: list[str] = []

    async def _mark_run() -> None:
        ran.append("ran")

    _dispatch_coroutine(_mark_run())

    assert ran == ["ran"]


def test_dispatch_coroutine_uses_running_loop():
    ran: list[str] = []

    async def _mark_run() -> None:
        ran.append("ran")

    async def _runner() -> None:
        _dispatch_coroutine(_mark_run())
        await asyncio.sleep(0)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_runner())
    finally:
        loop.close()

    assert ran == ["ran"]


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


def test_delivery_callback_stores_file_attachments(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    payload = [
        {"name": "report.txt", "data": b"file-content", "media_type": "text/plain"}
    ]
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        fields={LXMF.FIELD_FILE_ATTACHMENTS: payload},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        stored_files = hub.api.list_files()
        assert stored_files
        stored_path = Path(stored_files[0].path)
        assert stored_path.read_bytes() == b"file-content"
        assert sent
        ack_texts = [msg.content_as_string() for msg in sent]
        assert any("Stored files" in text for text in ack_texts if text)
        assert any(str(stored_files[0].file_id) in text for text in ack_texts if text)
    finally:
        hub.shutdown()

def test_delivery_callback_decodes_base64_file_payload(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    raw_bytes = b"base64-data"
    encoded = base64.b64encode(raw_bytes).decode("ascii")
    payload = [
        {
            "name": "payload.bin",
            "data": encoded,
            "media_type": "application/octet-stream",
        }
    ]
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        fields={LXMF.FIELD_FILE_ATTACHMENTS: payload},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        stored_files = hub.api.list_files()
        assert stored_files
        stored_path = Path(stored_files[0].path)
        assert stored_path.read_bytes() == raw_bytes
        assert sent
    finally:
        hub.shutdown()


def test_delivery_callback_accepts_integer_list_payload(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    raw_bytes = b"list-bytes"
    payload = [{"name": "list.bin", "data": list(raw_bytes)}]
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        fields={LXMF.FIELD_FILE_ATTACHMENTS: payload},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        stored_files = hub.api.list_files()
        assert stored_files
        stored_path = Path(stored_files[0].path)
        assert stored_path.read_bytes() == raw_bytes
        assert sent
    finally:
        hub.shutdown()


def test_delivery_callback_accepts_case_insensitive_payload_keys(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    raw_bytes = b"caps"
    payload = [{"Name": "caps.bin", "Data": raw_bytes}]
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        fields={LXMF.FIELD_FILE_ATTACHMENTS: payload},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        stored_files = hub.api.list_files()
        assert stored_files
        stored_path = Path(stored_files[0].path)
        assert stored_path.read_bytes() == raw_bytes
        assert sent
    finally:
        hub.shutdown()


def test_delivery_callback_accepts_list_attachment_payload(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    raw_bytes = b"list-payload"
    payload = [["readme.txt", raw_bytes]]
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        fields={LXMF.FIELD_FILE_ATTACHMENTS: payload},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        stored_files = hub.api.list_files()
        assert stored_files
        stored_path = Path(stored_files[0].path)
        assert stored_path.read_bytes() == raw_bytes
        assert sent
    finally:
        hub.shutdown()


def test_delivery_callback_skips_missing_attachment_data(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    payload = [{"name": "missing.bin"}]
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        fields={LXMF.FIELD_FILE_ATTACHMENTS: payload},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        assert hub.api.list_files() == []
        assert sent
        assert any(
            "Attachment errors" in msg.content_as_string() for msg in sent if msg
        )
    finally:
        hub.shutdown()


def test_delivery_callback_escape_prefixed_invalid_json_replies_error(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        content="\\\\\\[{broken]",
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        assert sent
        assert any(
            "Command error" in msg.content_as_string() for msg in sent if msg
        )
    finally:
        hub.shutdown()


def test_delivery_callback_stores_image_field(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    image_payload = {"name": "snapshot.png", "data": b"img-bytes", "mime": "image/png"}
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        fields={LXMF.FIELD_IMAGE: image_payload},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        stored_images = hub.api.list_images()
        assert stored_images
        stored_path = Path(stored_images[0].path)
        assert stored_path.read_bytes() == b"img-bytes"
        assert sent
        ack_texts = [msg.content_as_string() for msg in sent]
        assert any("Stored images" in text for text in ack_texts if text)
        assert any(str(stored_images[0].file_id) in text for text in ack_texts if text)
    finally:
        hub.shutdown()


def test_delivery_callback_infers_image_extension(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    png_bytes = b"\x89PNG\r\n\x1a\npayload"
    image_payload = {"data": png_bytes}
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        fields={LXMF.FIELD_IMAGE: image_payload},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        stored_images = hub.api.list_images()
        assert stored_images
        stored_path = Path(stored_images[0].path)
        assert stored_path.suffix == ".png"
        assert stored_path.read_bytes() == png_bytes
    finally:
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
        hub.wait_for_outbound_flush()

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
        hub.wait_for_outbound_flush()

        destinations = {msg.destination_hash for msg in sent}
        assert dest_two.identity.hash in destinations
        topic_hexes = hub.topic_subscribers.get(topic_id, set())
        assert dest_two.identity.hash.hex().lower() in topic_hexes
    finally:
        hub.shutdown()
