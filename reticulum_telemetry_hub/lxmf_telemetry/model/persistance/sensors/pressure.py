"""SQLAlchemy model for the Pressure sensor."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .sensor import Sensor
from .sensor_enum import SID_PRESSURE


class Pressure(Sensor):
    __tablename__ = "Pressure"

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    mbar: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_PRESSURE

    def pack(self):  # type: ignore[override]
        return self.mbar

    def unpack(self, packed: Any):  # type: ignore[override]
        if packed is None:
            self.mbar = None
            return None
        self.mbar = packed
        return {"mbar": self.mbar}

    __mapper_args__ = {
        "polymorphic_identity": SID_PRESSURE,
        "with_polymorphic": "*",
    }
