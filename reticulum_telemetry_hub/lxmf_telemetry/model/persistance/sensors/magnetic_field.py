"""SQLAlchemy model for the Magnetic Field sensor."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .sensor import Sensor
from .sensor_enum import SID_MAGNETIC_FIELD


class MagneticField(Sensor):
    __tablename__ = "MagneticField"

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    z: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __init__(
        self,
        stale_time: float | None = 1,
        data: Any | None = None,
        active: bool = False,
        synthesized: bool = False,
        last_update: float = 0,
        last_read: float = 0,
    ) -> None:
        super().__init__(
            stale_time=stale_time,
            data=data,
            active=active,
            synthesized=synthesized,
            last_update=last_update,
            last_read=last_read,
        )
        self.sid = SID_MAGNETIC_FIELD

    def pack(self):  # type: ignore[override]
        if self.x is None and self.y is None and self.z is None:
            return None
        return [self.x, self.y, self.z]

    def unpack(self, packed: Any):  # type: ignore[override]
        if packed is None:
            self.x = None
            self.y = None
            self.z = None
            return None

        try:
            self.x = packed[0]
            self.y = packed[1]
            self.z = packed[2]
        except (IndexError, TypeError):
            self.x = None
            self.y = None
            self.z = None
            return None

        return {"x": self.x, "y": self.y, "z": self.z}

    __mapper_args__ = {
        "polymorphic_identity": SID_MAGNETIC_FIELD,
        "with_polymorphic": "*",
    }
