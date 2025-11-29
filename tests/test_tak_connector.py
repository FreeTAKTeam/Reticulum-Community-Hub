import asyncio
import time
from datetime import datetime

import pytest

from reticulum_telemetry_hub.atak_cot.tak_connector import TakConnector
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
    assert event.uid.startswith("HUB-")
    assert event.point.lat == pytest.approx(40.7128)
    assert event.point.lon == pytest.approx(-74.006)
    assert event.detail is not None
    assert event.detail.contact is not None
    assert event.detail.contact.callsign == "userhash1"
    assert event.start.startswith("2025-01-01T00:00:00")


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
    assert event.uid.startswith("HUB-aabbccdd")


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
    assert event.detail.contact is not None
    assert event.detail.contact.callsign == "Alpha"
    assert event.detail.group is not None
    assert event.detail.group.name == "ops"
    assert event.detail.remarks.startswith("[topic:ops] Hello team")


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
    assert event.detail.group is not None
    assert cfg["fts"]["CALLSIGN"] == "HUB"
    assert parse_flag is False


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
