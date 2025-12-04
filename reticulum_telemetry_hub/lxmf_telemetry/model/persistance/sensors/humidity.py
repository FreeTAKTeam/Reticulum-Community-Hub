"""SQLAlchemy model for the Humidity sensor."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .sensor import Sensor
from .sensor_enum import SID_HUMIDITY


class Humidity(Sensor):
    __tablename__ = "Humidity"

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    percent_relative: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_HUMIDITY

    def pack(self):  # type: ignore[override]
        return self.percent_relative

    def unpack(self, packed: Any):  # type: ignore[override]
        if packed is None:
            self.percent_relative = None
            return None
        self.percent_relative = packed
        return {"percent_relative": self.percent_relative}

    __mapper_args__ = {
        "polymorphic_identity": SID_HUMIDITY,
        "with_polymorphic": "*",
    }
