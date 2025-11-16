import time
from datetime import datetime

import LXMF
import RNS
import pytest
from msgpack import packb, unpackb

from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import TelemetryController
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors import ConnectionMap
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.lxmf_propagation import (
    LXMFPropagation,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_mapping import (
    sid_mapping,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.rns_transport import (
    RNSTransport,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.telemeter import Telemeter
from tests.factories import (
    build_complex_telemeter_payload,
    create_connection_map_sensor,
    create_lxmf_propagation_sensor,
    create_rns_transport_sensor,
)

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


def test_handle_command_stream_is_msgpack_encoded(telemetry_controller, session_factory):
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
    packed = packb(payload, use_bin_type=True)
    message = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY: packed})
    assert controller.handle_message(message)

    # Ensure data persisted before issuing the telemetry command.
    with Session() as ses:
        assert ses.query(Telemeter).count() == 1

    command_msg = LXMF.LXMessage(src, dst)
    cmd = {TelemetryController.TELEMETRY_REQUEST: int(time.time())}

    reply = controller.handle_command(cmd, command_msg, dst)
    stream = reply.fields[LXMF.FIELD_TELEMETRY_STREAM]

    assert isinstance(stream, (bytes, bytearray))
    unpacked = unpackb(stream, strict_map_key=False)
    assert isinstance(unpacked, list)
    assert len(unpacked) == 1

    peer_hash, timestamp, telemeter_blob, metadata = unpacked[0]
    assert isinstance(peer_hash, (bytes, bytearray))
    assert isinstance(metadata, list)
    round_trip_payload = unpackb(telemeter_blob, strict_map_key=False)
    assert round_trip_payload == payload


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

    packed_telemeter = packb(tel_data, use_bin_type=True)
    timestamp = 1_700_000_000
    peer_hash = bytes.fromhex("42" * 16)
    stream_payload = [peer_hash, timestamp, packed_telemeter, ["meta"]]
    stream = packb([stream_payload], use_bin_type=True)

    message = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY_STREAM: stream})

    assert controller.handle_message(message)

    with Session() as ses:
        stored = ses.query(Telemeter).one()
        assert stored.time == datetime.fromtimestamp(timestamp)
        assert len(stored.sensors) > 0


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

    payload = build_complex_telemeter_payload()
    packed_telemeter = packb(payload, use_bin_type=True)
    timestamp = int(time.time())
    peer_hash = bytes.fromhex("24" * 16)
    stream_payload = [peer_hash, timestamp, packed_telemeter, ["meta"]]
    stream = packb([stream_payload], use_bin_type=True)

    message = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY_STREAM: stream})

    assert controller.handle_message(message)

    with Session() as ses:
        stored = ses.query(Telemeter).one()
        assert stored.peer_dest == RNS.hexrep(peer_hash, False)

    command_msg = LXMF.LXMessage(src, dst)
    command = {TelemetryController.TELEMETRY_REQUEST: timestamp - 1}

    reply = controller.handle_command(command, command_msg, dst)
    assert reply is not None

    stream_response = reply.fields[LXMF.FIELD_TELEMETRY_STREAM]
    unpacked = unpackb(stream_response, strict_map_key=False)
    assert len(unpacked) == 1

    returned_peer_hash, returned_timestamp, blob, metadata = unpacked[0]
    assert returned_peer_hash == peer_hash
    assert returned_timestamp == timestamp
    assert isinstance(metadata, list)
    assert unpackb(blob, strict_map_key=False) == payload


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

    payload = build_complex_telemeter_payload()
    packed_telemeter = packb(payload, use_bin_type=True)
    timestamp = int(time.time())
    peer_hash = bytes.fromhex("24" * 16)
    stream_payload = [peer_hash, timestamp, packed_telemeter, ["meta"]]
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
    unpacked = unpackb(stream_response, strict_map_key=False)
    assert len(unpacked) == 1

    returned_peer_hash, returned_timestamp, blob, metadata = unpacked[0]
    assert returned_peer_hash == peer_hash
    assert returned_timestamp == timestamp
    assert isinstance(metadata, list)
    assert unpackb(blob, strict_map_key=False) == payload


def test_handle_message_round_trip_complex_sensors(telemetry_controller, session_factory):
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
