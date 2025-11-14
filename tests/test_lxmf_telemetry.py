import time
from datetime import datetime

import LXMF
import RNS
from msgpack import packb, unpackb
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from reticulum_telemetry_hub.lxmf_telemetry import telemetry_controller as tc_mod
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance import Base
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import TelemetryController
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors import ConnectionMap
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_mapping import (
    sid_mapping,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.rns_transport import (
    RNSTransport,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.telemeter import Telemeter
import pytest

def test_deserialize_lxmf():
    with open("sample.bin", "rb") as f:
        tel_data = unpackb(f.read(), strict_map_key=False)

    tel = TelemetryController()._deserialize_telemeter(tel_data, "test")

    expected_order = [sid for sid in sid_mapping if sid in tel_data]

    assert [sensor.sid for sensor in tel.sensors] == expected_order
    assert len(tel.sensors) == len(expected_order)
    location = next(s for s in tel.sensors if hasattr(s, "latitude"))
    assert pytest.approx(location.latitude, rel=1e-6) == 44.657059
    assert pytest.approx(location.longitude, rel=1e-6) == -63.596294


def test_handle_command_stream_is_msgpack_encoded(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    tc_mod._engine = engine
    tc_mod.Session_cls = sessionmaker(bind=engine)

    controller = TelemetryController()

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
    dst = RNS.Destination(dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")

    with open("sample.bin", "rb") as f:
        tel_data = unpackb(f.read(), strict_map_key=False)

    packed = packb(tel_data, use_bin_type=True)
    message = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY: packed})
    assert controller.handle_message(message)

    command_msg = LXMF.LXMessage(src, dst)
    cmd = {TelemetryController.TELEMETRY_REQUEST: int(time.time())}

    reply = controller.handle_command(cmd, command_msg, dst)
    stream = reply.fields[LXMF.FIELD_TELEMETRY_STREAM]

    assert isinstance(stream, (bytes, bytearray))
    unpacked = unpackb(stream, strict_map_key=False)
    assert isinstance(unpacked, list)
    assert unpacked


def test_handle_message_stream_preserves_timestamp_and_sensors():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    tc_mod._engine = engine
    tc_mod.Session_cls = sessionmaker(bind=engine)

    controller = TelemetryController()

    src_identity = RNS.Identity()
    dst_identity = RNS.Identity()
    src = RNS.Destination(src_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
    dst = RNS.Destination(dst_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")

    with open("sample.bin", "rb") as f:
        tel_data = unpackb(f.read(), strict_map_key=False)

    packed_telemeter = packb(tel_data, use_bin_type=True)
    timestamp = 1_700_000_000
    peer_hash = bytes.fromhex("42" * 16)
    stream_payload = [peer_hash, timestamp, packed_telemeter, ["meta"]]
    stream = packb([stream_payload], use_bin_type=True)

    message = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY_STREAM: stream})

    assert controller.handle_message(message)

    with tc_mod.Session_cls() as ses:
        stored = ses.query(Telemeter).one()
        assert stored.time == datetime.fromtimestamp(timestamp)
        assert len(stored.sensors) > 0


def test_rns_transport_round_trip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    packed_payload = {
        "transport_enabled": True,
        "transport_identity": b"\x01" * 16,
        "transport_uptime": 4242,
        "traffic_rxb": 10_000,
        "traffic_txb": 20_000,
        "speed_rx": 128.5,
        "speed_tx": 256.75,
        "speed_rx_inst": 130.0,
        "speed_tx_inst": 260.0,
        "memory_used": 12_345_678,
        "interface_count": 2,
        "link_count": 7,
        "interfaces": [
            {"name": "if0", "state": "up"},
            {"name": "if1", "state": "down"},
        ],
        "path_table": [
            {"interface": "if0", "via": b"\xaa" * 8, "hash": b"\xbb" * 16, "hops": 1},
        ],
        "ifstats": {
            "rxb": 10_000,
            "txb": 20_000,
            "rxs": 500.0,
            "txs": 600.0,
            "interfaces": [
                {"name": "if0", "paths": 2},
                {"name": "if1", "paths": 0},
            ],
        },
    }

    telemeter = Telemeter(peer_dest="dest")
    sensor = RNSTransport()
    sensor.unpack(packed_payload)
    telemeter.sensors.append(sensor)

    with Session() as ses:
        ses.add(telemeter)
        ses.commit()

        stored = ses.query(RNSTransport).one()
        repacked = stored.pack()

    assert repacked["transport_identity"] == packed_payload["transport_identity"]
    assert repacked["interfaces"] == packed_payload["interfaces"]
    assert repacked["path_table"] == packed_payload["path_table"]
    assert repacked["ifstats"] == packed_payload["ifstats"]
    assert repacked["interface_count"] == packed_payload["interface_count"]


def test_connection_map_pack_unpack_round_trip():
    sensor = ConnectionMap()
    sensor.ensure_map("main", "Main Map")
    sensor.add_point(
        "main",
        "deadbeef",
        latitude=44.0,
        longitude=-63.0,
        altitude=10.0,
        point_type="peer",
        name="Gateway",
        signal_strength=-42,
        snr=12.5,
    )

    expected_payload = {
        "maps": {
            "main": {
                "label": "Main Map",
                "points": {
                    "deadbeef": {
                        "lat": 44.0,
                        "lon": -63.0,
                        "alt": 10.0,
                        "type": "peer",
                        "name": "Gateway",
                        "signal_strength": -42,
                        "snr": 12.5,
                    }
                },
            }
        }
    }

    packed = sensor.pack()
    assert packed == expected_payload

    unpacked = ConnectionMap()
    normalized = unpacked.unpack(packed)

    assert normalized == expected_payload
    assert len(unpacked.maps) == 1

    unpacked_map = unpacked.ensure_map("main")
    assert unpacked_map.label == "Main Map"
    assert len(unpacked_map.points) == 1

    point = unpacked_map.points[0]
    assert point.point_hash == "deadbeef"
    assert point.latitude == 44.0
    assert point.longitude == -63.0
    assert point.altitude == 10.0
    assert point.point_type == "peer"
    assert point.name == "Gateway"
    assert point.signals == {"signal_strength": -42, "snr": 12.5}

    # Updating the map label should modify the existing map entry.
    updated = unpacked.ensure_map("main", label="Updated Label")
    assert updated.label == "Updated Label"
