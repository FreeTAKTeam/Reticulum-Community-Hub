"""SQLAlchemy model for the Battery sensor."""
from __future__ import annotations

from typing import Any, Optional

from msgpack import unpackb
from sqlalchemy import Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .sensor import Sensor
from .sensor_enum import SID_BATTERY


class Battery(Sensor):
    __tablename__ = "Battery"

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    charge_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    charging: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __init__(self) -> None:
        super().__init__(stale_time=10)
        self.sid = SID_BATTERY

    def pack(self):  # type: ignore[override]
        if (
            self.charge_percent is None
            and self.charging is None
            and self.temperature is None
        ):
            legacy_payload = self._hydrate_from_legacy_payload()
            if (
                self.charge_percent is None
                and self.charging is None
                and self.temperature is None
            ):
                return legacy_payload

        charge = None if self.charge_percent is None else round(self.charge_percent, 1)
        return [charge, self.charging, self.temperature]

    def unpack(self, packed: Any):  # type: ignore[override]
        if packed is None:
            self.charge_percent = None
            self.charging = None
            self.temperature = None
            return None

        try:
            values = self._apply_payload(packed)
        except (IndexError, TypeError, ValueError):
            values = None

        if values is None:
            self.charge_percent = None
            self.charging = None
            self.temperature = None
            return None

        return {
            "charge_percent": self.charge_percent,
            "charging": self.charging,
            "temperature": self.temperature,
        }

    def _apply_payload(self, payload: Any) -> Optional[list[Any]]:
        """Populate typed columns from an iterable payload.

        Returns the payload as a list when successful so callers can reuse the
        decoded values (e.g. when hydrating legacy rows).
        """

        if isinstance(payload, (bytes, bytearray, memoryview, str)):
            return None

        if isinstance(payload, dict):
            return None

        try:
            values = list(payload)
        except TypeError:
            return None

        charge_raw = values[0] if len(values) > 0 else None
        try:
            self.charge_percent = (
                None if charge_raw is None else round(float(charge_raw), 1)
            )
        except (TypeError, ValueError):
            self.charge_percent = None

        self.charging = values[1] if len(values) > 1 else None
        self.temperature = values[2] if len(values) > 2 else None

        return values

    def _hydrate_from_legacy_payload(self) -> Optional[list[Any]]:
        """Populate typed fields from legacy ``Sensor.data`` blobs if needed."""

        if getattr(self, "_legacy_hydrated", False):
            return getattr(self, "_legacy_payload", None)

        setattr(self, "_legacy_hydrated", True)

        raw = self.data
        if raw is None:
            payload: Any = None
        elif isinstance(raw, (bytes, bytearray, memoryview)):
            try:
                payload = unpackb(raw, strict_map_key=False)
            except (TypeError, ValueError):
                payload = raw
        else:
            payload = raw

        values = self._apply_payload(payload) if payload is not None else None
        fallback = values if values is not None else payload
        setattr(self, "_legacy_payload", fallback)
        return fallback

    __mapper_args__ = {
        "polymorphic_identity": SID_BATTERY,
        "with_polymorphic": "*",
    }
