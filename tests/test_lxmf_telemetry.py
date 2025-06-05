from msgpack import unpackb
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import TelemetryController
import pytest

def test_deserialize_lxmf():
    with open("sample.bin", "rb") as f:
        tel_data = unpackb(f.read(), strict_map_key=False)

    tel = TelemetryController()._deserialize_telemeter(tel_data, "test")

    assert len(tel.sensors) == 2
    location = next(s for s in tel.sensors if hasattr(s, "latitude"))
    assert pytest.approx(location.latitude, rel=1e-6) == 44.657059
    assert pytest.approx(location.longitude, rel=1e-6) == -63.596294
