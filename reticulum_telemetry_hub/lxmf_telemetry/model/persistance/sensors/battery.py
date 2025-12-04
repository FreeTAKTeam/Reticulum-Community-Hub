"""SQLAlchemy model for the Battery sensor."""

from __future__ import annotations

from typing import Any, Optional

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
            return None

        charge = None if self.charge_percent is None else round(self.charge_percent, 1)
        return [charge, self.charging, self.temperature]

    def unpack(self, packed: Any):  # type: ignore[override]
        if packed is None:
            self.charge_percent = None
            self.charging = None
            self.temperature = None
            return None

        try:
            self.charge_percent = (
                None if packed[0] is None else round(float(packed[0]), 1)
            )
            self.charging = packed[1] if len(packed) > 1 else None
            if len(packed) > 2:
                self.temperature = packed[2]
            else:
                self.temperature = None
        except (IndexError, TypeError, ValueError):
            self.charge_percent = None
            self.charging = None
            self.temperature = None
            return None

        return {
            "charge_percent": self.charge_percent,
            "charging": self.charging,
            "temperature": self.temperature,
        }

    __mapper_args__ = {
        "polymorphic_identity": SID_BATTERY,
        "with_polymorphic": "*",
    }
