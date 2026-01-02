"""Runtime helpers for ReticulumTelemetryHub daemon services."""

from __future__ import annotations

import asyncio
import time
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Iterator, Mapping

import RNS

try:  # pragma: no cover - optional dependency
    from gpsdclient import GPSDClient  # type: ignore
except ImportError:  # pragma: no cover - gpsdclient is optional
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


def _utcnow() -> datetime:
    """
    Return a timezone-aware UTC timestamp with the tzinfo stripped.

    Returns:
        datetime: The current UTC timestamp without timezone information.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class HubService:
    """Base class for long running Reticulum telemetry services."""

    name: str

    def __post_init__(self) -> None:
        """
        Initialize thread synchronization primitives for the service.

        Sets up the stop event and placeholder thread handle used by the
        lifecycle helpers.
        """
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        """
        Start the service in a background thread if supported.

        Returns:
            bool: ``True`` if the service was started; ``False`` if it was
            already running or unsupported on this host.
        """
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
        """Stop the background thread and reset lifecycle flags."""
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
        """
        Determine whether the service can run on the current host.

        Returns:
            bool: ``True`` when the dependencies are available, otherwise
            ``False``.
        """
        return True

    def poll_interval(self) -> float:  # pragma: no cover - trivial default
        """
        Return the preferred polling interval in seconds.

        Returns:
            float: Number of seconds to wait between iterations.
        """
        return 1.0

    def _run(self) -> None:  # pragma: no cover - interface method
        """
        Execute the service logic.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _run_wrapper(self) -> None:
        """Wrap ``_run`` with crash logging and cleanup handling."""
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
        """
        Initialize the gpsd-backed telemetry service.

        Args:
            telemeter_manager (TelemeterManager): Manager providing the location
                sensor to update.
            client_factory (Callable[..., GPSDClient] | None): Factory used to
                create GPSD clients. Defaults to ``GPSDClient`` when available.
            host (str | None): gpsd host, defaults to ``127.0.0.1``.
            port (int | None): gpsd TCP port, defaults to ``2947``.
        """
        super().__init__(name="gpsd")
        self._telemeter_manager = telemeter_manager
        self._client_factory = client_factory or (
            lambda **kwargs: GPSDClient(**kwargs)
        )  # type: ignore[arg-type]
        self._host = host or "127.0.0.1"
        self._port = port or 2947

    def is_supported(self) -> bool:
        """
        Check whether gpsd dependencies are present.

        Returns:
            bool: ``True`` when gpsdclient is available and a telemeter manager
            has been configured.
        """
        return GPSDClient is not None and self._telemeter_manager is not None

    def _run(self) -> None:
        """Continuously poll gpsd and apply updates to the location sensor."""
        manager = self._telemeter_manager
        if manager is None:
            return

        # Ensure the location sensor exists before polling GPS data.
        manager.enable_sensor("location")
        sensor = manager.get_sensor("location")
        if sensor is None:
            RNS.log(
                ("GPS daemon service could not obtain a location sensor; " "aborting"),
                RNS.LOG_WARNING,
            )
            return

        try:
            client = self._client_factory(host=self._host, port=self._port)
        except Exception as exc:
            RNS.log(
                ("Unable to connect to gpsd on " f"{self._host}:{self._port}: {exc}"),
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
        """
        Yield GPS samples from the gpsdclient stream.

        Args:
            client (GPSDClient): Connected gpsd client.

        Returns:
            Iterator[dict]: Iterable of GPS payload dictionaries.
        """
        return client.dict_stream(convert_datetime=False)

    def _apply_gps_payload(self, sensor, payload: Mapping[str, Any]) -> None:
        """
        Map gpsd payload fields onto the hub's location sensor.

        Args:
            sensor: Location sensor instance to mutate.
            payload (Mapping[str, Any]): Raw gpsd payload dictionary.
        """
        lat = payload.get("lat")
        lon = payload.get("lon")
        if lat is None or lon is None:
            return
        sensor.latitude = float(lat)
        sensor.longitude = float(lon)
        sensor.altitude = self._coerce_float(payload.get("alt"), sensor.altitude)
        sensor.speed = self._coerce_float(payload.get("speed"), sensor.speed)
        sensor.bearing = self._coerce_float(payload.get("track"), sensor.bearing)
        sensor.accuracy = self._coerce_float(payload.get("eps"), sensor.accuracy)
        sensor.last_update = _utcnow()

    @staticmethod
    def _coerce_float(
        value: Any, current: float | None, *, default: float = 0.0
    ) -> float:
        """
        Convert a value to float, falling back to the current or default value.

        Args:
            value (Any): Candidate value to convert.
            current (float | None): Current sensor value to preserve on failure.
            default (float): Default when neither the value nor current is set.

        Returns:
            float: Coerced float value.
        """
        if value is None:
            return current if current is not None else default
        try:
            return float(value)
        except (TypeError, ValueError):
            return current if current is not None else default


class CotTelemetryService(HubService):
    """Scheduler that pushes location updates to a TAK endpoint."""

    def __init__(
        self,
        *,
        connector: TakConnector,
        interval: float | None,
        keepalive_interval: float | None = None,
        ping_interval: float | None = None,
    ) -> None:
        """
        Initialize the TAK connector scheduler.

        Args:
            connector (TakConnector): Connected TAK connector instance.
            interval (float | None): Desired CoT send interval in seconds.
            keepalive_interval (float | None): Override for keepalive cadence.
            ping_interval (float | None): Override for ping cadence.
        """
        super().__init__(name="tak_cot")
        self._connector = connector
        connector_interval = connector.config.poll_interval_seconds
        default_keepalive = connector.config.keepalive_interval_seconds
        self._interval = interval if interval and interval > 0 else connector_interval
        if self._interval <= 0:
            self._interval = 1.0
        resolved_keepalive = (
            keepalive_interval
            if keepalive_interval is not None and keepalive_interval > 0
            else default_keepalive
        )
        self._keepalive_interval = (
            resolved_keepalive if resolved_keepalive > 0 else 60.0
        )
        self._ping_interval = (
            ping_interval
            if ping_interval is not None and ping_interval > 0
            else self._keepalive_interval
        )

    def is_supported(self) -> bool:
        """
        Confirm the TAK connector is configured.

        Returns:
            bool: ``True`` when the connector exists and the interval is valid.
        """
        return self._connector is not None and self._interval > 0

    def poll_interval(self) -> float:
        """
        Return the configured CoT polling interval.

        Returns:
            float: Seconds between location pushes.
        """
        return self._interval

    def _run(self) -> None:
        """Send periodic location updates, keepalives, and pings."""
        last_keepalive = time.monotonic() - self._keepalive_interval
        last_location = time.monotonic() - self._interval
        last_ping = time.monotonic() - self._ping_interval
        while not self._stop_event.is_set():
            now = time.monotonic()
            if now - last_ping >= self._ping_interval:
                try:
                    asyncio.run(self._connector.send_ping())
                    last_ping = time.monotonic()
                except Exception as exc:  # pragma: no cover - defensive logging
                    RNS.log(
                        f"TAK connector failed to send hello keepalive: {exc}",
                        RNS.LOG_ERROR,
                    )
            if now - last_keepalive >= self._keepalive_interval:
                try:
                    asyncio.run(self._connector.send_keepalive())
                    last_keepalive = time.monotonic()
                except Exception as exc:  # pragma: no cover - defensive logging
                    RNS.log(
                        f"TAK connector failed to send keepalive: {exc}",
                        RNS.LOG_ERROR,
                    )
            if now - last_location >= self._interval:
                try:
                    asyncio.run(self._connector.send_latest_location())
                    last_location = time.monotonic()
                except Exception as exc:  # pragma: no cover - defensive logging
                    RNS.log(
                        f"TAK connector failed to send CoT update: {exc}",
                        RNS.LOG_ERROR,
                    )
            remaining_keepalive = self._keepalive_interval - (
                time.monotonic() - last_keepalive
            )
            remaining_location = self._interval - (time.monotonic() - last_location)
            remaining_ping = self._ping_interval - (time.monotonic() - last_ping)
            wait_time = max(
                min(remaining_keepalive, remaining_location, remaining_ping), 0.01
            )
            self._stop_event.wait(wait_time)


def _gps_factory(hub: "ReticulumTelemetryHub") -> HubService:
    """
    Build the GPS daemon service from hub configuration.

    Args:
        hub (ReticulumTelemetryHub): Active hub instance.

    Returns:
        HubService: Configured GPS telemetry service.
    """
    config_manager = hub.config_manager or HubConfigurationManager(
        storage_path=hub.storage_path
    )
    runtime_config = config_manager.runtime_config
    return GpsTelemetryService(
        telemeter_manager=hub.telemeter_manager,
        host=runtime_config.gpsd_host,
        port=runtime_config.gpsd_port,
    )


def _cot_factory(hub: "ReticulumTelemetryHub") -> HubService:
    """
    Build the TAK CoT scheduler from hub configuration.

    Args:
        hub (ReticulumTelemetryHub): Active hub instance.

    Returns:
        HubService: Configured CoT telemetry service.
    """
    config_manager = hub.config_manager or HubConfigurationManager(
        storage_path=hub.storage_path
    )
    connector = hub.tak_connector
    if connector is None:
        connector = TakConnector(
            config=config_manager.tak_config,
            telemeter_manager=hub.telemeter_manager,
            telemetry_controller=hub.tel_controller,
            identity_lookup=hub._lookup_identity_label,
        )
    interval = connector.config.poll_interval_seconds
    keepalive = connector.config.keepalive_interval_seconds
    return CotTelemetryService(
        connector=connector, interval=interval, keepalive_interval=keepalive
    )


SERVICE_FACTORIES: dict[str, Callable[["ReticulumTelemetryHub"], HubService]] = {
    "gpsd": _gps_factory,
    "tak_cot": _cot_factory,
}
