"""Runtime helpers for configuring locally collected telemetry snapshots."""

from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Protocol

from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor import (
    Sensor,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_mapping import (
    sid_mapping,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_ACCELERATION,
    SID_AMBIENT_LIGHT,
    SID_ANGULAR_VELOCITY,
    SID_BATTERY,
    SID_CONNECTION_MAP,
    SID_CUSTOM,
    SID_FUEL,
    SID_GRAVITY,
    SID_HUMIDITY,
    SID_INFORMATION,
    SID_LOCATION,
    SID_LXMF_PROPAGATION,
    SID_MAGNETIC_FIELD,
    SID_NVM,
    SID_PHYSICAL_LINK,
    SID_POWER_CONSUMPTION,
    SID_POWER_PRODUCTION,
    SID_PRESSURE,
    SID_PROCESSOR,
    SID_PROXIMITY,
    SID_RAM,
    SID_RECEIVED,
    SID_RNS_TRANSPORT,
    SID_TANK,
    SID_TEMPERATURE,
    SID_TIME,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.telemeter import Telemeter


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


SnapshotMutator = Callable[[Telemeter, dict[int, Any]], None]


class TelemetryPlugin(Protocol):
    """Protocol describing telemetry plugins that can customize snapshots."""

    def setup(self, manager: "TelemeterManager") -> None: ...


@dataclass
class StaticInformationConfig:
    """Configuration describing synthesized Information sensor contents."""

    enabled: bool = True
    contents: str = ""


@dataclass
class StaticLocationConfig:
    """Configuration describing synthesized Location sensor coordinates."""

    enabled: bool = True
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    speed: float | None = None
    bearing: float | None = None
    accuracy: float | None = None


SENSOR_NAME_TO_SID = {
    "time": SID_TIME,
    "location": SID_LOCATION,
    "pressure": SID_PRESSURE,
    "battery": SID_BATTERY,
    "physical_link": SID_PHYSICAL_LINK,
    "acceleration": SID_ACCELERATION,
    "temperature": SID_TEMPERATURE,
    "humidity": SID_HUMIDITY,
    "magnetic_field": SID_MAGNETIC_FIELD,
    "ambient_light": SID_AMBIENT_LIGHT,
    "gravity": SID_GRAVITY,
    "angular_velocity": SID_ANGULAR_VELOCITY,
    "proximity": SID_PROXIMITY,
    "information": SID_INFORMATION,
    "received": SID_RECEIVED,
    "power_consumption": SID_POWER_CONSUMPTION,
    "power_production": SID_POWER_PRODUCTION,
    "processor": SID_PROCESSOR,
    "ram": SID_RAM,
    "nvm": SID_NVM,
    "tank": SID_TANK,
    "fuel": SID_FUEL,
    "lxmf_propagation": SID_LXMF_PROPAGATION,
    "rns_transport": SID_RNS_TRANSPORT,
    "connection_map": SID_CONNECTION_MAP,
    "custom": SID_CUSTOM,
}

DEFAULT_SENSOR_ORDER = (
    "time",
    "location",
    "information",
    "battery",
    "pressure",
    "temperature",
    "humidity",
    "magnetic_field",
    "ambient_light",
    "gravity",
    "angular_velocity",
    "acceleration",
    "proximity",
    "physical_link",
    "received",
    "power_consumption",
    "power_production",
    "processor",
    "ram",
    "nvm",
    "tank",
    "fuel",
    "lxmf_propagation",
    "rns_transport",
    "connection_map",
    "custom",
)


@dataclass
class TelemetryRuntimeConfig:
    """Runtime configuration controlling synthesized sensors and toggles."""

    enabled_sensors: MutableMapping[int, bool] = field(default_factory=dict)
    static_information: StaticInformationConfig | None = None
    static_location: StaticLocationConfig | None = None

    @classmethod
    def from_manager(
        cls,
        manager: HubConfigurationManager | None,
        *,
        filename: str = "telemetry.ini",
    ) -> "TelemetryRuntimeConfig":
        if manager is None:
            return cls()

        telemetry_filename = manager.runtime_config.telemetry_filename or filename

        if manager.config_parser.has_section("telemetry"):
            return cls.from_section(manager.config_parser["telemetry"])

        path = Path(manager.storage_path) / telemetry_filename
        return cls.from_file(path)

    @classmethod
    def from_file(cls, path: Path | None) -> "TelemetryRuntimeConfig":
        if path is None:
            return cls()

        parser = ConfigParser()
        if path.exists():
            parser.read(path)

        if parser.has_section("telemetry"):
            section: Mapping[str, str] = parser["telemetry"]
        else:
            section = {}

        return cls.from_section(section)

    @classmethod
    def from_section(cls, section: Mapping[str, str]) -> "TelemetryRuntimeConfig":
        if section is None:
            section = {}

        enabled: MutableMapping[int, bool] = {}
        for name, sid in SENSOR_NAME_TO_SID.items():
            flag_key = f"enable_{name}"
            if flag_key in section:
                enabled[sid] = _get_bool(section, flag_key, True)

        info_cfg = None
        info_text = section.get("static_information", "").strip()
        if info_text:
            info_enabled = _get_bool(section, "enable_information", True)
            info_cfg = StaticInformationConfig(enabled=info_enabled, contents=info_text)

        location_cfg = None
        if _get_bool(section, "synthesize_location", False):
            latitude = _get_float(section, "location_latitude")
            longitude = _get_float(section, "location_longitude")
            if latitude is not None and longitude is not None:
                location_cfg = StaticLocationConfig(
                    enabled=True,
                    latitude=latitude,
                    longitude=longitude,
                    altitude=_get_float(section, "location_altitude"),
                    speed=_get_float(section, "location_speed"),
                    bearing=_get_float(section, "location_bearing"),
                    accuracy=_get_float(section, "location_accuracy"),
                )

        return cls(
            enabled_sensors=enabled,
            static_information=info_cfg,
            static_location=location_cfg,
        )

    def is_enabled(self, sid: int) -> bool:
        return self.enabled_sensors.get(sid, True)


def _get_bool(section: Mapping[str, str], key: str, default: bool) -> bool:
    value = section.get(key)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _get_float(section: Mapping[str, str], key: str) -> float | None:
    value = section.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TelemeterManager:
    """Own a long-lived ``Telemeter`` configured via hub settings."""

    def __init__(
        self,
        *,
        config_manager: HubConfigurationManager | None = None,
        config: TelemetryRuntimeConfig | None = None,
        telemeter: Telemeter | None = None,
    ) -> None:
        self._config_manager = config_manager
        self._config = config or TelemetryRuntimeConfig.from_manager(config_manager)
        self._telemeter = telemeter or Telemeter(peer_dest="")
        self._sensors: MutableMapping[int, Sensor] = {}
        self._sensor_order: list[int] = []
        self._enabled: MutableMapping[int, bool] = {}
        self._mutators: list[SnapshotMutator] = []
        self._initialize_default_sensors()

    @property
    def telemeter(self) -> Telemeter:
        return self._telemeter

    def get_sensor(self, sid_or_name: int | str) -> Sensor | None:
        sid = self._normalize_sid(sid_or_name)
        return self._sensors.get(sid)

    def enable_sensor(self, sid_or_name: int | str) -> None:
        sid = self._normalize_sid(sid_or_name)
        if sid not in self._sensors:
            self._add_sensor_instance(sid)
        self._enabled[sid] = True

    def disable_sensor(self, sid_or_name: int | str) -> None:
        sid = self._normalize_sid(sid_or_name)
        self._enabled[sid] = False

    def add_sensor(self, sensor: Sensor, *, enabled: bool = True) -> Sensor:
        sid = sensor.sid
        self._sensors[sid] = sensor
        if sid not in self._sensor_order:
            self._sensor_order.append(sid)
        if sensor not in self._telemeter.sensors:
            self._telemeter.sensors.append(sensor)
        self._enabled[sid] = enabled
        return sensor

    def add_snapshot_mutator(self, mutator: SnapshotMutator) -> None:
        self._mutators.append(mutator)

    def register_plugin(
        self, plugin: TelemetryPlugin | Callable[["TelemeterManager"], None]
    ) -> None:
        if hasattr(plugin, "setup"):
            plugin.setup(self)  # type: ignore[attr-defined]
        elif callable(plugin):
            plugin(self)
        else:  # pragma: no cover - defensive guard
            raise TypeError(
                "Telemetry plugins must be callables or expose a setup() method"
            )

    def snapshot(self) -> dict[int, Any]:
        """Pack enabled sensors and return a telemetry snapshot."""

        payload: dict[int, Any] = {}
        now = _utcnow()
        self._synthesize_information()
        self._synthesize_location(now)

        for sid in self._sensor_order:
            if not self._enabled.get(sid, True):
                continue
            sensor = self._sensors.get(sid)
            if sensor is None:
                continue
            if sid == SID_TIME and hasattr(sensor, "utc"):
                sensor.utc = now
            packed = sensor.pack()
            if packed is None:
                continue
            payload[sid] = packed

        for mutator in self._mutators:
            mutator(self._telemeter, payload)

        return payload

    # ------------------------------------------------------------------ #
    # private helpers
    # ------------------------------------------------------------------ #
    def _initialize_default_sensors(self) -> None:
        for name in DEFAULT_SENSOR_ORDER:
            sid = SENSOR_NAME_TO_SID.get(name)
            if sid is None:
                continue
            self._add_sensor_instance(sid)

    def _add_sensor_instance(self, sid: int) -> None:
        sensor_cls = sid_mapping.get(sid)
        if sensor_cls is None:
            return
        sensor = sensor_cls()
        self._sensors[sid] = sensor
        self._sensor_order.append(sid)
        self._telemeter.sensors.append(sensor)
        self._enabled[sid] = self._config.is_enabled(sid)

    def _normalize_sid(self, sid_or_name: int | str) -> int:
        if isinstance(sid_or_name, int):
            return sid_or_name
        if isinstance(sid_or_name, str):
            key = sid_or_name.strip().lower()
            if key in SENSOR_NAME_TO_SID:
                return SENSOR_NAME_TO_SID[key]
            raise KeyError(f"Unknown telemetry sensor '{sid_or_name}'")
        raise TypeError("Sensor identifiers must be int or str")

    def _synthesize_information(self) -> None:
        cfg = self._config.static_information
        if cfg is None or not cfg.enabled or not cfg.contents:
            return
        self.enable_sensor(SID_INFORMATION)
        sensor = self._sensors.get(SID_INFORMATION)
        if sensor is None:
            return
        setattr(sensor, "contents", cfg.contents)
        setattr(sensor, "synthesized", True)

    def _synthesize_location(self, timestamp: datetime) -> None:
        cfg = self._config.static_location
        if cfg is None or not cfg.enabled:
            return
        if cfg.latitude is None or cfg.longitude is None:
            return
        self.enable_sensor(SID_LOCATION)
        sensor = self._sensors.get(SID_LOCATION)
        if sensor is None:
            return
        defaults: Mapping[str, float] = {
            "altitude": 0.0,
            "speed": 0.0,
            "bearing": 0.0,
            "accuracy": 0.0,
        }
        setattr(sensor, "latitude", cfg.latitude)
        setattr(sensor, "longitude", cfg.longitude)
        setattr(
            sensor,
            "altitude",
            cfg.altitude if cfg.altitude is not None else defaults["altitude"],
        )
        setattr(
            sensor, "speed", cfg.speed if cfg.speed is not None else defaults["speed"]
        )
        setattr(
            sensor,
            "bearing",
            cfg.bearing if cfg.bearing is not None else defaults["bearing"],
        )
        setattr(
            sensor,
            "accuracy",
            cfg.accuracy if cfg.accuracy is not None else defaults["accuracy"],
        )
        setattr(sensor, "last_update", timestamp)
        setattr(sensor, "synthesized", True)
