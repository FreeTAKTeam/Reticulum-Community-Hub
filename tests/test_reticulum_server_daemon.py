import time

from reticulum_telemetry_hub.reticulum_server import services
from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub


class DummyService(services.HubService):
    def __init__(self, *, supported: bool):
        super().__init__(name="dummy")
        self._supported = supported
        self.started = False

    def is_supported(self) -> bool:
        return self._supported

    def _run(self) -> None:
        self.started = True
        self._stop_event.wait(0.1)


def test_daemon_sampler_collects_local_telemetry(tmp_path):
    hub = ReticulumTelemetryHub(
        "Daemon",
        str(tmp_path),
        tmp_path / "identity",
        hub_telemetry_interval=0.01,
    )

    try:
        hub.start_daemon_workers()
        time.sleep(0.05)
        hub.stop_daemon_workers()
        stored = hub.tel_controller.get_telemetry()
        assert stored, "Sampler did not persist telemetry in daemon mode"
    finally:
        hub.shutdown()


def test_daemon_service_gating(monkeypatch, tmp_path):
    hub = ReticulumTelemetryHub(
        "Daemon",
        str(tmp_path),
        tmp_path / "identity",
        hub_telemetry_interval=0.01,
    )

    unsupported = DummyService(supported=False)
    supported = DummyService(supported=True)

    monkeypatch.setitem(
        services.SERVICE_FACTORIES,
        "unsupported",
        lambda hub: unsupported,
    )
    monkeypatch.setitem(
        services.SERVICE_FACTORIES,
        "supported",
        lambda hub: supported,
    )

    try:
        hub.start_daemon_workers(services=["unsupported", "supported"])
        assert "supported" in hub._active_services
        assert supported.started
        assert "unsupported" not in hub._active_services
    finally:
        hub.stop_daemon_workers()
        hub.shutdown()
