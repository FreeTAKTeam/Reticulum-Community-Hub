"""Additional collection-backed generic telemetry sensor models."""

from __future__ import annotations

from typing import Any
from typing import Optional

from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from .generic import _CollectionEntry
from .generic import _CollectionSensor
from .sensor_enum import SID_CUSTOM
from .sensor_enum import SID_FUEL
from .sensor_enum import SID_NVM
from .sensor_enum import SID_RAM
from .sensor_enum import SID_TANK


class RandomAccessMemory(_CollectionSensor):
    __tablename__ = "RandomAccessMemory"
    SID = SID_RAM

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    entries: Mapped[list["RandomAccessMemoryEntry"]] = relationship(
        "RandomAccessMemoryEntry",
        back_populates="sensor",
        cascade="all, delete-orphan",
        order_by="RandomAccessMemoryEntry.id",
    )

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_RAM

    def update_entry(
        self,
        capacity: Optional[float] = None,
        used: Optional[float] = None,
        type_label: Any = None,
    ) -> bool:
        label = RandomAccessMemoryEntry.normalize_label(type_label)
        if label is None:
            return False
        entry = self._get_or_create_entry(label)
        entry.capacity = capacity
        entry.used = used
        return True

    def remove_entry(self, type_label: Any = None) -> bool:
        label = RandomAccessMemoryEntry.normalize_label(type_label)
        if label is None:
            return False
        return self._remove_entry(label)

    def pack(self):  # type: ignore[override]
        return self._pack_entries()

    def unpack(self, packed: Any):  # type: ignore[override]
        return self._unpack_entries(packed)

    __mapper_args__ = {
        "polymorphic_identity": SID_RAM,
        "with_polymorphic": "*",
    }


class RandomAccessMemoryEntry(_CollectionEntry):
    __tablename__ = "RandomAccessMemoryEntry"

    capacity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    used: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sensor: Mapped[RandomAccessMemory] = relationship(
        "RandomAccessMemory", back_populates="entries"
    )

    def pack_values(self) -> list[Any]:
        return [self.capacity, self.used]

    @classmethod
    def from_packed(cls, label: str, values: Any) -> "RandomAccessMemoryEntry":
        capacity = None
        used = None
        if isinstance(values, (list, tuple)):
            if values:
                capacity = values[0]
            if len(values) > 1:
                used = values[1]
        return cls(type_label=label, capacity=capacity, used=used)


RandomAccessMemory.entry_model = RandomAccessMemoryEntry  # type: ignore[attr-defined]


class NonVolatileMemory(_CollectionSensor):
    __tablename__ = "NonVolatileMemory"
    SID = SID_NVM

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    entries: Mapped[list["NonVolatileMemoryEntry"]] = relationship(
        "NonVolatileMemoryEntry",
        back_populates="sensor",
        cascade="all, delete-orphan",
        order_by="NonVolatileMemoryEntry.id",
    )

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_NVM

    def update_entry(
        self,
        capacity: Optional[float] = None,
        used: Optional[float] = None,
        type_label: Any = None,
    ) -> bool:
        label = NonVolatileMemoryEntry.normalize_label(type_label)
        if label is None:
            return False
        entry = self._get_or_create_entry(label)
        entry.capacity = capacity
        entry.used = used
        return True

    def remove_entry(self, type_label: Any = None) -> bool:
        label = NonVolatileMemoryEntry.normalize_label(type_label)
        if label is None:
            return False
        return self._remove_entry(label)

    def pack(self):  # type: ignore[override]
        return self._pack_entries()

    def unpack(self, packed: Any):  # type: ignore[override]
        return self._unpack_entries(packed)

    __mapper_args__ = {
        "polymorphic_identity": SID_NVM,
        "with_polymorphic": "*",
    }


class NonVolatileMemoryEntry(_CollectionEntry):
    __tablename__ = "NonVolatileMemoryEntry"

    capacity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    used: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sensor: Mapped[NonVolatileMemory] = relationship(
        "NonVolatileMemory", back_populates="entries"
    )

    def pack_values(self) -> list[Any]:
        return [self.capacity, self.used]

    @classmethod
    def from_packed(cls, label: str, values: Any) -> "NonVolatileMemoryEntry":
        capacity = None
        used = None
        if isinstance(values, (list, tuple)):
            if values:
                capacity = values[0]
            if len(values) > 1:
                used = values[1]
        return cls(type_label=label, capacity=capacity, used=used)


NonVolatileMemory.entry_model = NonVolatileMemoryEntry  # type: ignore[attr-defined]


class Custom(_CollectionSensor):
    __tablename__ = "Custom"
    SID = SID_CUSTOM

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    entries: Mapped[list["CustomEntry"]] = relationship(
        "CustomEntry",
        back_populates="sensor",
        cascade="all, delete-orphan",
        order_by="CustomEntry.id",
    )

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_CUSTOM

    def update_entry(
        self,
        value: Any = None,
        type_label: Any = None,
        custom_icon: Optional[str] = None,
    ) -> bool:
        label = CustomEntry.normalize_label(type_label)
        if label is None:
            return False
        entry = self._get_or_create_entry(label)
        entry.value = value
        entry.custom_icon = custom_icon
        return True

    def remove_entry(self, type_label: Any = None) -> bool:
        label = CustomEntry.normalize_label(type_label)
        if label is None:
            return False
        return self._remove_entry(label)

    def pack(self):  # type: ignore[override]
        return self._pack_entries()

    def unpack(self, packed: Any):  # type: ignore[override]
        return self._unpack_entries(packed)

    __mapper_args__ = {
        "polymorphic_identity": SID_CUSTOM,
        "with_polymorphic": "*",
    }


class CustomEntry(_CollectionEntry):
    __tablename__ = "CustomEntry"

    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    custom_icon: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sensor: Mapped[Custom] = relationship("Custom", back_populates="entries")

    def pack_values(self) -> list[Any]:
        return [self.value, self.custom_icon]

    @classmethod
    def from_packed(cls, label: str, values: Any) -> "CustomEntry":
        value = None
        custom_icon = None
        if isinstance(values, (list, tuple)):
            if values:
                value = values[0]
            if len(values) > 1:
                custom_icon = values[1]
        return cls(type_label=label, value=value, custom_icon=custom_icon)


Custom.entry_model = CustomEntry  # type: ignore[attr-defined]


class Tank(_CollectionSensor):
    __tablename__ = "Tank"
    SID = SID_TANK

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    entries: Mapped[list["TankEntry"]] = relationship(
        "TankEntry",
        back_populates="sensor",
        cascade="all, delete-orphan",
        order_by="TankEntry.id",
    )

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_TANK

    def update_entry(
        self,
        capacity: Optional[float] = None,
        level: Optional[float] = None,
        unit: Optional[str] = None,
        type_label: Any = None,
        custom_icon: Optional[str] = None,
    ) -> bool:
        label = TankEntry.normalize_label(type_label)
        if label is None:
            return False
        if unit is not None and not isinstance(unit, str):
            return False
        entry = self._get_or_create_entry(label)
        entry.capacity = capacity
        entry.level = level
        entry.unit = unit
        entry.custom_icon = custom_icon
        return True

    def remove_entry(self, type_label: Any = None) -> bool:
        label = TankEntry.normalize_label(type_label)
        if label is None:
            return False
        return self._remove_entry(label)

    def pack(self):  # type: ignore[override]
        return self._pack_entries()

    def unpack(self, packed: Any):  # type: ignore[override]
        return self._unpack_entries(packed)

    __mapper_args__ = {
        "polymorphic_identity": SID_TANK,
        "with_polymorphic": "*",
    }


class TankEntry(_CollectionEntry):
    __tablename__ = "TankEntry"

    capacity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    custom_icon: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sensor: Mapped[Tank] = relationship("Tank", back_populates="entries")

    def pack_values(self) -> list[Any]:
        return [self.capacity, self.level, self.unit, self.custom_icon]

    @classmethod
    def from_packed(cls, label: str, values: Any) -> "TankEntry":
        capacity = None
        level = None
        unit = None
        custom_icon = None
        if isinstance(values, (list, tuple)):
            if values:
                capacity = values[0]
            if len(values) > 1:
                level = values[1]
            if len(values) > 2:
                unit = values[2]
            if len(values) > 3:
                custom_icon = values[3]
        return cls(
            type_label=label,
            capacity=capacity,
            level=level,
            unit=unit,
            custom_icon=custom_icon,
        )


Tank.entry_model = TankEntry  # type: ignore[attr-defined]


class Fuel(_CollectionSensor):
    __tablename__ = "Fuel"
    SID = SID_FUEL

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    entries: Mapped[list["FuelEntry"]] = relationship(
        "FuelEntry",
        back_populates="sensor",
        cascade="all, delete-orphan",
        order_by="FuelEntry.id",
    )

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_FUEL

    def update_entry(
        self,
        capacity: Optional[float] = None,
        level: Optional[float] = None,
        unit: Optional[str] = None,
        type_label: Any = None,
        custom_icon: Optional[str] = None,
    ) -> bool:
        label = FuelEntry.normalize_label(type_label)
        if label is None:
            return False
        if unit is not None and not isinstance(unit, str):
            return False
        entry = self._get_or_create_entry(label)
        entry.capacity = capacity
        entry.level = level
        entry.unit = unit
        entry.custom_icon = custom_icon
        return True

    def remove_entry(self, type_label: Any = None) -> bool:
        label = FuelEntry.normalize_label(type_label)
        if label is None:
            return False
        return self._remove_entry(label)

    def pack(self):  # type: ignore[override]
        return self._pack_entries()

    def unpack(self, packed: Any):  # type: ignore[override]
        return self._unpack_entries(packed)

    __mapper_args__ = {
        "polymorphic_identity": SID_FUEL,
        "with_polymorphic": "*",
    }


class FuelEntry(_CollectionEntry):
    __tablename__ = "FuelEntry"

    capacity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    custom_icon: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sensor: Mapped[Fuel] = relationship("Fuel", back_populates="entries")

    def pack_values(self) -> list[Any]:
        return [self.capacity, self.level, self.unit, self.custom_icon]

    @classmethod
    def from_packed(cls, label: str, values: Any) -> "FuelEntry":
        capacity = None
        level = None
        unit = None
        custom_icon = None
        if isinstance(values, (list, tuple)):
            if values:
                capacity = values[0]
            if len(values) > 1:
                level = values[1]
            if len(values) > 2:
                unit = values[2]
            if len(values) > 3:
                custom_icon = values[3]
        return cls(
            type_label=label,
            capacity=capacity,
            level=level,
            unit=unit,
            custom_icon=custom_icon,
        )


Fuel.entry_model = FuelEntry  # type: ignore[attr-defined]
