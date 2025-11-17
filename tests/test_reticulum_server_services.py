import pytest

from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import TelemeterManager
from reticulum_telemetry_hub.reticulum_server import services


def _make_service(monkeypatch, payloads):
    manager = TelemeterManager(config_manager=None)
    svc = services.GpsTelemetryService(
        telemeter_manager=manager,
        client_factory=lambda **_: object(),
    )
    monkeypatch.setattr(svc, "_iter_gps_stream", lambda client: iter(payloads))
    return svc, manager


def test_gps_service_populates_location_sensor(monkeypatch):
    payloads = [
        {"lat": None, "lon": 20.0},
        {"lat": 42.1234, "lon": -71.9876, "alt": "12.5", "speed": 3.2, "track": 180, "eps": 5},
    ]
    service, manager = _make_service(monkeypatch, payloads)

    service._run()

    sensor = manager.get_sensor("location")
    assert sensor is not None
    assert pytest.approx(sensor.latitude, rel=1e-6) == 42.1234
    assert pytest.approx(sensor.longitude, rel=1e-6) == -71.9876
    assert sensor.altitude == 12.5
    assert sensor.speed == 3.2
    assert sensor.bearing == 180.0
    assert sensor.accuracy == 5.0
    assert sensor.last_update is not None
    assert sensor.pack() is not None


def test_gps_service_preserves_previous_values(monkeypatch):
    payloads = [
        {"lat": 1.0, "lon": 2.0, "speed": 7.5},
        {"lat": 3.0, "lon": 4.0},
    ]
    service, manager = _make_service(monkeypatch, payloads)

    service._run()

    sensor = manager.get_sensor("location")
    assert sensor is not None
    # Most recent coordinates should win, but missing ancillary readings fall back to existing values.
    assert sensor.latitude == 3.0
    assert sensor.longitude == 4.0
    assert sensor.speed == 7.5
    assert sensor.altitude == 0.0
    assert sensor.bearing == 0.0
    assert sensor.accuracy == 0.0
