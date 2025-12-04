"""SQLAlchemy model for the Information sensor."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from .sensor import Sensor
from .sensor_enum import SID_INFORMATION


class Information(Sensor):
    """Persisted representation of Sideband's information sensor."""

    __tablename__ = "Information"

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    contents: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __init__(self, contents: Optional[str] = "") -> None:
        super().__init__(stale_time=5)
        self.sid = SID_INFORMATION
        self.contents = contents or ""

    def pack(self):  # type: ignore[override]
        if self.contents is None:
            return None
        return str(self.contents)

    def unpack(self, packed):  # type: ignore[override]
        if packed is None:
            self.contents = None
            return None
        self.contents = str(packed)
        return {"contents": self.contents}

    __mapper_args__ = {
        "polymorphic_identity": SID_INFORMATION,
        "with_polymorphic": "*",
    }
