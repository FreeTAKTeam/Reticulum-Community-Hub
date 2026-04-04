import asyncio
import base64
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import LXMF
import pytest
import RNS
from msgpack import packb
from sqlalchemy import text as sqlalchemy_text

import reticulum_telemetry_hub.api.storage as api_storage
from reticulum_telemetry_hub.api.models import FileAttachment
from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_daemon.LXMF import display_name_from_app_data
from reticulum_telemetry_hub.reticulum_server import services
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from reticulum_telemetry_hub.reticulum_server.__main__ import APP_NAME
from reticulum_telemetry_hub.reticulum_server.__main__ import REM_APP_NAME
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
        assert supported.event_log is hub.event_log
        assert "unsupported" not in hub._active_services
    finally:
        hub.stop_daemon_workers()
        hub.shutdown()


def test_create_service_records_initialization_failure(monkeypatch, tmp_path):
    hub = ReticulumTelemetryHub(
        "Daemon",
        str(tmp_path),
        tmp_path / "identity",
        hub_telemetry_interval=0.01,
    )

    def _broken_factory(_hub):
        raise RuntimeError("init boom")

    monkeypatch.setitem(services.SERVICE_FACTORIES, "broken", _broken_factory)

    try:
        assert hub._create_service("broken") is None
        events = [
            event
            for event in hub.event_log.list_events()
            if event.get("type") == "daemon_service_error"
        ]
        assert events
        metadata = events[0]["metadata"]
        assert metadata["service"] == "broken"
        assert metadata["operation"] == "init"
        assert metadata["exception_type"] == "RuntimeError"
        assert metadata["exception_message"] == "init boom"
    finally:
        hub.shutdown()


def test_headless_run_clamps_non_positive_announce_interval(monkeypatch, tmp_path):
    hub = ReticulumTelemetryHub(
        "Daemon",
        str(tmp_path),
        tmp_path / "identity",
        announce_interval=0,
    )
    sleep_calls: list[int] = []

    monkeypatch.setattr(hub, "_refresh_announce_capabilities", lambda **kwargs: None)
    monkeypatch.setattr(hub, "_announce_active_markers", lambda: None)

    def _send_announce(*, reason: str) -> None:
        assert reason == "periodic"
        hub._shutdown = True

    monkeypatch.setattr(hub, "_send_announce", _send_announce)
    monkeypatch.setattr(time, "sleep", lambda seconds: sleep_calls.append(seconds))

    try:
        hub.run()
    finally:
        hub.shutdown()

    assert sleep_calls == [1]


def test_hub_registers_delivery_and_rem_app_announce_handlers(monkeypatch, tmp_path) -> None:
    registered_handlers: list[object] = []

    monkeypatch.setattr(
        RNS.Transport,
        "register_announce_handler",
        lambda handler: registered_handlers.append(handler),
    )

    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")

    try:
        aspects = [getattr(handler, "aspect_filter", None) for handler in registered_handlers]
        assert APP_NAME in aspects
        assert REM_APP_NAME in aspects
    finally:
        hub.shutdown()


def test_hub_service_run_wrapper_records_event() -> None:
    event_log = EventLog()

    class CrashingService(services.HubService):
        def __init__(self) -> None:
            super().__init__(name="crashy", event_log=event_log)

        def _run(self) -> None:
            raise RuntimeError("service boom")

    service = CrashingService()
    service._run_wrapper()

    events = [
        event for event in event_log.list_events() if event.get("type") == "daemon_service_error"
    ]
    assert events
    metadata = events[0]["metadata"]
    assert metadata["service"] == "crashy"
    assert metadata["operation"] == "run"
    assert metadata["exception_type"] == "RuntimeError"
    assert metadata["exception_message"] == "service boom"


def test_gps_service_connect_failure_records_event() -> None:
    event_log = EventLog()

    class DummyManager:
        def enable_sensor(self, name: str) -> None:
            _ = name

        def get_sensor(self, name: str):
            _ = name
            return SimpleNamespace(
                altitude=None,
                speed=None,
                bearing=None,
                accuracy=None,
                latitude=None,
                longitude=None,
                last_update=None,
            )

    service = services.GpsTelemetryService(
        telemeter_manager=DummyManager(),
        client_factory=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("gps boom")),
        host="127.0.0.1",
        port=2947,
    )
    service.event_log = event_log

    service._run()

    events = [
        event for event in event_log.list_events() if event.get("type") == "daemon_service_error"
    ]
    assert events
    metadata = events[0]["metadata"]
    assert metadata["service"] == "gpsd"
    assert metadata["operation"] == "connect"
    assert metadata["exception_type"] == "RuntimeError"
    assert metadata["exception_message"] == "gps boom"


def test_cot_service_send_failures_record_events() -> None:
    event_log = EventLog()

    class DummyConnector:
        def __init__(self) -> None:
            self.config = SimpleNamespace(
                poll_interval_seconds=1.0,
                keepalive_interval_seconds=1.0,
            )
            self.service: services.CotTelemetryService | None = None

        async def send_ping(self) -> None:
            if self.service is not None:
                self.service._stop_event.set()
            raise RuntimeError("ping boom")

        async def send_keepalive(self) -> None:
            raise RuntimeError("keepalive boom")

        async def send_latest_location(self) -> None:
            raise RuntimeError("location boom")

    connector = DummyConnector()
    service = services.CotTelemetryService(
        connector=connector,
        interval=1.0,
        keepalive_interval=1.0,
        ping_interval=1.0,
    )
    connector.service = service
    service.event_log = event_log

    service._run()

    events = [
        event for event in event_log.list_events() if event.get("type") == "daemon_service_error"
    ]
    assert len(events) == 3
    operations = {event["metadata"]["operation"] for event in events}
    assert operations == {"send_ping", "send_keepalive", "send_latest_location"}


def test_apply_lxmf_router_runtime_config_records_nonfatal_events(tmp_path) -> None:
    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    hub.event_log = EventLog()

    class DummyRouter:
        def set_message_storage_limit(self, **kwargs):
            _ = kwargs

        def set_authentication(self, **kwargs):
            _ = kwargs

        def allow(self, identity_hash):
            _ = identity_hash
            raise RuntimeError("allow boom")

        def prioritise(self, destination_hash):
            _ = destination_hash
            raise RuntimeError("prioritise boom")

        def ignore_destination(self, destination_hash):
            _ = destination_hash
            raise RuntimeError("ignore boom")

    lxmf_path = tmp_path / "lxmf-router.ini"
    lxmf_path.write_text("[lxmf]\n", encoding="utf-8")
    (tmp_path / "allowed").write_text(f"{'aa' * 16}\n", encoding="utf-8")
    (tmp_path / "ignored").write_text(f"{'bb' * 16}\n", encoding="utf-8")

    hub.lxm_router = DummyRouter()
    hub.config_manager = SimpleNamespace(
        config=SimpleNamespace(
            lxmf_router=SimpleNamespace(
                path=lxmf_path,
                message_storage_limit_megabytes=7.5,
                auth_required=True,
                prioritised_lxmf_destinations=("cc" * 16,),
            )
        )
    )

    hub._apply_lxmf_router_runtime_config()

    events = [
        event
        for event in hub.event_log.list_events()
        if event.get("type") == "lxmf_runtime_error"
    ]
    assert len(events) == 3
    hooks = {event["metadata"]["hook"] for event in events}
    assert hooks == {"allow", "prioritise", "ignore_destination"}


def test_handle_lxmf_on_inbound_persist_failure_records_event(tmp_path) -> None:
    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    hub.event_log = EventLog()
    hub.storage_path = tmp_path
    hub.config_manager = SimpleNamespace(
        config=SimpleNamespace(lxmf_router=SimpleNamespace(on_inbound="process-inbound"))
    )

    class FailingMessage:
        def write_to_directory(self, path: str):
            _ = path
            raise RuntimeError("persist boom")

    hub._handle_lxmf_on_inbound(FailingMessage())

    events = [
        event
        for event in hub.event_log.list_events()
        if event.get("type") == "lxmf_runtime_error"
    ]
    assert events
    metadata = events[0]["metadata"]
    assert metadata["operation"] == "on_inbound_persist"
    assert metadata["exception_type"] == "RuntimeError"
    assert metadata["exception_message"] == "persist boom"


def test_handle_lxmf_on_inbound_execute_failure_records_event(
    monkeypatch,
    tmp_path,
) -> None:
    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    hub.event_log = EventLog()
    hub.storage_path = tmp_path
    hub.config_manager = SimpleNamespace(
        config=SimpleNamespace(lxmf_router=SimpleNamespace(on_inbound="process-inbound"))
    )

    class Message:
        def write_to_directory(self, path: str):
            written = Path(path) / "message.msg"
            written.write_text("payload", encoding="utf-8")
            return written

    monkeypatch.setattr(
        "reticulum_telemetry_hub.reticulum_server.__main__.subprocess.call",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("exec boom")),
    )

    hub._handle_lxmf_on_inbound(Message())

    events = [
        event
        for event in hub.event_log.list_events()
        if event.get("type") == "lxmf_runtime_error"
    ]
    assert events
    metadata = events[0]["metadata"]
    assert metadata["operation"] == "on_inbound_execute"
    assert metadata["exception_type"] == "RuntimeError"
    assert metadata["exception_message"] == "exec boom"


def test_delivery_callback_records_response_send_failures(tmp_path) -> None:
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    calls = {"count": 0}

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        fields={LXMF.FIELD_COMMANDS: [{PLUGIN_COMMAND: "TestCommand"}]},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    attachment_response = hub._reply_message(
        message,
        "Attachment payload",
        fields={
            LXMF.FIELD_FILE_ATTACHMENTS: [
                {"name": "report.txt", "data": b"payload", "media_type": "text/plain"}
            ]
        },
    )
    assert attachment_response is not None
    hub.command_handler = lambda commands, inbound: [attachment_response]

    def handle_outbound(_message):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("send boom")
        raise RuntimeError("fallback boom")

    hub.lxm_router.handle_outbound = handle_outbound

    try:
        hub.delivery_callback(message)
        events = [
            event
            for event in hub.event_log.list_events()
            if event.get("type") == "lxmf_runtime_error"
        ]
        operations = {event["metadata"]["operation"] for event in events}
        assert operations == {"send_response", "send_fallback_response"}
    finally:
        hub.shutdown()


def test_dispatch_northbound_message_records_attachment_build_failure(
    tmp_path,
) -> None:
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    hub.send_message = lambda *args, **kwargs: True
    hub._build_lxmf_attachment_fields = lambda attachments: (_ for _ in ()).throw(
        RuntimeError("attachment boom")
    )

    attachment = FileAttachment(
        name="note.txt",
        path=str(tmp_path / "note.txt"),
        category="file",
        size=4,
        media_type="text/plain",
    )

    try:
        hub.dispatch_northbound_message("hello", fields={"attachments": [attachment]})
        events = [
            event
            for event in hub.event_log.list_events()
            if event.get("type") == "lxmf_runtime_error"
        ]
        assert events
        metadata = events[0]["metadata"]
        assert metadata["operation"] == "build_attachment_fields"
        assert metadata["exception_type"] == "RuntimeError"
        assert metadata["exception_message"] == "attachment boom"
    finally:
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


def test_delivery_callback_telemetry_only_from_unjoined_sender_does_not_reply_help(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(api_storage, "text", sqlalchemy_text, raising=False)
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    payload = packb({1: int(time.time())}, use_bin_type=True)
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        fields={LXMF.FIELD_TELEMETRY: payload},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        assert sent == []
    finally:
        hub.shutdown()


def test_delivery_callback_plaintext_from_unjoined_sender_replies_help(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(api_storage, "text", sqlalchemy_text, raising=False)
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        content="hello hub",
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        assert len(sent) == 1
        assert "Command" in sent[0].content_as_string()
    finally:
        hub.shutdown()


def test_delivery_callback_unknown_command_from_unjoined_sender_does_not_duplicate_help(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(api_storage, "text", sqlalchemy_text, raising=False)
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
    hub.lxm_router.handle_outbound = lambda message: sent.append(message)

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = LXMF.LXMessage(
        hub.my_lxmf_dest,
        sender,
        fields={LXMF.FIELD_COMMANDS: [{PLUGIN_COMMAND: "NotARealCommand"}]},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.signature_validated = True

    try:
        hub.delivery_callback(message)
        assert len(sent) == 1
        assert "Unknown command" in sent[0].content_as_string()
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
        assert queued.state == "queued"
        deadline = time.time() + 1.5
        delivered_message = None
        delivered_event = None
        while time.time() < deadline:
            matches = [
                message
                for message in hub.api.list_chat_messages(limit=20, direction="outbound")
                if message.message_id == queued.message_id
            ]
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
            if matches and matches[0].state == "delivered" and delivered_event is not None:
                delivered_message = matches[0]
                break
            time.sleep(0.05)

        assert delivered_message is not None
        assert delivered_message.destination == recipient_hex
        assert delivered_message.delivery_metadata["acked"] is True
        assert delivered_message.delivery_metadata["route_type"] == "targeted"
        assert delivered_message.delivery_metadata["content_type"] == "text/plain; schema=lxmf.chat.v1"

        assert delivered_event is not None
        metadata = delivered_event.get("metadata")
        assert isinstance(metadata, dict)
        assert metadata.get("State") == "delivered"
        assert metadata.get("Destination") == recipient_hex
        assert metadata.get("acknowledgement_type") == "delivery_receipt"
        assert "enqueue_age_ms" in metadata.get("DeliveryMetadata", {})
    finally:
        hub.shutdown()


def test_dispatch_northbound_message_fails_when_delivery_ack_never_arrives(tmp_path):
    hub = ReticulumTelemetryHub(
        "Daemon",
        str(tmp_path),
        tmp_path / "identity",
        outbound_delivery_receipt_timeout=0.05,
        outbound_backoff=0.01,
        outbound_max_attempts=1,
    )
    recipient = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    recipient_hex = recipient.identity.hash.hex().lower()
    hub.connections = {recipient.identity.hash: recipient}
    hub.lxm_router.handle_outbound = lambda message: None

    try:
        queued = hub.dispatch_northbound_message(
            "delivery timeout test",
            destination=recipient_hex,
        )
        assert queued is not None
        assert queued.message_id
        assert queued.state == "queued"

        deadline = time.time() + 1.5
        failed_message = None
        while time.time() < deadline:
            matches = [
                message
                for message in hub.api.list_chat_messages(limit=20, direction="outbound")
                if message.message_id == queued.message_id
            ]
            if matches and matches[0].state == "failed":
                failed_message = matches[0]
                break
            time.sleep(0.05)

        assert failed_message is not None
        assert failed_message.destination == recipient_hex

        events = hub.event_log.list_events(limit=200)
        failure_event = next(
            (
                entry
                for entry in events
                if entry.get("type") == "message_delivery_failed"
                and isinstance(entry.get("metadata"), dict)
                and entry["metadata"].get("MessageID") == queued.message_id
            ),
            None,
        )
        assert failure_event is not None
        metadata = failure_event.get("metadata")
        assert isinstance(metadata, dict)
        assert metadata.get("State") == "failed"
        assert metadata.get("Destination") == recipient_hex
        assert failed_message.delivery_metadata["acked"] is False
        assert failed_message.delivery_metadata["attempts"] == 1
        routed_event = next(
            (
                entry
                for entry in events
                if entry.get("type") == "message_routed"
                and isinstance(entry.get("metadata"), dict)
                and entry["metadata"].get("MessageID") == queued.message_id
            ),
            None,
        )
        assert routed_event is not None
        routed_metadata = routed_event.get("metadata")
        assert isinstance(routed_metadata, dict)
        assert "queue_depth" in routed_metadata
        assert "enqueue_duration_ms" in routed_metadata
        assert "active_sends" in routed_metadata
        assert "pending_receipts" in routed_metadata
    finally:
        hub.shutdown()


def test_dispatch_northbound_message_rejects_mixed_routing_modes(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")

    try:
        with pytest.raises(ValueError, match="mutually exclusive"):
            hub.dispatch_northbound_message(
                "mixed route",
                topic_id="ops.alpha",
                destination="deadbeef",
            )
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

    def _simulate_outbound(message: LXMF.LXMessage) -> None:
        sent.append(message)
        callback = getattr(message, "_LXMessage__delivery_callback", None)
        if callable(callback):
            message.state = LXMF.LXMessage.DELIVERED
            callback(message)

    hub.lxm_router.handle_outbound = _simulate_outbound

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
        hub.api.record_identity_announce(
            source_identity,
            display_name="REM Alpha",
            announce_capabilities="R3AKT,EMergencyMessages",
        )
        hub.api.record_identity_announce(
            peer_identity,
            display_name="Generic Bravo",
            announce_capabilities=["telemetry"],
        )
        hub.api.set_rem_mode(source_identity, "connected")
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

        event_field = int(getattr(LXMF, "FIELD_EVENT", 0xED))
        renderer_field = int(getattr(LXMF, "FIELD_RENDERER", 0x0F))
        renderer_markdown_value = int(getattr(LXMF, "RENDERER_MARKDOWN", 0x02))

        rem_fanout = [
            item
            for item in outbound
            if isinstance(item.get("fields"), dict)
            and event_field in item["fields"]
        ]
        assert len(rem_fanout) == 1
        assert rem_fanout[0]["destination"] == source_identity
        for item in rem_fanout:
            fields = item["fields"]
            assert isinstance(fields, dict)
            assert fields[event_field]["event_type"] == "mission.registry.log_entry.upserted"
            assert fields[event_field]["payload"]["mission_uid"] == "mission-1"
        generic_fanout = [
            item
            for item in outbound
            if item.get("destination") == peer_identity and "### Mission Log Update" in str(item.get("message") or "")
        ]
        assert len(generic_fanout) == 1
        generic_message = str(generic_fanout[0].get("message") or "")
        assert generic_message.startswith("### Mission Log Update")
        assert "Mission: mission-1" in generic_message
        peer_fields = generic_fanout[0].get("fields")
        assert isinstance(peer_fields, dict)
        assert peer_fields.get(renderer_field) == renderer_markdown_value
    finally:
        hub.shutdown()


def test_rem_registry_commands_and_connected_eam_fanout(tmp_path):
    hub = ReticulumTelemetryHub("Daemon", str(tmp_path), tmp_path / "identity")

    rem_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    generic_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    rem_identity = rem_dest.identity.hash.hex().lower()
    generic_identity = generic_dest.identity.hash.hex().lower()
    hub.connections = {
        rem_dest.identity.hash: rem_dest,
        generic_dest.identity.hash: generic_dest,
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

    class _InboundMessage:
        def __init__(self, source_destination: RNS.Destination) -> None:
            self.source = source_destination
            self.fields: dict = {}

        def get_source(self):
            return self.source

    hub.send_message = _capture_send  # type: ignore[assignment]

    try:
        hub.api.record_identity_announce(
            rem_identity,
            display_name="REM Alpha",
            announce_capabilities="R3AKT,EMergencyMessages",
        )
        hub.api.record_identity_announce(
            generic_identity,
            display_name="Generic Bravo",
            announce_capabilities=["telemetry"],
        )

        command_message = _InboundMessage(rem_dest)
        mode_responses = hub.command_handler(  # pylint: disable=assignment-from-no-return
            [
                {
                    "command_id": "mode-1",
                    "source": {"rns_identity": rem_identity},
                    "timestamp": "2026-04-02T12:00:00Z",
                    "command_type": "rem.registry.mode.set",
                    "args": {"mode": "connected"},
                },
                {
                    "command_id": "peers-1",
                    "source": {"rns_identity": rem_identity},
                    "timestamp": "2026-04-02T12:00:00Z",
                    "command_type": "rem.registry.peers.list",
                    "args": {},
                },
            ],
            command_message,
        )

        result_payloads = [
            response.fields[LXMF.FIELD_RESULTS]
            for response in mode_responses
            if LXMF.FIELD_RESULTS in response.fields
            and response.fields[LXMF.FIELD_RESULTS].get("status") == "result"
        ]
        assert any(payload["result"]["mode"] == "connected" for payload in result_payloads if "mode" in payload["result"])
        assert any(payload["result"]["items"][0]["identity"] == rem_identity for payload in result_payloads if "items" in payload["result"])

        assert hub.mission_domain_service is not None
        hub.mission_domain_service.upsert_team({"uid": "team-1", "team_name": "Ops"})
        hub.mission_domain_service.upsert_team_member(
            {
                "uid": "member-1",
                "team_uid": "team-1",
                "rns_identity": rem_identity,
                "display_name": "REM Alpha",
                "callsign": "OPS-1",
            }
        )
        assert hub.emergency_action_message_service is not None
        hub.emergency_action_message_service.upsert_message(
            {
                "eam_uid": "eam-1",
                "callsign": "OPS-1",
                "group_name": "Ops",
                "team_member_uid": "member-1",
                "team_uid": "team-1",
                "reported_by": "REM Alpha",
                "security_status": "Green",
                "capability_status": "Red",
                "preparedness_status": "Green",
                "medical_status": "Green",
                "mobility_status": "Green",
                "comms_status": "Green",
                "source": {"rns_identity": rem_identity},
            }
        )

        rem_messages = [
            item
            for item in outbound
            if item.get("destination") == rem_identity
            and isinstance(item.get("fields"), dict)
            and LXMF.FIELD_COMMANDS in item["fields"]
        ]
        generic_messages = [
            item
            for item in outbound
            if item.get("destination") == generic_identity
            and "### Emergency Message Updated" in str(item.get("message") or "")
        ]

        assert rem_messages
        command_payload = rem_messages[0]["fields"][LXMF.FIELD_COMMANDS][0]
        assert command_payload["command_type"] == "mission.registry.eam.upsert"
        assert command_payload["args"]["eam_uid"] == "eam-1"
        assert generic_messages
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
