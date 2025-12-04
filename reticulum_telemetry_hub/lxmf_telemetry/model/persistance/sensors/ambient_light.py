"""SQLAlchemy model for the Ambient Light sensor."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .sensor import Sensor
from .sensor_enum import SID_AMBIENT_LIGHT


class AmbientLight(Sensor):
    __tablename__ = "AmbientLight"

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    lux: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __init__(self) -> None:
        super().__init__(stale_time=1)
        self.sid = SID_AMBIENT_LIGHT

    def pack(self):  # type: ignore[override]
        return self.lux

    def unpack(self, packed: Any):  # type: ignore[override]
        if packed is None:
            self.lux = None
            return None
        self.lux = packed
        return {"lux": self.lux}

    __mapper_args__ = {
        "polymorphic_identity": SID_AMBIENT_LIGHT,
        "with_polymorphic": "*",
    }
