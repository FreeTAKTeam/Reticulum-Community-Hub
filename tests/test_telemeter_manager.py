from __future__ import annotations

from dataclasses import dataclass

from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor import Sensor
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_BATTERY,
    SID_INFORMATION,
    SID_LOCATION,
    SID_TIME,
)
from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import TelemeterManager


def _make_config_manager(tmp_path, telemetry_contents: str) -> HubConfigurationManager:
    storage = tmp_path / "storage"
    storage.mkdir()
    telemetry_file = storage / "telemetry.ini"
    telemetry_file.write_text(telemetry_contents)
    reticulum_cfg = tmp_path / "reticulum.ini"
    reticulum_cfg.write_text("[reticulum]\n")
    lxmf_cfg = tmp_path / "lxmf.ini"
    lxmf_cfg.write_text("[lxmf]\n")
    return HubConfigurationManager(
        storage_path=storage,
        reticulum_config_path=reticulum_cfg,
        lxmf_router_config_path=lxmf_cfg,
    )


def test_manager_synthesizes_static_location_and_information(tmp_path):
    cfg_text = (
        "[telemetry]\n"
        "synthesize_location = true\n"
        "location_latitude = 44.0\n"
        "location_longitude = -63.0\n"
        "location_altitude = 10.0\n"
        "location_accuracy = 5.0\n"
        "static_information = Callsign RTH\n"
    )
    config_manager = _make_config_manager(tmp_path, cfg_text)
    manager = TelemeterManager(config_manager=config_manager)

    payload = manager.snapshot()

    assert SID_TIME in payload
    assert SID_INFORMATION in payload
    info_sensor = manager.get_sensor("information")
    assert info_sensor is not None
    assert getattr(info_sensor, "contents") == "Callsign RTH"

    assert SID_LOCATION in payload
    location_sensor = manager.get_sensor("location")
    assert location_sensor is not None
    assert getattr(location_sensor, "latitude") == 44.0
    assert getattr(location_sensor, "longitude") == -63.0
    assert getattr(location_sensor, "altitude") == 10.0
    assert getattr(location_sensor, "accuracy") == 5.0


def test_manager_respects_sensor_enable_flags(tmp_path):
    cfg_text = "[telemetry]\nenable_battery = no\n"
    config_manager = _make_config_manager(tmp_path, cfg_text)
    manager = TelemeterManager(config_manager=config_manager)

    battery = manager.get_sensor("battery")
    assert battery is not None
    setattr(battery, "charge_percent", 50.0)

    payload = manager.snapshot()
    assert SID_BATTERY not in payload

    manager.enable_sensor("battery")
    payload = manager.snapshot()
    assert SID_BATTERY in payload


def test_manager_plugins_extend_snapshot(tmp_path):
    manager = TelemeterManager()

    class PluginSensor(Sensor):
        def __init__(self) -> None:
            super().__init__(stale_time=1)
            self.sid = 0xFE

        def pack(self):  # type: ignore[override]
            return {"plugin": True}

    @dataclass
    class DummyPlugin:
        injected_sid: int = 0xFD

        def setup(self, manager: TelemeterManager) -> None:
            manager.add_sensor(PluginSensor())
            manager.add_snapshot_mutator(
                lambda _tele, payload: payload.setdefault(self.injected_sid, "mutated")
            )

    manager.register_plugin(DummyPlugin())

    snapshot = manager.snapshot()
    assert 0xFE in snapshot
    assert snapshot[0xFE] == {"plugin": True}
    assert 0xFD in snapshot
    assert snapshot[0xFD] == "mutated"
