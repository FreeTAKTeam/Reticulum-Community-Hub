"""Generic SQLAlchemy models for telemetry sensors without dedicated schema.

These classes persist the raw packed payload for each sensor while ensuring the
``Sensor.sid`` column is populated so serialization works as expected. They use
single-table inheritance to reuse the base :class:`Sensor` table.
"""
from __future__ import annotations

from typing import Any

from .sensor import Sensor
from .sensor_enum import (
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
    SID_LXMF_PROPAGATION,
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
)
from msgpack import packb, unpackb


class RawSensor(Sensor):
    """Base class for sensors that simply persist packed payloads."""

    __abstract__ = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        sid = getattr(type(self), "SID", None)
        if sid is not None:
            self.sid = sid

    def pack(self) -> Any:  # type: ignore[override]
        if self.data is None:
            return None

        cached = getattr(self, "_cached", None)
        if cached is None:
            cached = unpackb(self.data, strict_map_key=False)
            setattr(self, "_cached", cached)
        return cached

    def unpack(self, packed: Any) -> Any:  # type: ignore[override]
        setattr(self, "_cached", packed)
        self.data = None if packed is None else packb(packed, use_bin_type=True)
        return packed


def _build_sensor_class(name: str, sid: int):
    return type(
        name,
        (RawSensor,),
        {
            "SID": sid,
            "__module__": __name__,
            "__mapper_args__": {"polymorphic_identity": sid, "with_polymorphic": "*"},
        },
    )


Pressure = _build_sensor_class("Pressure", SID_PRESSURE)
Battery = _build_sensor_class("Battery", SID_BATTERY)
PhysicalLink = _build_sensor_class("PhysicalLink", SID_PHYSICAL_LINK)
Acceleration = _build_sensor_class("Acceleration", SID_ACCELERATION)
Temperature = _build_sensor_class("Temperature", SID_TEMPERATURE)
Humidity = _build_sensor_class("Humidity", SID_HUMIDITY)
AmbientLight = _build_sensor_class("AmbientLight", SID_AMBIENT_LIGHT)
Gravity = _build_sensor_class("Gravity", SID_GRAVITY)
AngularVelocity = _build_sensor_class("AngularVelocity", SID_ANGULAR_VELOCITY)
Proximity = _build_sensor_class("Proximity", SID_PROXIMITY)
Information = _build_sensor_class("Information", SID_INFORMATION)
Received = _build_sensor_class("Received", SID_RECEIVED)
PowerConsumption = _build_sensor_class("PowerConsumption", SID_POWER_CONSUMPTION)
PowerProduction = _build_sensor_class("PowerProduction", SID_POWER_PRODUCTION)
Processor = _build_sensor_class("Processor", SID_PROCESSOR)
RandomAccessMemory = _build_sensor_class("RandomAccessMemory", SID_RAM)
NonVolatileMemory = _build_sensor_class("NonVolatileMemory", SID_NVM)
Tank = _build_sensor_class("Tank", SID_TANK)
Fuel = _build_sensor_class("Fuel", SID_FUEL)
LXMFPropagation = _build_sensor_class("LXMFPropagation", SID_LXMF_PROPAGATION)
RNSTransport = _build_sensor_class("RNSTransport", SID_RNS_TRANSPORT)
ConnectionMap = _build_sensor_class("ConnectionMap", SID_CONNECTION_MAP)
Custom = _build_sensor_class("Custom", SID_CUSTOM)


__all__ = [
    "Acceleration",
    "AmbientLight",
    "AngularVelocity",
    "Battery",
    "ConnectionMap",
    "Custom",
    "Fuel",
    "Gravity",
    "Humidity",
    "Information",
    "LXMFPropagation",
    "NonVolatileMemory",
    "PhysicalLink",
    "PowerConsumption",
    "PowerProduction",
    "Pressure",
    "Processor",
    "Proximity",
    "RandomAccessMemory",
    "Received",
    "RNSTransport",
    "Tank",
    "Temperature",
]
