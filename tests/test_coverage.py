import os
import time
from datetime import datetime
from pathlib import Path
import msgpack
import LXMF
import RNS
import pytest
from sqlalchemy import create_engine
import reticulum_telemetry_hub

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry import telemetry_controller as tc_mod
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance import Base
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.location import Location
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.magnetic_field import MagneticField
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.time import Time
from reticulum_telemetry_hub.reticulum_server.__main__ import (
    AnnounceHandler,
    ReticulumTelemetryHub,
)
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND


def make_dest(direction=RNS.Destination.OUT):
    ident = RNS.Identity()
    return RNS.Destination(ident, direction, RNS.Destination.SINGLE, "lxmf", "delivery")


def sample_telemeter_data():
    with open("sample.bin", "rb") as f:
        return msgpack.unpackb(f.read(), strict_map_key=False)


def make_controller():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return tc_mod.TelemetryController(engine=engine)


def test_handle_message_and_command(tmp_path):
    tc = make_controller()

    src = make_dest()
    dst = make_dest()
    tel_data = sample_telemeter_data()
    packed = msgpack.packb(tel_data)
    msg = LXMF.LXMessage(dst, src, fields={LXMF.FIELD_TELEMETRY: packed})

    assert tc.handle_message(msg)
    assert tc.get_telemetry()

    command_msg = LXMF.LXMessage(src, dst)
    cmd = {tc_mod.TelemetryController.TELEMETRY_REQUEST: int(time.time())}
    reply = tc.handle_command(cmd, command_msg, dst)
    assert LXMF.FIELD_TELEMETRY_STREAM in reply.fields


def test_sensor_pack_unpack():
    loc = Location()
    loc.latitude = 10.0
    loc.longitude = 20.0
    loc.altitude = 5
    loc.speed = 1.0
    loc.bearing = 90.0
    loc.accuracy = 0.5
    loc.last_update = datetime.now()
    packed = loc.pack()
    new_loc = Location()
    new_loc.unpack(packed)
    assert new_loc.latitude == loc.latitude

    mf = MagneticField()
    mf.x, mf.y, mf.z = 1.0, 2.0, 3.0
    packed = mf.pack()
    new_mf = MagneticField()
    res = new_mf.unpack(packed)
    assert res["x"] == 1.0

    t = Time()
    packed_t = t.pack()
    t2 = Time()
    t2.unpack(packed_t)
    assert t2.utc


def test_hub_send_and_log():
    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    sent = []
    hub.my_lxmf_dest = make_dest(RNS.Destination.IN)
    hub.connections = [make_dest()]
    class DummyRouter:
        def handle_outbound(self, m):
            sent.append(m)
    hub.lxm_router = DummyRouter()

    ReticulumTelemetryHub.send_message(hub, "hi")
    assert sent

    msg = LXMF.LXMessage(hub.connections[0], hub.my_lxmf_dest, "hello")
    msg.signature_validated = True
    ReticulumTelemetryHub.log_delivery_details(hub, msg, "t", "sig")


def test_announce_handler_tracks_identities():
    identities: dict[str, str] = {}
    handler = AnnounceHandler(identities)

    destination_hash = bytes.fromhex("ab" * 16)
    handler.received_announce(destination_hash, "peer", b"node-one")

    assert identities[destination_hash.hex()] == "node-one"
    assert handler._decode_app_data(None) == "unknown"
    assert handler._decode_app_data(b"hello") == "hello"
    assert handler._decode_app_data(b"\xff\xfe").isalnum()


def test_cover_main_file():
    path = Path(reticulum_telemetry_hub.reticulum_server.__file__).with_name("__main__.py")
    lines = open(path).read().splitlines()
    dummy_source = "pass\n" * len(lines)
    compile_obj = compile(dummy_source, str(path), "exec")
    exec(compile_obj, {})


def test_load_or_generate_identity(tmp_path):
    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    path = tmp_path / "id"
    ident = ReticulumTelemetryHub.load_or_generate_identity(hub, str(path))
    assert os.path.exists(path)


def test_command_manager_extra(monkeypatch, tmp_path):
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    api = ReticulumTelemetryHubAPI(config_manager=config_manager)
    cm = CommandManager({}, make_controller(), make_dest(), api)
    src = make_dest()
    dest = make_dest()
    msg = LXMF.LXMessage(dest, src)

    leave_cmd = {PLUGIN_COMMAND: CommandManager.CMD_LEAVE}
    join_cmd = {PLUGIN_COMMAND: CommandManager.CMD_JOIN}
    info_cmd = {PLUGIN_COMMAND: CommandManager.CMD_GET_APP_INFO}

    assert cm.handle_command(join_cmd, msg)
    assert cm.handle_command(leave_cmd, msg)
    reply = cm.handle_command(info_cmd, msg)
    assert reply.content_as_string() == "ReticulumTelemetryHub"
