import asyncio
import base64
import re
import threading
import time
from pathlib import Path

import LXMF
import RNS

from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_daemon.LXMF import display_name_from_app_data
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


def test_default_hub_name_includes_version_and_destination_hash(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[app]\n"
        "version = 7.8.9\n"
        "\n"
        "[hub]\n"
        "display_name =\n",
        encoding="utf-8",
    )
    manager = HubConfigurationManager(storage_path=tmp_path, config_path=config_path)
    hub = ReticulumTelemetryHub(
        None,
        str(tmp_path),
        tmp_path / "identity",
        config_manager=manager,
    )

    try:
        destination_hash = hub.my_lxmf_dest.hash.hex()
        expected_name = f"RCH_7.8.9_{destination_hash}"
        assert hub.display_name == expected_name
        assert getattr(hub.my_lxmf_dest, "display_name", None) == expected_name

        app_data = hub._invoke_router_hook("get_announce_app_data", hub.my_lxmf_dest.hash)
        assert display_name_from_app_data(app_data) == expected_name
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


def test_delivery_callback_skips_empty_attachment_data(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    payload = {"name": "empty.webp", "data": ""}
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        fields={LXMF.FIELD_IMAGE: payload},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        assert hub.api.list_images() == []
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


def test_delivery_callback_treats_flat_image_list_payload_as_single_attachment(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    image_bytes = b"\xff\xd8\xfftest-jpeg"
    image_payload = ["jpg", image_bytes]
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
        assert len(stored_images) == 1
        assert re.fullmatch(
            r"Image_\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}\.jpg",
            stored_images[0].name,
        )
        stored_path = Path(stored_images[0].path)
        assert stored_path.read_bytes() == image_bytes
        assert stored_images[0].size == len(image_bytes)
        assert sent
    finally:
        hub.shutdown()


def test_delivery_callback_prefers_original_name_from_image_sequence_payload(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    image_bytes = b"\xff\xd8\xfftest-jpeg"
    image_payload = ["jpg", image_bytes, "image/jpeg", "IMG_20260217_122233.JPG"]
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
        assert len(stored_images) == 1
        assert stored_images[0].name == "IMG_20260217_122233.JPG"
        stored_path = Path(stored_images[0].path)
        assert stored_path.read_bytes() == image_bytes
        assert sent
    finally:
        hub.shutdown()


def test_delivery_callback_extension_label_uses_generated_image_name(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    image_bytes = b"RIFFxxxxWEBPpayload"
    image_payload = ["webp", image_bytes, "image/webp"]
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
        assert len(stored_images) == 1
        assert re.fullmatch(
            r"Image_\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}\.webp",
            stored_images[0].name,
        )
        stored_path = Path(stored_images[0].path)
        assert stored_path.read_bytes() == image_bytes
        assert sent
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


def test_dispatch_northbound_message_records_delivery_ack_event(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    recipient = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    recipient_hex = recipient.identity.hash.hex().lower()
    hub.connections = {recipient.identity.hash: recipient}

    def _simulate_outbound(message: LXMF.LXMessage) -> None:
        callback = getattr(message, "_LXMessage__delivery_callback", None)
        if not callable(callback):
            return

        def _deliver() -> None:
            time.sleep(0.05)
            message.state = LXMF.LXMessage.DELIVERED
            callback(message)

        threading.Thread(target=_deliver, daemon=True).start()

    hub.lxm_router.handle_outbound = _simulate_outbound

    try:
        queued = hub.dispatch_northbound_message(
            "delivery ack test",
            destination=recipient_hex,
        )
        assert queued is not None
        assert queued.message_id
        deadline = time.time() + 1.5
        delivered_message = None
        while time.time() < deadline:
            matches = [
                message
                for message in hub.api.list_chat_messages(limit=20, direction="outbound")
                if message.message_id == queued.message_id
            ]
            if matches and matches[0].state == "delivered":
                delivered_message = matches[0]
                break
            time.sleep(0.05)

        assert delivered_message is not None
        assert delivered_message.destination == recipient_hex

        events = hub.event_log.list_events(limit=200)
        delivered_event = next(
            (
                entry
                for entry in events
                if entry.get("type") == "message_delivered"
                and isinstance(entry.get("metadata"), dict)
                and entry["metadata"].get("MessageID") == queued.message_id
            ),
            None,
        )
        assert delivered_event is not None
        metadata = delivered_event.get("metadata")
        assert isinstance(metadata, dict)
        assert metadata.get("State") == "delivered"
        assert metadata.get("Destination") == recipient_hex
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


def test_mission_registry_event_fanout_is_capability_aware(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")

    source_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    peer_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    source_identity = source_dest.identity.hash.hex().lower()
    peer_identity = peer_dest.identity.hash.hex().lower()

    hub.connections = {
        source_dest.identity.hash: source_dest,
        peer_dest.identity.hash: peer_dest,
    }

    outbound: list[dict[str, object]] = []

    def _capture_send(
        message: str,
        *,
        topic: str | None = None,
        destination: str | None = None,
        exclude: set[str] | None = None,
        fields: dict | None = None,
        sender: RNS.Destination | None = None,
    ) -> bool:
        outbound.append(
            {
                "message": message,
                "topic": topic,
                "destination": destination,
                "exclude": exclude,
                "fields": fields,
                "sender": sender,
            }
        )
        return True

    hub.send_message = _capture_send  # type: ignore[assignment]

    try:
        hub.api.grant_identity_capability(source_identity, "r3akt")
        assert hub.mission_domain_service is not None
        domain = hub.mission_domain_service
        domain.upsert_mission({"uid": "mission-1", "mission_name": "Mission"})
        domain.upsert_team(
            {
                "uid": "team-1",
                "team_name": "Ops",
                "mission_uids": ["mission-1"],
            }
        )
        domain.upsert_team_member(
            {
                "uid": "member-1",
                "team_uid": "team-1",
                "rns_identity": source_identity,
                "display_name": "Source",
            }
        )
        domain.upsert_team_member(
            {
                "uid": "member-2",
                "team_uid": "team-1",
                "rns_identity": peer_identity,
                "display_name": "Peer",
            }
        )
        domain.upsert_log_entry(
            {
                "entry_uid": "entry-1",
                "mission_uid": "mission-1",
                "content": "Mission delta",
            }
        )

        custom_type_field = int(getattr(LXMF, "FIELD_CUSTOM_TYPE", 0xFB))
        custom_data_field = int(getattr(LXMF, "FIELD_CUSTOM_DATA", 0xFC))
        custom_meta_field = int(getattr(LXMF, "FIELD_CUSTOM_META", 0xFD))
        renderer_field = int(getattr(LXMF, "FIELD_RENDERER", 0x0F))
        renderer_markdown_value = int(getattr(LXMF, "RENDERER_MARKDOWN", 0x02))

        custom_fanout = [
            item
            for item in outbound
            if isinstance(item.get("fields"), dict)
            and custom_type_field in item["fields"]
        ]
        assert len(custom_fanout) == 1
        assert custom_fanout[0]["destination"] == source_identity
        for item in custom_fanout:
            fields = item["fields"]
            assert isinstance(fields, dict)
            assert fields[custom_type_field] == "r3akt.mission.change.v1"
            assert fields[custom_data_field]["mission_uid"] == "mission-1"
            assert (
                fields[custom_meta_field]["event_type"]
                == "mission.registry.mission_change.upserted"
            )
        generic_fanout = [
            item
            for item in outbound
            if item.get("destination") == peer_identity
            and "### Mission " in str(item.get("message") or "")
        ]
        assert len(generic_fanout) == 1
        generic_message = str(generic_fanout[0].get("message") or "")
        assert generic_message.startswith("### Mission ")
        assert "mission-1" not in generic_message
        peer_fields = generic_fanout[0].get("fields")
        assert isinstance(peer_fields, dict)
        assert custom_type_field not in peer_fields
        assert peer_fields.get(renderer_field) == renderer_markdown_value
    finally:
        hub.shutdown()


def test_mission_change_fanout_de_duplicates_by_change_uid(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    destination = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    destination_identity = destination.identity.hash.hex().lower()
    outbound: list[dict[str, object]] = []

    def _capture_send(
        message: str,
        *,
        topic: str | None = None,
        destination: str | None = None,
        exclude: set[str] | None = None,
        fields: dict | None = None,
        sender: RNS.Destination | None = None,
    ) -> bool:
        outbound.append(
            {
                "message": message,
                "topic": topic,
                "destination": destination,
                "exclude": exclude,
                "fields": fields,
                "sender": sender,
            }
        )
        return True

    hub.send_message = _capture_send  # type: ignore[assignment]
    try:
        assert hub.mission_domain_service is not None
        domain = hub.mission_domain_service
        domain.upsert_mission({"uid": "mission-1", "mission_name": "Mission"})
        domain.upsert_team(
            {"uid": "team-1", "team_name": "Ops", "mission_uids": ["mission-1"]}
        )
        domain.upsert_team_member(
            {
                "uid": "member-1",
                "team_uid": "team-1",
                "rns_identity": destination_identity,
                "display_name": "Peer",
            }
        )
        hub.api.grant_identity_capability(destination_identity, "r3akt")
        payload = {
            "uid": "change-1",
            "mission_uid": "mission-1",
            "change_type": "ADD_CONTENT",
            "delta": {"version": 1, "logs": [], "assets": [], "tasks": []},
        }
        domain.upsert_mission_change(payload)
        domain.upsert_mission_change(payload)

        fanout_for_change = [
            item for item in outbound if item.get("destination") == destination_identity
        ]
        assert len(fanout_for_change) == 1
    finally:
        hub.shutdown()
