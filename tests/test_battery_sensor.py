"""Tests for the Battery sensor compatibility helpers."""

from msgpack import packb

from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.battery import (
    Battery,
)


def test_battery_pack_hydrates_legacy_blob():
    sensor = Battery()
    legacy_payload = [82.345, True, 36.1]
    sensor.data = packb(legacy_payload, use_bin_type=True)

    packed = sensor.pack()

    assert packed == [82.3, True, 36.1]
    assert sensor.charge_percent == 82.3
    assert sensor.charging is True
    assert sensor.temperature == 36.1


def test_battery_pack_returns_raw_payload_when_unparsable():
    sensor = Battery()
    raw_bytes = b"\x01\x02\x03"
    sensor.data = raw_bytes

    packed = sensor.pack()

    assert packed == raw_bytes
    assert sensor.charge_percent is None
    assert sensor.charging is None
    assert sensor.temperature is None
