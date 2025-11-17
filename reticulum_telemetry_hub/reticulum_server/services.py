"""Runtime helpers for ReticulumTelemetryHub daemon services."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterator

import RNS

try:  # pragma: no cover - optional dependency
    from gpsdclient import GPSDClient  # type: ignore
except Exception:  # pragma: no cover - gpsdclient is optional
    GPSDClient = None  # type: ignore

from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import TelemeterManager


@dataclass
class HubService:
    """Base class for long running Reticulum telemetry services."""

    name: str

    def __post_init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        if self._thread is not None:
            return False
        if not self.is_supported():
            RNS.log(
                f"Skipping daemon service '{self.name}' because the host does not provide the required hardware/software",
                RNS.LOG_INFO,
            )
            return False
        self._thread = threading.Thread(target=self._run_wrapper, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join()
        self._thread = None
        self._stop_event.clear()

    # ------------------------------------------------------------------
    # overridable hooks
    # ------------------------------------------------------------------
    def is_supported(self) -> bool:  # pragma: no cover - trivial default
        return True

    def poll_interval(self) -> float:  # pragma: no cover - trivial default
        return 1.0

    def _run(self) -> None:  # pragma: no cover - interface method
        raise NotImplementedError

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _run_wrapper(self) -> None:
        try:
            self._run()
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Daemon service '{self.name}' crashed: {exc}",
                RNS.LOG_ERROR,
            )
        finally:
            self._thread = None
            self._stop_event.clear()


class GpsTelemetryService(HubService):
    """GPS backed telemetry mutator that enriches location sensors."""

    def __init__(
        self,
        *,
        telemeter_manager: TelemeterManager,
        client_factory: Callable[..., GPSDClient] | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        super().__init__(name="gpsd")
        self._telemeter_manager = telemeter_manager
        self._client_factory = client_factory or (lambda **kwargs: GPSDClient(**kwargs))  # type: ignore[arg-type]
        self._host = host or os.getenv("RTH_GPSD_HOST", "127.0.0.1")
        raw_port = os.getenv("RTH_GPSD_PORT")
        self._port = int(raw_port) if raw_port is not None else (port or 2947)

    def is_supported(self) -> bool:
        return GPSDClient is not None and self._telemeter_manager is not None

    def _run(self) -> None:
        manager = self._telemeter_manager
        if manager is None:
            return

        # Ensure the location sensor exists before polling GPS data.
        manager.enable_sensor("location")
        sensor = manager.get_sensor("location")
        if sensor is None:
            RNS.log(
                "GPS daemon service could not obtain a location sensor; aborting",
                RNS.LOG_WARNING,
            )
            return

        try:
            client = self._client_factory(host=self._host, port=self._port)
        except Exception as exc:
            RNS.log(f"Unable to connect to gpsd on {self._host}:{self._port}: {exc}", RNS.LOG_ERROR)
            return

        stream = self._iter_gps_stream(client)
        for payload in stream:
            if self._stop_event.is_set():
                break
            lat = payload.get("lat")
            lon = payload.get("lon")
            if lat is None or lon is None:
                continue
            sensor.latitude = lat
            sensor.longitude = lon
            if payload.get("alt") is not None:
                sensor.altitude = payload["alt"]
            if payload.get("speed") is not None:
                sensor.speed = payload["speed"]
            sensor.last_update = datetime.utcnow()

    def _iter_gps_stream(self, client: GPSDClient) -> Iterator[dict]:  # pragma: no cover - passthrough
        return client.dict_stream(convert_datetime=False)


def _gps_factory(hub: "ReticulumTelemetryHub") -> HubService:
    return GpsTelemetryService(telemeter_manager=hub.telemeter_manager)


SERVICE_FACTORIES: dict[str, Callable[["ReticulumTelemetryHub"], HubService]] = {
    "gpsd": _gps_factory,
}
