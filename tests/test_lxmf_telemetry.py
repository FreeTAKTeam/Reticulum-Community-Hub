import struct
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import LXMF
import RNS
import pytest
from msgpack import packb, unpackb
from sqlalchemy.exc import OperationalError

from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors import (
    ConnectionMap,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.lxmf_propagation import (
    LXMFPropagation,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.location import (
    Location,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_LOCATION,
    SID_TIME,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_mapping import (
    sid_mapping,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.rns_transport import (
    RNSTransport,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.telemeter import Telemeter
from reticulum_telemetry_hub.reticulum_server.appearance import (
    build_telemetry_icon_appearance_payload,
)
from tests.factories import (
    build_complex_telemeter_payload,
    create_connection_map_sensor,
    create_lxmf_propagation_sensor,
    create_rns_transport_sensor,
)


def _make_config_manager(tmp_path: Path) -> HubConfigurationManager:
    """Create a minimal configuration manager for API-backed tests."""

    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "config.ini").write_text("[app]\nname = TelemetryTest\n")
    return HubConfigurationManager(storage_path=storage)


def _decode_stream_entries(stream_field):
    """Return telemetry stream entries regardless of encoding."""

    if isinstance(stream_field, (bytes, bytearray)):
        return unpackb(stream_field, strict_map_key=False)
    assert isinstance(stream_field, list)
    return stream_field


def test_deserialize_lxmf(telemetry_controller):
    with open("sample.bin", "rb") as f:
        tel_data = unpackb(f.read(), strict_map_key=False)

    tel = telemetry_controller._deserialize_telemeter(tel_data, "test")

    expected_order = [sid for sid in sid_mapping if sid in tel_data]

    assert [sensor.sid for sensor in tel.sensors] == expected_order
    assert len(tel.sensors) == len(expected_order)
    location = next(s for s in tel.sensors if hasattr(s, "latitude"))
    assert pytest.approx(location.latitude, rel=1e-6) == 44.657059
    assert pytest.approx(location.longitude, rel=1e-6) == -63.596294


def test_handle_command_stream_is_msgpack_encoded(
    telemetry_controller, session_factory
):
    controller = telemetry_controller
    Session = session_factory

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    timestamp = int(time.time())
    payload = build_complex_telemeter_payload(timestamp=timestamp)
    packed = packb(payload, use_bin_type=True)
    message = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY: packed})
    assert controller.handle_message(message)

    # Ensure data persisted before issuing the telemetry command.
    with Session() as ses:
        assert ses.query(Telemeter).count() == 1

    command_msg = LXMF.LXMessage(src, dst)
    cmd = {TelemetryController.TELEMETRY_REQUEST: int(time.time()) - 5}

    reply = controller.handle_command(cmd, command_msg, dst)
    stream = reply.fields[LXMF.FIELD_TELEMETRY_STREAM]
    unpacked = _decode_stream_entries(stream)
    assert isinstance(unpacked, list)
    assert len(unpacked) == 1

    peer_hash, timestamp, telemeter_blob = unpacked[0][:3]
    assert isinstance(peer_hash, (bytes, bytearray))
    assert unpacked[0][3] == build_telemetry_icon_appearance_payload(payload)
    round_trip_payload = unpackb(telemeter_blob, strict_map_key=False)
    assert round_trip_payload[SID_TIME] == pytest.approx(timestamp, rel=0)
    # Remaining sensors should match the original payload.
    round_trip_payload.pop(SID_TIME, None)
    expected_payload = dict(payload)
    expected_payload.pop(SID_TIME, None)
    assert round_trip_payload == expected_payload


def test_handle_message_stream_preserves_timestamp_and_sensors(
    telemetry_controller, session_factory
):
    controller = telemetry_controller
    Session = session_factory

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    with open("sample.bin", "rb") as f:
        tel_data = unpackb(f.read(), strict_map_key=False)

    sensor_timestamp = tel_data[SID_TIME]
    packed_telemeter = packb(tel_data, use_bin_type=True)
    timestamp = 1_700_000_000
    peer_hash = bytes.fromhex("42" * 16)
    stream_payload = [peer_hash, timestamp, packed_telemeter]
    stream = packb([stream_payload], use_bin_type=True)

    message = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY_STREAM: stream})

    assert controller.handle_message(message)

    with Session() as ses:
        stored = ses.query(Telemeter).one()
        assert stored.time == datetime.fromtimestamp(sensor_timestamp)
        assert len(stored.sensors) > 0


def test_handle_message_stream_without_sid_time_uses_entry_timestamp(
    telemetry_controller, session_factory
):
    controller = telemetry_controller
    Session = session_factory

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    timestamp = 1_700_000_000
    payload = build_complex_telemeter_payload()
    packed_telemeter = packb(payload, use_bin_type=True)
    peer_hash = bytes.fromhex("99" * 16)
    stream_payload = [peer_hash, timestamp, packed_telemeter]
    stream = packb([stream_payload], use_bin_type=True)

    message = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY_STREAM: stream})

    assert controller.handle_message(message)

    with Session() as ses:
        stored = ses.query(Telemeter).one()
        assert stored.time == datetime.fromtimestamp(timestamp)
        assert len(stored.sensors) > 0


def test_telemetry_session_retries_close_failed_sessions(
    telemetry_controller, monkeypatch
):
    telemetry_controller._SESSION_RETRIES = 2
    telemetry_controller._SESSION_BACKOFF = 0
    closed_sessions: list[bool] = []

    class FailingSession:
        def execute(self, _):
            raise OperationalError("SELECT 1", {}, Exception("locked"))

        def close(self):
            closed_sessions.append(True)

    monkeypatch.setattr(telemetry_controller, "_session_cls", lambda: FailingSession())

    with pytest.raises(OperationalError):
        telemetry_controller._acquire_session_with_retry()

    assert len(closed_sessions) == telemetry_controller._SESSION_RETRIES


def test_telemetry_request_filters_by_topic(tmp_path, telemetry_db_engine):
    api = ReticulumTelemetryHubAPI(config_manager=_make_config_manager(tmp_path))
    controller = TelemetryController(engine=telemetry_db_engine, api=api)

    topic = api.create_topic(Topic(topic_name="Ops", topic_path="/ops"))

    sender_identity = RNS.Identity()
    peer_identity = RNS.Identity()
    other_identity = RNS.Identity()

    sender_dest = sender_identity.hash.hex()
    peer_dest = peer_identity.hash.hex()
    other_dest = other_identity.hash.hex()

    api.subscribe_topic(topic.topic_id, destination=sender_dest)
    api.subscribe_topic(topic.topic_id, destination=peer_dest)

    timestamp = int(time.time())
    payload = build_complex_telemeter_payload(timestamp=timestamp)

    controller.save_telemetry(payload, peer_dest)
    controller.save_telemetry(payload, other_dest)

    src = RNS.Destination(
        sender_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    command_msg = LXMF.LXMessage(dst, src)
    cmd = {TelemetryController.TELEMETRY_REQUEST: int(time.time()) - 5, "TopicID": topic.topic_id}

    reply = controller.handle_command(cmd, command_msg, dst)
    stream = reply.fields[LXMF.FIELD_TELEMETRY_STREAM]
    unpacked = _decode_stream_entries(stream)
    assert len(unpacked) == 1
    assert unpacked[0][0] == bytes.fromhex(peer_dest)


def test_telemetry_request_denies_unsubscribed_sender(tmp_path, telemetry_db_engine):
    api = ReticulumTelemetryHubAPI(config_manager=_make_config_manager(tmp_path))
    controller = TelemetryController(engine=telemetry_db_engine, api=api)

    topic = api.create_topic(Topic(topic_name="Ops", topic_path="/ops"))

    sender_identity = RNS.Identity()
    peer_identity = RNS.Identity()

    peer_dest = peer_identity.hash.hex()

    api.subscribe_topic(topic.topic_id, destination=peer_dest)

    payload = build_complex_telemeter_payload(timestamp=int(time.time()))
    controller.save_telemetry(payload, peer_dest)

    src = RNS.Destination(
        sender_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    command_msg = LXMF.LXMessage(dst, src)
    cmd = {TelemetryController.TELEMETRY_REQUEST: int(time.time()) - 5, "TopicID": topic.topic_id}

    reply = controller.handle_command(cmd, command_msg, dst)
    assert reply.content_as_string().startswith("Telemetry request denied")


def test_humanize_returns_time_and_location_values(telemetry_controller):
    controller = telemetry_controller
    timestamp = 1_700_000_000
    location = Location()
    location.latitude = 44.657059
    location.longitude = -63.596294
    location.altitude = 120.5
    location.speed = 5.5
    location.bearing = 90.0
    location.accuracy = 2.5
    location.last_update = datetime.fromtimestamp(timestamp)
    payload = {
        SID_TIME: timestamp,
        SID_LOCATION: location.pack(),
    }
    readable = controller._humanize_telemetry(payload)
    time_value = readable["time"]
    assert time_value["timestamp"] == pytest.approx(timestamp)
    assert time_value["iso"] == datetime.fromtimestamp(timestamp).isoformat()
    location_value = readable["location"]
    assert pytest.approx(location_value["latitude"], rel=1e-6) == 44.657059
    assert pytest.approx(location_value["longitude"], rel=1e-6) == -63.596294
    assert pytest.approx(location_value["altitude"], rel=1e-6) == 120.5
    assert pytest.approx(location_value["speed"], rel=1e-6) == 5.5
    assert pytest.approx(location_value["bearing"], rel=1e-6) == 90.0
    assert pytest.approx(location_value["accuracy"], rel=1e-6) == 2.5
    assert location_value["last_update_timestamp"] == pytest.approx(timestamp)
    assert (
        location_value["last_update_iso"]
        == datetime.fromtimestamp(timestamp).isoformat()
    )


def test_handle_message_notifies_listener(telemetry_controller):
    events: list[tuple[dict, bytes | str | None, datetime | None]] = []

    def listener(payload: dict, peer_hash, timestamp: datetime | None) -> None:
        events.append((payload, peer_hash, timestamp))

    telemetry_controller.register_listener(listener)

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    location = Location()
    location.latitude = 50.0
    location.longitude = 15.0
    location.altitude = 10.0
    location.speed = 1.0
    location.bearing = 2.0
    location.accuracy = 0.5
    location.last_update = datetime(2025, 11, 29, 20, 36, 2)
    payload = {
        SID_LOCATION: location.pack(),
        SID_TIME: int(time.time()),
    }

    message = LXMF.LXMessage(
        dst, src, fields={LXMF.FIELD_TELEMETRY: packb(payload, use_bin_type=True)}
    )
    assert telemetry_controller.handle_message(message)

    assert events
    decoded, peer_hash, timestamp = events[0]
    assert decoded.get("location", {}).get("latitude") == pytest.approx(50.0)
    assert decoded.get("location", {}).get("longitude") == pytest.approx(15.0)
    assert peer_hash == src.hash
    assert timestamp is not None
    assert isinstance(timestamp, datetime)


def test_stream_ingest_followed_by_command_returns_valid_response(
    telemetry_controller, session_factory
):
    controller = telemetry_controller
    Session = session_factory

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    timestamp = int(time.time())
    sensor_timestamp = timestamp + 42
    payload = build_complex_telemeter_payload(timestamp=sensor_timestamp)
    packed_telemeter = packb(payload, use_bin_type=True)
    peer_hash = bytes.fromhex("24" * 16)
    stream_payload = [peer_hash, timestamp, packed_telemeter]
    stream = packb([stream_payload], use_bin_type=True)

    message = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY_STREAM: stream})

    assert controller.handle_message(message)

    with Session() as ses:
        stored = ses.query(Telemeter).one()
        assert stored.peer_dest == RNS.hexrep(peer_hash, False)
        assert stored.time == datetime.fromtimestamp(sensor_timestamp)

    command_msg = LXMF.LXMessage(src, dst)
    command = {TelemetryController.TELEMETRY_REQUEST: timestamp - 1}

    reply = controller.handle_command(command, command_msg, dst)
    assert reply is not None

    stream_response = reply.fields[LXMF.FIELD_TELEMETRY_STREAM]
    unpacked = _decode_stream_entries(stream_response)
    assert len(unpacked) == 1

    returned_peer_hash, returned_timestamp, blob = unpacked[0][:3]
    assert returned_peer_hash == peer_hash
    assert returned_timestamp == sensor_timestamp
    returned_payload = unpackb(blob, strict_map_key=False)
    assert returned_payload.pop(SID_TIME, None) == pytest.approx(
        sensor_timestamp, rel=0
    )
    expected_payload = dict(payload)
    expected_payload.pop(SID_TIME, None)
    assert returned_payload == expected_payload


def test_handle_command_omits_body_payload(telemetry_controller, session_factory):
    controller = telemetry_controller
    Session = session_factory

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    timestamp = int(time.time())
    payload = build_complex_telemeter_payload(timestamp=timestamp)
    packed_telemeter = packb(payload, use_bin_type=True)
    peer_hash = bytes.fromhex("24" * 16)
    stream_payload = [peer_hash, timestamp, packed_telemeter]
    stream = packb([stream_payload], use_bin_type=True)

    message = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY_STREAM: stream})

    assert controller.handle_message(message)

    with Session() as ses:
        assert ses.query(Telemeter).count() == 1

    command_msg = LXMF.LXMessage(src, dst)
    command = {TelemetryController.TELEMETRY_REQUEST: timestamp - 1}

    reply = controller.handle_command(command, command_msg, dst)

    assert reply is not None
    assert reply.fields.get(LXMF.FIELD_TELEMETRY_STREAM)
    assert not reply.content


def test_handle_command_accepts_sideband_collector_format(
    telemetry_controller, session_factory
):
    controller = telemetry_controller
    Session = session_factory

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    timestamp = int(time.time())
    sensor_timestamp = timestamp + 99
    payload = build_complex_telemeter_payload(timestamp=sensor_timestamp)
    packed_telemeter = packb(payload, use_bin_type=True)
    peer_hash = bytes.fromhex("24" * 16)
    stream_payload = [peer_hash, timestamp, packed_telemeter]
    stream = packb([stream_payload], use_bin_type=True)

    message = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY_STREAM: stream})
    assert controller.handle_message(message)

    with Session() as ses:
        assert ses.query(Telemeter).count() == 1

    command_msg = LXMF.LXMessage(src, dst)
    command = {TelemetryController.TELEMETRY_REQUEST: [timestamp - 1, True]}

    reply = controller.handle_command(command, command_msg, dst)
    assert reply is not None

    stream_response = reply.fields[LXMF.FIELD_TELEMETRY_STREAM]
    unpacked = _decode_stream_entries(stream_response)
    assert len(unpacked) == 1

    returned_peer_hash, returned_timestamp, blob = unpacked[0][:3]
    assert returned_peer_hash == peer_hash
    assert returned_timestamp == sensor_timestamp
    returned_payload = unpackb(blob, strict_map_key=False)
    assert returned_payload.pop(SID_TIME, None) == pytest.approx(
        sensor_timestamp, rel=0
    )
    expected_payload = dict(payload)
    expected_payload.pop(SID_TIME, None)
    assert returned_payload == expected_payload


def test_handle_command_accepts_string_numeric_request_key(
    telemetry_controller, session_factory
):
    controller = telemetry_controller
    Session = session_factory

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    timestamp = int(time.time())
    payload = build_complex_telemeter_payload(timestamp=timestamp)
    peer_dest = "aa" * 16
    controller.save_telemetry(payload, peer_dest)

    with Session() as ses:
        assert ses.query(Telemeter).count() == 1

    command_msg = LXMF.LXMessage(src, dst)
    command = {str(TelemetryController.TELEMETRY_REQUEST): timestamp - 1}

    reply = controller.handle_command(command, command_msg, dst)
    assert reply is not None

    stream_response = reply.fields[LXMF.FIELD_TELEMETRY_STREAM]
    unpacked = _decode_stream_entries(stream_response)
    assert len(unpacked) == 1
    assert unpacked[0][0] == bytes.fromhex(peer_dest)


def test_handle_command_accepts_string_numeric_request_key_with_leading_zero(
    telemetry_controller, session_factory
):
    controller = telemetry_controller
    Session = session_factory

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    timestamp = int(time.time())
    payload = build_complex_telemeter_payload(timestamp=timestamp)
    peer_dest = "aa" * 16
    controller.save_telemetry(payload, peer_dest)

    with Session() as ses:
        assert ses.query(Telemeter).count() == 1

    command_msg = LXMF.LXMessage(src, dst)
    command = {"01": timestamp - 1}

    reply = controller.handle_command(command, command_msg, dst)
    assert reply is not None

    stream_response = reply.fields[LXMF.FIELD_TELEMETRY_STREAM]
    unpacked = _decode_stream_entries(stream_response)
    assert len(unpacked) == 1
    assert unpacked[0][0] == bytes.fromhex(peer_dest)


def test_handle_command_returns_latest_snapshot_per_peer(
    telemetry_controller, session_factory
):
    controller = telemetry_controller
    Session = session_factory

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    peer_a = bytes.fromhex("aa" * 16)
    peer_b = bytes.fromhex("bb" * 16)
    t0 = int(time.time()) - 100

    def send_snapshot(
        peer_hash: bytes, timestamp: int, sensor_time: int | None = None
    ) -> None:
        telem_payload = build_complex_telemeter_payload(
            timestamp=sensor_time if sensor_time is not None else timestamp
        )
        stream_payload = [peer_hash, timestamp, packb(telem_payload, use_bin_type=True)]
        stream = packb([stream_payload], use_bin_type=True)
        message = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY_STREAM: stream})
        assert controller.handle_message(message)

    # Older snapshot for peer A, then a newer one, plus one for peer B
    send_snapshot(peer_a, t0)
    send_snapshot(peer_a, t0 + 10)
    send_snapshot(peer_b, t0 + 5)

    with Session() as ses:
        # Sanity check DB holds all three entries
        assert ses.query(Telemeter).count() == 3

    command_msg = LXMF.LXMessage(src, dst)
    command = {TelemetryController.TELEMETRY_REQUEST: 0}

    reply = controller.handle_command(command, command_msg, dst)
    stream_response = reply.fields[LXMF.FIELD_TELEMETRY_STREAM]
    unpacked = _decode_stream_entries(stream_response)

    assert len(unpacked) == 2  # one per peer
    by_peer = {}
    for entry in unpacked:
        peer_hash = entry[0]
        by_peer[peer_hash] = entry
    assert by_peer[peer_a][1] == t0 + 10
    assert by_peer[peer_b][1] == t0 + 5


def test_handle_message_round_trip_complex_sensors(
    telemetry_controller, session_factory
):
    controller = telemetry_controller
    Session = session_factory

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    payload = build_complex_telemeter_payload()
    message = LXMF.LXMessage(
        dst,
        src,
        fields={LXMF.FIELD_TELEMETRY: packb(payload, use_bin_type=True)},
    )

    assert controller.handle_message(message)

    with Session() as ses:
        stored = ses.query(Telemeter).one()
        serialized = controller._serialize_telemeter(stored)
        timestamp = serialized.pop(SID_TIME, None)
        assert timestamp == pytest.approx(int(stored.time.timestamp()), rel=0)
        assert serialized == payload


def test_rns_transport_round_trip(session_factory):
    Session = session_factory

    telemeter = Telemeter(peer_dest="dest")
    sensor = create_rns_transport_sensor()
    expected_payload = sensor.pack()
    assert expected_payload is not None
    telemeter.sensors.append(sensor)

    with Session() as ses:
        ses.add(telemeter)
        ses.commit()

        stored = ses.query(RNSTransport).one()
        repacked = stored.pack()

    assert repacked == expected_payload


def test_lxmf_propagation_round_trip(session_factory):
    Session = session_factory

    telemeter = Telemeter(peer_dest="dest")
    sensor = create_lxmf_propagation_sensor()
    expected_payload = sensor.pack()
    assert expected_payload is not None
    telemeter.sensors.append(sensor)

    with Session() as ses:
        ses.add(telemeter)
        ses.commit()

        stored = ses.query(LXMFPropagation).one()
        repacked = stored.pack()

    assert repacked == expected_payload
    assert set(repacked["peers"].keys()) == set(expected_payload["peers"].keys())


def test_connection_map_pack_unpack_round_trip(session_factory):
    Session = session_factory

    sensor = create_connection_map_sensor()
    expected_payload = sensor.pack()
    assert expected_payload is not None

    telemeter = Telemeter(peer_dest="dest")
    telemeter.sensors.append(sensor)

    with Session() as ses:
        ses.add(telemeter)
        ses.commit()

        stored = ses.query(ConnectionMap).one()
        repacked = stored.pack()

    assert repacked == expected_payload

    unpacked = ConnectionMap()
    normalized = unpacked.unpack(repacked)

    assert normalized == expected_payload
    assert len(unpacked.maps) == 2

    main_map = unpacked.ensure_map("main")
    assert main_map.label == "Main Map"
    assert len(main_map.points) == 1
    main_point = main_map.points[0]
    assert main_point.point_hash == "deadbeef"
    assert main_point.latitude == 44.0
    assert main_point.longitude == -63.0
    assert main_point.altitude == 10.0
    assert main_point.point_type == "peer"
    assert main_point.name == "Gateway"
    assert main_point.signals == {"signal_strength": -40, "snr": 12.5}

    backup_map = unpacked.ensure_map("backup")
    assert backup_map.label == "Backup Map"
    assert len(backup_map.points) == 1
    backup_point = backup_map.points[0]
    assert backup_point.point_hash == "feedface"
    assert backup_point.latitude == 45.0
    assert backup_point.longitude == -62.0
    assert backup_point.altitude == 12.0
    assert backup_point.point_type == "peer"
    assert backup_point.name == "Repeater"
    assert backup_point.signals == {"signal_strength": -55, "snr": 10.0}

    # Updating the map label should modify the existing map entry.
    updated = unpacked.ensure_map("main", label="Updated Label")
    assert updated.label == "Updated Label"


def test_controller_rejects_engine_and_db_path(telemetry_db_engine):
    with pytest.raises(ValueError):
        TelemetryController(engine=telemetry_db_engine, db_path="telemetry.db")


def test_get_telemetry_filters_end_time(telemetry_controller, session_factory):
    Session = session_factory

    newer = Telemeter(peer_dest="peer-newer")
    newer.time = datetime.now()
    older = Telemeter(peer_dest="peer-older")
    older.time = newer.time - timedelta(hours=1)

    with Session() as session:
        session.add_all([newer, older])
        session.commit()

    end_time = newer.time - timedelta(minutes=30)
    results = telemetry_controller.get_telemetry(end_time=end_time)

    assert all(telemeter.time <= end_time for telemeter in results)


def test_ingest_local_payload_ignores_empty_payload(
    telemetry_controller, session_factory
):
    Session = session_factory

    result = telemetry_controller.ingest_local_payload({}, peer_dest="local")

    assert result is None
    with Session() as session:
        assert session.query(Telemeter).count() == 0


def test_handle_message_stream_skips_invalid_entries(
    telemetry_controller, session_factory
):
    controller = telemetry_controller
    Session = session_factory

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    invalid_entries = [
        {"peer": "missing tuple"},
        ["not-bytes", 123, {"sid": 1}],
        [b"\x01\x02", "not-a-number", {"sid": 2}],
        [b"\x03\x04", 123, None],
    ]

    message = LXMF.LXMessage(
        dst, src, fields={LXMF.FIELD_TELEMETRY_STREAM: invalid_entries}
    )

    assert controller.handle_message(message)

    with Session() as session:
        assert session.query(Telemeter).count() == 0


def test_handle_command_rejects_empty_sideband_request(
    telemetry_controller, session_factory
):
    controller = telemetry_controller
    Session = session_factory

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    with Session() as session:
        session.query(Telemeter).delete()
        session.commit()

    command_msg = LXMF.LXMessage(src, dst)
    command = {TelemetryController.TELEMETRY_REQUEST: []}

    assert controller.handle_command(command, command_msg, dst) is None


def test_handle_command_rejects_non_numeric_timestamp(telemetry_controller):
    controller = telemetry_controller

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    command_msg = LXMF.LXMessage(src, dst)
    command = {TelemetryController.TELEMETRY_REQUEST: "invalid"}

    with pytest.raises(TypeError):
        controller.handle_command(command, command_msg, dst)


def test_handle_command_returns_none_without_request(telemetry_controller):
    controller = telemetry_controller

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(
        src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dst = RNS.Destination(
        dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    command_msg = LXMF.LXMessage(src, dst)

    assert controller.handle_command({}, command_msg, dst) is None


def test_humanize_handles_unknown_sensor(telemetry_controller):
    controller = telemetry_controller

    readable = controller._humanize_telemetry({999: "raw"})

    assert readable["sid_999"] == "raw"


def test_extract_timestamp_rejects_invalid_iso(telemetry_controller):
    controller = telemetry_controller

    timestamp = controller._extract_timestamp({"time": {"iso": "not-a-datetime"}})

    assert timestamp is None


def test_deserialize_skips_none_sensor_payload(telemetry_controller):
    controller = telemetry_controller

    telemeter = controller._deserialize_telemeter({SID_TIME: 1, SID_LOCATION: None})

    assert len(telemeter.sensors) == 1
    assert telemeter.sensors[0].sid == SID_TIME


def test_peer_hash_bytes_handles_invalid_inputs(telemetry_controller):
    controller = telemetry_controller

    missing = Telemeter(peer_dest="   ")
    odd_length = Telemeter(peer_dest="abc")
    invalid_hex = Telemeter(peer_dest="zz")

    assert controller._peer_hash_bytes(missing) is None
    assert controller._peer_hash_bytes(odd_length) is None
    assert controller._peer_hash_bytes(invalid_hex) is None


def test_location_pack_strips_invalid_altitude_sentinel():
    """Very large altitude values should be treated as 'no altitude'."""

    sensor = Location()
    sensor.latitude = 1.0
    sensor.longitude = 2.0
    sensor.altitude = 42_949_672.95
    sensor.speed = 0.0
    sensor.bearing = 0.0
    sensor.accuracy = 0.0
    sensor.last_update = datetime.fromtimestamp(1_700_000_000)

    packed = sensor.pack()
    altitude_raw = struct.unpack("!I", packed[2])[0]
    assert altitude_raw == 0


def test_concurrent_telemetry_writes(tmp_path):
    db_path = tmp_path / "telemetry_threads.db"
    controller = TelemetryController(db_path=db_path)

    worker_count = 12
    iterations = 5
    errors: list[Exception] = []
    barrier = threading.Barrier(worker_count)

    def worker(index: int):
        try:
            barrier.wait()
            for j in range(iterations):
                payload = {SID_TIME: int(time.time()) + j}
                controller.save_telemetry(payload, f"peer-{index}")
        except Exception as exc:  # pragma: no cover - defensive capture
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(worker_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors

    with controller._session_scope() as session:
        assert session.query(Telemeter).count() == worker_count * iterations
    controller._engine.dispose()
