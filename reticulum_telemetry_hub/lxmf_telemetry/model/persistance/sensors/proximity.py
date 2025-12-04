"""SQLAlchemy model for the Proximity sensor."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .sensor import Sensor
from .sensor_enum import SID_PROXIMITY


class Proximity(Sensor):
    __tablename__ = "Proximity"

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    triggered: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    def __init__(self) -> None:
        super().__init__(stale_time=1)
        self.sid = SID_PROXIMITY

    def pack(self):  # type: ignore[override]
        return self.triggered

    def unpack(self, packed: Any):  # type: ignore[override]
        if packed is None:
            self.triggered = None
            return None
        self.triggered = packed
        return {"triggered": self.triggered}

    __mapper_args__ = {
        "polymorphic_identity": SID_PROXIMITY,
        "with_polymorphic": "*",
    }
