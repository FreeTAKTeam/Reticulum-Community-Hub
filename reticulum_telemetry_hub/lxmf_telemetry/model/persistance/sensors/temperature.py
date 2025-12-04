"""SQLAlchemy model for the Temperature sensor."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .sensor import Sensor
from .sensor_enum import SID_TEMPERATURE


class Temperature(Sensor):
    __tablename__ = "Temperature"

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_TEMPERATURE

    def pack(self):  # type: ignore[override]
        return self.c

    def unpack(self, packed: Any):  # type: ignore[override]
        if packed is None:
            self.c = None
            return None
        self.c = packed
        return {"c": self.c}

    __mapper_args__ = {
        "polymorphic_identity": SID_TEMPERATURE,
        "with_polymorphic": "*",
    }
