"""SQLAlchemy model for the Physical Link sensor."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .sensor import Sensor
from .sensor_enum import SID_PHYSICAL_LINK


class PhysicalLink(Sensor):
    __tablename__ = "PhysicalLink"

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    rssi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    snr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    q: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_PHYSICAL_LINK

    def pack(self):  # type: ignore[override]
        if self.rssi is None and self.snr is None and self.q is None:
            return None
        return [self.rssi, self.snr, self.q]

    def unpack(self, packed: Any):  # type: ignore[override]
        if packed is None:
            self.rssi = None
            self.snr = None
            self.q = None
            return None

        try:
            self.rssi = packed[0]
            self.snr = packed[1]
            self.q = packed[2]
        except (IndexError, TypeError):
            self.rssi = None
            self.snr = None
            self.q = None
            return None

        return {"rssi": self.rssi, "snr": self.snr, "q": self.q}

    __mapper_args__ = {
        "polymorphic_identity": SID_PHYSICAL_LINK,
        "with_polymorphic": "*",
    }
