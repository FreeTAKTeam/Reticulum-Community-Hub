"""Connection map sensor models."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import Base
from .sensor import Sensor
from .sensor_enum import SID_CONNECTION_MAP


_UNSET = object()


class ConnectionMap(Sensor):
    """Sensor representing a set of maps populated with connection points."""

    __tablename__ = "ConnectionMap"

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    maps: Mapped[list["ConnectionMapMap"]] = relationship(
        "ConnectionMapMap",
        back_populates="sensor",
        cascade="all, delete-orphan",
        order_by="ConnectionMapMap.id",
    )

    SID = SID_CONNECTION_MAP

    def __init__(self) -> None:
        super().__init__()
        self.sid = SID_CONNECTION_MAP

    def ensure_map(
        self, map_name: str, label: Optional[str] = None
    ) -> "ConnectionMapMap":
        """Return an existing map entry or create a new one."""

        for entry in self.maps:
            if entry.map_name == map_name:
                if label is not None:
                    entry.label = label
                return entry

        entry = ConnectionMapMap(map_name=map_name, label=label)
        entry.sensor = self
        return entry

    def add_point(
        self,
        map_name: str,
        point_hash: str,
        *,
        latitude: float | None | object = _UNSET,
        longitude: float | None | object = _UNSET,
        altitude: float | None | object = _UNSET,
        point_type: str | None | object = _UNSET,
        name: str | None | object = _UNSET,
        signals: dict[str, Any] | None | object = _UNSET,
        **extra_signals: Any,
    ) -> "ConnectionMapPoint":
        """Add or update a connection point within a map."""

        entry = self.ensure_map(map_name)
        point = entry.get_point(point_hash)
        if point is None:
            point = ConnectionMapPoint(point_hash=point_hash)
            point.map = entry

        if latitude is not _UNSET:
            point.latitude = latitude  # type: ignore[assignment]
        if longitude is not _UNSET:
            point.longitude = longitude  # type: ignore[assignment]
        if altitude is not _UNSET:
            point.altitude = altitude  # type: ignore[assignment]
        if point_type is not _UNSET:
            point.point_type = point_type  # type: ignore[assignment]
        if name is not _UNSET:
            point.name = name  # type: ignore[assignment]

        if signals is not _UNSET or extra_signals:
            if signals is _UNSET:
                merged_signals: dict[str, Any] = dict(point.signals or {})
            elif signals is None:
                merged_signals = {}
            else:
                merged_signals = {k: v for k, v in signals.items() if v is not None}
            for key, value in extra_signals.items():
                if value is not None:
                    merged_signals[key] = value
            point.signals = merged_signals or None

        return point

    def pack(self) -> Optional[dict[str, Any]]:  # type: ignore[override]
        maps_payload: dict[str, dict[str, Any]] = {}
        for entry in self.maps:
            points_payload: dict[str, dict[str, Any]] = {}
            for point in entry.points:
                points_payload[point.point_hash] = point.to_payload()
            maps_payload[entry.map_name] = entry.to_payload(points_payload)

        if not maps_payload:
            return None

        return {"maps": maps_payload}

    def unpack(self, packed: Any) -> Optional[dict[str, Any]]:  # type: ignore[override]
        self.maps[:] = []

        if not isinstance(packed, dict):
            return None

        maps_payload = packed.get("maps")
        if not isinstance(maps_payload, dict):
            return None

        normalized: dict[str, dict[str, Any]] = {}
        for map_name, payload in maps_payload.items():
            if not isinstance(map_name, str):
                continue

            label = None
            points_data: Any = None
            if isinstance(payload, dict):
                label = payload.get("label")
                points_data = payload.get("points")

            entry = ConnectionMapMap(map_name=map_name, label=label)
            entry.sensor = self

            if isinstance(points_data, dict):
                for point_hash, point_payload in points_data.items():
                    if not isinstance(point_hash, str) or not isinstance(
                        point_payload, dict
                    ):
                        continue
                    point = ConnectionMapPoint.from_payload(point_hash, point_payload)
                    point.map = entry
            normalized[map_name] = entry.to_payload(entry.pack_points())

        return {"maps": normalized} if normalized else None

    __mapper_args__ = {
        "polymorphic_identity": SID_CONNECTION_MAP,
        "with_polymorphic": "*",
    }


class ConnectionMapMap(Base):
    """ORM model representing a named map."""

    __tablename__ = "ConnectionMapMap"
    __table_args__ = (UniqueConstraint("sensor_id", "map_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sensor_id: Mapped[int] = mapped_column(
        ForeignKey("ConnectionMap.id", ondelete="CASCADE")
    )
    map_name: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    sensor: Mapped[ConnectionMap] = relationship("ConnectionMap", back_populates="maps")
    points: Mapped[list["ConnectionMapPoint"]] = relationship(
        "ConnectionMapPoint",
        back_populates="map",
        cascade="all, delete-orphan",
        order_by="ConnectionMapPoint.id",
    )

    def get_point(self, point_hash: str) -> Optional["ConnectionMapPoint"]:
        for point in self.points:
            if point.point_hash == point_hash:
                return point
        return None

    def to_payload(self, points: dict[str, dict[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {"points": points}
        if self.label is not None:
            payload["label"] = self.label
        return payload

    def pack_points(self) -> dict[str, dict[str, Any]]:
        return {point.point_hash: point.to_payload() for point in self.points}


class ConnectionMapPoint(Base):
    """ORM model for individual map points."""

    __tablename__ = "ConnectionMapPoint"
    __table_args__ = (UniqueConstraint("map_id", "point_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    map_id: Mapped[int] = mapped_column(
        ForeignKey("ConnectionMapMap.id", ondelete="CASCADE")
    )
    point_hash: Mapped[str] = mapped_column(String, nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    altitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    point_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    signals: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    map: Mapped[ConnectionMapMap] = relationship(
        "ConnectionMapMap", back_populates="points"
    )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.latitude is not None:
            payload["lat"] = self.latitude
        if self.longitude is not None:
            payload["lon"] = self.longitude
        if self.altitude is not None:
            payload["alt"] = self.altitude
        if self.point_type is not None:
            payload["type"] = self.point_type
        if self.name is not None:
            payload["name"] = self.name
        if self.signals:
            payload.update(self.signals)
        return payload

    @classmethod
    def from_payload(
        cls, point_hash: str, payload: dict[str, Any]
    ) -> "ConnectionMapPoint":
        signals: dict[str, Any] = {}
        latitude = payload.get("lat")
        longitude = payload.get("lon")
        altitude = payload.get("alt")
        point_type = payload.get("type")
        name = payload.get("name")

        for key, value in payload.items():
            if key not in {"lat", "lon", "alt", "type", "name"}:
                signals[key] = value

        return cls(
            point_hash=point_hash,
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            point_type=point_type,
            name=name,
            signals=signals or None,
        )


__all__ = [
    "ConnectionMap",
    "ConnectionMapMap",
    "ConnectionMapPoint",
]
