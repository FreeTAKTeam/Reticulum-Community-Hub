import asyncio
import json
import time
from datetime import datetime, timedelta

import xml.etree.ElementTree as ET

import pytest
import RNS

from reticulum_telemetry_hub.atak_cot.tak_connector import LocationSnapshot
from reticulum_telemetry_hub.atak_cot.tak_connector import TakConnector
from reticulum_telemetry_hub.atak_cot import Remarks
from reticulum_telemetry_hub.config.models import TakConnectionConfig
from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import (
    TelemeterManager,
)
from reticulum_telemetry_hub.reticulum_server.services import (
    CotTelemetryService,
)


class DummyPytakClient:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def create_and_send_message(self, message, config=None, parse_inbound=True):
        self.sent.append((message, config, parse_inbound))


def _build_manager() -> TelemeterManager:
    manager = TelemeterManager()
    sensor = manager.get_sensor("location")
    assert sensor is not None
    sensor.latitude = 40.7128
    sensor.longitude = -74.006
    sensor.altitude = 12.0
    sensor.speed = 2.5
    sensor.bearing = 180.0
    sensor.accuracy = 5.0
    sensor.last_update = datetime(2025, 1, 1, 0, 0, 0)
    manager.telemeter.peer_dest = "userhash1"
    return manager


def _telemetry_payload() -> dict:
    return {
        "time": {"timestamp": 1764453963.0},
        "location": {
            "latitude": 50.0,
            "longitude": 15.0,
            "altitude": 0.0,
            "speed": 0.0,
            "bearing": 0.0,
            "accuracy": 0.01,
            "last_update_iso": "2025-11-29T20:36:02",
        },
    }


def test_connector_builds_cot_event_from_location():
    manager = _build_manager()
    config = TakConnectionConfig(
        cot_url="udp://example:8087",
        callsign="HUB",
        poll_interval_seconds=10.0,
    )
    client = DummyPytakClient()
    connector = TakConnector(
        config=config, pytak_client=client, telemeter_manager=manager
    )

    event = connector.build_event()

    assert event is not None
    assert event.uid == "userhash1"
    assert event.point.lat == pytest.approx(40.7128)
    assert event.point.lon == pytest.approx(-74.006)
    assert event.detail is not None
    assert event.detail.contact is not None
    assert event.detail.contact.callsign == "userhash1"
    assert event.detail.contact.endpoint == "example:8087:udp"
    assert event.detail.group is not None
    assert event.detail.group.name == "Yellow"
    assert event.detail.group.role == "Team Member"
    assert event.detail.track is not None
    assert event.detail.track.course == pytest.approx(180.0)
    assert event.detail.track.speed == pytest.approx(2.5)
    assert event.detail.status is not None
    assert event.detail.status.battery == pytest.approx(0.0)
    assert event.detail.takv is not None
    assert event.detail.takv.version == "4.9.0.156"
    assert event.detail.uid is not None
    assert event.detail.uid.droid == "userhash1"
    assert event.start.startswith("2025-01-01T00:00:00")


def test_connector_build_event_generates_expected_xml():
    manager = _build_manager()
    connector = TakConnector(
        config=TakConnectionConfig(callsign="HUB"), telemeter_manager=manager
    )

    event = connector.build_event()

    assert event is not None
    xml_data = event.to_xml()
    root = ET.fromstring(xml_data)

    assert root.get("uid") == "userhash1"

    detail = root.find("detail")
    assert detail is not None
    contact_el = detail.find("contact")
    assert contact_el is not None
    assert contact_el.get("callsign") == "userhash1"
    assert contact_el.get("endpoint") == "127.0.0.1:8087:tcp"

    takv_el = detail.find("takv")
    assert takv_el is not None
    assert takv_el.get("version") == "4.9.0.156"
    assert takv_el.get("platform") == "WinTAK-CIV"
    assert takv_el.get("os") == "Microsoft Windows 11 Pro"
    assert takv_el.get("device") == "LENOVO 20XW003LUS"

    group_el = detail.find("__group")
    assert group_el is not None
    assert group_el.get("name") == "Yellow"
    assert group_el.get("role") == "Team Member"

    track_el = detail.find("track")
    assert track_el is not None
    assert track_el.get("course") == "180.0"
    assert track_el.get("speed") == "2.5"

    status_el = detail.find("status")
    assert status_el is not None
    assert status_el.get("battery") == "0.0"

    uid_el = detail.find("uid")
    assert uid_el is not None
    assert uid_el.get("Droid") == "userhash1"


def test_connector_prefers_identity_lookup_label():
    manager = _build_manager()
    manager.telemeter.peer_dest = "deadbeef"
    lookups: list[str | bytes | None] = []

    def lookup_identity(peer_hash: str | bytes | None) -> str:
        lookups.append(peer_hash)
        if peer_hash == "deadbeef":
            return "Display Name"
        return ""

    connector = TakConnector(
        config=TakConnectionConfig(callsign="HUB"),
        telemeter_manager=manager,
        identity_lookup=lookup_identity,
    )

    event = connector.build_event()

    assert event is not None
    assert event.uid == "deadbeef"
    assert event.detail is not None
    assert event.detail.contact is not None
    assert event.detail.contact.callsign == "Display Name"
    assert lookups


def test_connector_normalizes_pretty_hash_identifiers():
    manager = _build_manager()
    manager.telemeter.peer_dest = "aa:bb:cc:dd"
    connector = TakConnector(
        config=TakConnectionConfig(callsign="HUB"), telemeter_manager=manager
    )

    event = connector.build_event()

    assert event is not None
    assert event.detail is not None
    assert event.detail.contact is not None
    assert event.detail.contact.callsign == "aabbccdd"
    assert event.uid == "aabbccdd"


def test_connector_sends_cot_payload():
    manager = _build_manager()
    client = DummyPytakClient()
    config = TakConnectionConfig(cot_url="udp://example:8087", callsign="HUB")
    connector = TakConnector(
        config=config, pytak_client=client, telemeter_manager=manager
    )

    sent = asyncio.run(connector.send_latest_location())

    assert sent is True
    assert client.sent
    message, cfg, parse_flag = client.sent[0]
    assert message.detail.contact.callsign == "userhash1"
    assert cfg["fts"]["COT_URL"] == "udp://example:8087"
    assert cfg["fts"]["TAK_PROTO"] == "0"
    assert cfg["fts"]["FTS_COMPAT"] == "1"
    assert parse_flag is False


def test_connection_config_includes_pytak_options():
    config = TakConnectionConfig(
        cot_url="tcp://example:1234",
        callsign="TEST",
        tak_proto=0,
        fts_compat=1,
    )

    cfg = config.to_config_parser()

    assert cfg["fts"]["COT_URL"] == "tcp://example:1234"
    assert cfg["fts"]["CALLSIGN"] == "TEST"
    assert cfg["fts"]["TAK_PROTO"] == "0"
    assert cfg["fts"]["FTS_COMPAT"] == "1"


def test_send_latest_location_uses_snapshot(monkeypatch):
    """Ensure ``send_latest_location`` sends when a snapshot exists."""

    client = DummyPytakClient()
    connector = TakConnector(
        config=TakConnectionConfig(callsign="HUB"), pytak_client=client
    )
    snapshot = LocationSnapshot(
        latitude=1.0,
        longitude=2.0,
        altitude=3.0,
        speed=0.0,
        bearing=0.0,
        accuracy=1.0,
        updated_at=datetime(2025, 1, 1, 0, 0, 0),
    )
    monkeypatch.setattr(connector, "_latest_location", lambda: snapshot)

    result = asyncio.run(connector.send_latest_location())

    assert result is True
    assert client.sent
    message, cfg, parse_flag = client.sent[0]
    assert message.point.lat == pytest.approx(1.0)
    assert message.point.lon == pytest.approx(2.0)
    assert cfg["fts"]["CALLSIGN"] == "HUB"
    assert parse_flag is False


def test_build_event_from_telemetry_uses_sender_uid():
    peer_hash = bytes.fromhex("c9ded55aad183600fd8c4e2ad341a7e1")
    connector = TakConnector(config=TakConnectionConfig(callsign="HUB"))

    event = connector.build_event_from_telemetry(
        _telemetry_payload(),
        peer_hash=peer_hash,
        timestamp=datetime(2025, 11, 29, 22, 6, 3),
    )

    assert event is not None
    assert event.uid == peer_hash.hex()
    assert event.detail is not None
    assert event.detail.contact is not None
    assert event.detail.contact.callsign == peer_hash.hex()
    assert event.point.lat == pytest.approx(50.0)
    assert event.point.lon == pytest.approx(15.0)
    assert event.start.startswith("2025-11-29T20:36:02")


def test_send_telemetry_event_dispatches(monkeypatch):
    client = DummyPytakClient()

    def identity_lookup(_: str | bytes | None) -> str:
        return "Scout"

    connector = TakConnector(
        config=TakConnectionConfig(callsign="HUB"),
        pytak_client=client,
        identity_lookup=identity_lookup,
    )

    asyncio.run(
        connector.send_telemetry_event(
            _telemetry_payload(),
            peer_hash="abcd1234",
            timestamp=datetime(2025, 11, 29, 22, 6, 3),
        )
    )

    assert client.sent
    event, cfg, parse_flag = client.sent[0]
    assert event.uid == "abcd1234"
    assert event.detail.contact.callsign == "Scout"
    assert cfg["fts"]["CALLSIGN"] == "HUB"
    assert parse_flag is False


def test_send_keepalive_dispatches():
    client = DummyPytakClient()
    connector = TakConnector(
        config=TakConnectionConfig(callsign="HUB"), pytak_client=client
    )

    asyncio.run(connector.send_keepalive())

    assert client.sent
    message, cfg, parse_flag = client.sent[0]
    root = ET.fromstring(message)
    assert root.get("type") == "t-x-d-d"
    assert root.get("uid") == "takPong"
    assert cfg["fts"]["CALLSIGN"] == "HUB"
    assert parse_flag is False


def test_cot_service_publishes_periodically():
    manager = _build_manager()
    client = DummyPytakClient()
    connector = TakConnector(
        config=TakConnectionConfig(poll_interval_seconds=0.05),
        pytak_client=client,
        telemeter_manager=manager,
    )
    service = CotTelemetryService(connector=connector, interval=0.05)

    try:
        started = service.start()
        assert started is True
        time.sleep(0.3)
    finally:
        service.stop()

    assert len(client.sent) >= 2
    assert any(isinstance(payload, bytes) for payload, _, _ in client.sent)
    assert any(hasattr(payload, "detail") for payload, _, _ in client.sent)


def test_build_chat_event_includes_topic():
    connector = TakConnector(config=TakConnectionConfig(callsign="RTH"))

    event = connector.build_chat_event(
        content="Hello team",
        sender_label="Alpha",
        topic_id="ops",
        source_hash=b"\xaa" * 8,
        timestamp=datetime(2025, 1, 2, 3, 4, 5),
    )

    assert event.type == connector.CHAT_EVENT_TYPE
    assert event.detail is not None
    assert event.detail.chat is not None
    assert event.detail.chat.chatroom == "ops"
    assert event.detail.chat.chat_group is not None
    assert isinstance(event.detail.remarks, Remarks)
    assert event.detail.remarks.text == "Hello team"
    assert event.detail.remarks.to == "ops"


def test_send_chat_event_dispatches_payload():
    client = DummyPytakClient()
    connector = TakConnector(
        config=TakConnectionConfig(callsign="HUB"), pytak_client=client
    )

    asyncio.run(
        connector.send_chat_event(
            content="Status update",
            sender_label="Bravo",
            topic_id="status",
            source_hash="feed",
            timestamp=datetime(2025, 1, 1, 0, 0, 0),
        )
    )

    assert client.sent
    event, cfg, parse_flag = client.sent[0]
    assert event.type == connector.CHAT_EVENT_TYPE
    assert event.detail is not None
    assert event.detail.chat is not None
    assert event.detail.chat.chatroom == "status"
    assert isinstance(event.detail.remarks, Remarks)
    assert event.detail.remarks.text == "Status update"
    assert cfg["fts"]["CALLSIGN"] == "HUB"
    assert parse_flag is False


def test_send_latest_location_logs_payload(monkeypatch):
    manager = _build_manager()
    client = DummyPytakClient()
    connector = TakConnector(
        config=TakConnectionConfig(callsign="HUB"),
        pytak_client=client,
        telemeter_manager=manager,
    )
    logs: list[tuple[str, int | None]] = []

    def fake_log(message: str, level: int | None = None) -> None:
        logs.append((message, level))

    monkeypatch.setattr(
        "reticulum_telemetry_hub.atak_cot.tak_connector.RNS.log", fake_log
    )

    asyncio.run(connector.send_latest_location())

    assert client.sent
    assert logs
    payload_entry = next(
        (msg for msg, level in logs if "payload:" in msg and level == RNS.LOG_INFO),
        None,
    )
    assert payload_entry is not None
    payload_text = payload_entry.split("payload:", maxsplit=1)[1].strip()
    payload = json.loads(payload_text)
    assert payload.get("type") == connector.EVENT_TYPE


def test_send_chat_event_logs_payload(monkeypatch):
    client = DummyPytakClient()
    connector = TakConnector(
        config=TakConnectionConfig(callsign="HUB"), pytak_client=client
    )
    logs: list[tuple[str, int | None]] = []

    def fake_log(message: str, level: int | None = None) -> None:
        logs.append((message, level))

    monkeypatch.setattr(
        "reticulum_telemetry_hub.atak_cot.tak_connector.RNS.log", fake_log
    )

    asyncio.run(
        connector.send_chat_event(
            content="Status update",
            sender_label="Bravo",
            topic_id="ops",
            source_hash="feed",
            timestamp=datetime(2025, 1, 1, 0, 0, 0),
        )
    )

    assert client.sent
    assert logs
    payload_entry = next(
        (msg for msg, level in logs if "payload:" in msg and level == RNS.LOG_INFO),
        None,
    )
    assert payload_entry is not None
    payload_text = payload_entry.split("payload:", maxsplit=1)[1].strip()
    payload = json.loads(payload_text)
    assert payload.get("type") == connector.CHAT_EVENT_TYPE


def test_chat_uids_remain_unique():
    connector = TakConnector(config=TakConnectionConfig(callsign="RTH"))

    first = connector.build_chat_event(
        content="Hello there",
        sender_label="Alpha",
        topic_id="ops",
        source_hash=b"\x01" * 8,
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
    )
    second = connector.build_chat_event(
        content="Hello there",
        sender_label="Alpha",
        topic_id="ops",
        source_hash=b"\x01" * 8,
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
    )

    assert first.uid != second.uid


def test_chat_event_matches_geochat_payload(monkeypatch):
    connector = TakConnector(config=TakConnectionConfig(callsign="RTH"))

    class FixedDateTime(datetime):
        @classmethod
        def utcnow(cls) -> datetime:  # type: ignore[override]
            return datetime(2025, 1, 2, 3, 4, 6)

    class FixedUUID:
        hex = "abcdefabcdefabcdefabcdefabcdefab"

    monkeypatch.setattr(
        "reticulum_telemetry_hub.atak_cot.tak_connector.datetime", FixedDateTime
    )
    monkeypatch.setattr(
        "reticulum_telemetry_hub.atak_cot.tak_connector.uuid.uuid4",
        lambda: FixedUUID(),
    )

    start_time = datetime(2025, 1, 2, 3, 4, 5)
    topic_id = "ops"
    content = "Hello team"
    identifier = connector._identifier_from_hash(b"\x01" * 8)
    timestamp_ms = int(start_time.timestamp() * 1000)
    uid_suffix = FixedUUID.hex[:6]
    uid = f"GeoChat.{identifier}-chat-{timestamp_ms}-{uid_suffix}"
    now = FixedDateTime.utcnow()
    stale_delta = max(connector.config.poll_interval_seconds, 1.0)
    stale = now + timedelta(seconds=stale_delta * 2)

    event = connector.build_chat_event(
        content=content,
        sender_label="Alpha",
        topic_id=topic_id,
        source_hash=b"\x01" * 8,
        timestamp=start_time,
    )

    expected_xml = (
        f'<event version="2.0" uid="{uid}" type="{connector.CHAT_EVENT_TYPE}" '
        f'how="{connector.CHAT_EVENT_HOW}" time="{now.replace(microsecond=0).isoformat()}Z" '
        f'start="{start_time.replace(microsecond=0).isoformat()}Z" '
        f'stale="{stale.replace(microsecond=0).isoformat()}Z">'
        '<point lat="0.0" lon="0.0" hae="0.0" ce="0.0" le="0.0" />'
        "<detail>"
        f'<__chat id="{topic_id}" chatroom="{topic_id}" senderCallsign="Alpha" groupOwner="false">'
        f'<chatgrp chatroom="{topic_id}" id="{topic_id}" uid0="{identifier}" uid1="" />'
        "<hierarchy>"
        '<group uid="TeamGroups" name="Teams">'
        f'<group uid="{topic_id}" name="{topic_id}">'
        f'<contact uid="{identifier}" name="Alpha" />'
        "</group>"
        "</group>"
        "</hierarchy>"
        "</__chat>"
        f'<link uid="{identifier}" type="{connector.CHAT_LINK_TYPE}" relation="p-p" />'
        f'<remarks source="BAO.F.Alpha.{identifier}" sourceID="{identifier}" to="{topic_id}" '
        f'time="{start_time.replace(microsecond=0).isoformat()}Z">{content}</remarks>'
        "</detail>"
        "</event>"
    )

    normalized_expected = ET.tostring(ET.fromstring(expected_xml), encoding="unicode")
    normalized_actual = ET.tostring(ET.fromstring(event.to_xml()), encoding="unicode")

    assert normalized_actual == normalized_expected
