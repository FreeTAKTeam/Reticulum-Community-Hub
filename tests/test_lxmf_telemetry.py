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
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_mapping import (
    sid_mapping,
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
