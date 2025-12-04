"""SQLAlchemy model for the Received sensor."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Float, ForeignKey, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from .sensor import Sensor
from .sensor_enum import SID_RECEIVED


class Received(Sensor):
    __tablename__ = "Received"

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    by: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    via: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    geodesic_distance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    euclidian_distance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_RECEIVED

    def pack(self):  # type: ignore[override]
        if (
            self.by is None
            and self.via is None
            and self.geodesic_distance is None
            and self.euclidian_distance is None
        ):
            return None

        return [
            self.by,
            self.via,
            self.geodesic_distance,
            self.euclidian_distance,
        ]

    def unpack(self, packed: Any):  # type: ignore[override]
        if packed is None:
            self.by = None
            self.via = None
            self.geodesic_distance = None
            self.euclidian_distance = None
            return None

        try:
            self.by = packed[0]
            self.via = packed[1]
            self.geodesic_distance = packed[2]
            self.euclidian_distance = packed[3]
        except (IndexError, TypeError):
            self.by = None
            self.via = None
            self.geodesic_distance = None
            self.euclidian_distance = None
            return None

        return {
            "by": self.by,
            "via": self.via,
            "distance": {
                "geodesic": self.geodesic_distance,
                "euclidian": self.euclidian_distance,
            },
        }

    __mapper_args__ = {
        "polymorphic_identity": SID_RECEIVED,
        "with_polymorphic": "*",
    }
