"""Runtime helpers for ReticulumTelemetryHub daemon services."""

from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Iterator, Mapping

import RNS

try:  # pragma: no cover - optional dependency
    from gpsdclient import GPSDClient  # type: ignore
except Exception:  # pragma: no cover - gpsdclient is optional
    GPSDClient = None  # type: ignore

from reticulum_telemetry_hub.atak_cot.tak_connector import TakConnector
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import (
    TelemeterManager,
)

if TYPE_CHECKING:
    from reticulum_telemetry_hub.reticulum_server.__main__ import (
        ReticulumTelemetryHub,
    )


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
                (
                    "Skipping daemon service "
                    f"'{self.name}' because the host does not provide "
                    "the required hardware/software"
                ),
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
        self._client_factory = client_factory or (
            lambda **kwargs: GPSDClient(**kwargs)
        )  # type: ignore[arg-type]
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
                (
                    "GPS daemon service could not obtain a location sensor; "
                    "aborting"
                ),
                RNS.LOG_WARNING,
            )
            return

        try:
            client = self._client_factory(host=self._host, port=self._port)
        except Exception as exc:
            RNS.log(
                (
                    "Unable to connect to gpsd on "
                    f"{self._host}:{self._port}: {exc}"
                ),
                RNS.LOG_ERROR,
            )
            return

        stream = self._iter_gps_stream(client)
        for payload in stream:
            if self._stop_event.is_set():
                break
            self._apply_gps_payload(sensor, payload)

    def _iter_gps_stream(
        self, client: GPSDClient
    ) -> Iterator[dict]:  # pragma: no cover - passthrough
        return client.dict_stream(convert_datetime=False)

    def _apply_gps_payload(self, sensor, payload: Mapping[str, Any]) -> None:
        lat = payload.get("lat")
        lon = payload.get("lon")
        if lat is None or lon is None:
            return
        sensor.latitude = float(lat)
        sensor.longitude = float(lon)
        sensor.altitude = self._coerce_float(
            payload.get("alt"), sensor.altitude
        )
        sensor.speed = self._coerce_float(
            payload.get("speed"), sensor.speed
        )
        sensor.bearing = self._coerce_float(
            payload.get("track"), sensor.bearing
        )
        sensor.accuracy = self._coerce_float(
            payload.get("eps"), sensor.accuracy
        )
        sensor.last_update = datetime.utcnow()

    @staticmethod
    def _coerce_float(
        value: Any, current: float | None, *, default: float = 0.0
    ) -> float:
        if value is None:
            return current if current is not None else default
        try:
            return float(value)
        except (TypeError, ValueError):
            return current if current is not None else default


class CotTelemetryService(HubService):
    """Scheduler that pushes location updates to a TAK endpoint."""

    def __init__(self, *, connector: TakConnector, interval: float) -> None:
        super().__init__(name="tak_cot")
        self._connector = connector
        self._interval = interval if interval > 0 else 1.0

    def is_supported(self) -> bool:
        return self._connector is not None and self._interval > 0

    def poll_interval(self) -> float:
        return self._interval

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                asyncio.run(self._connector.send_latest_location())
            except Exception as exc:  # pragma: no cover - defensive logging
                RNS.log(
                    f"TAK connector failed to send CoT update: {exc}",
                    RNS.LOG_ERROR,
                )
            self._stop_event.wait(self._interval)


def _gps_factory(hub: "ReticulumTelemetryHub") -> HubService:
    return GpsTelemetryService(telemeter_manager=hub.telemeter_manager)


def _cot_factory(hub: "ReticulumTelemetryHub") -> HubService:
    config_manager = hub.config_manager or HubConfigurationManager(
        storage_path=hub.storage_path
    )
    connector = hub.tak_connector
    if connector is None:
        connector = TakConnector(
            config=config_manager.tak_config,
            telemeter_manager=hub.telemeter_manager,
            telemetry_controller=hub.tel_controller,
        )
    interval = connector.config.poll_interval_seconds
    return CotTelemetryService(connector=connector, interval=interval)


SERVICE_FACTORIES: dict[
    str, Callable[["ReticulumTelemetryHub"], HubService]
] = {
    "gpsd": _gps_factory,
    "tak_cot": _cot_factory,
}
