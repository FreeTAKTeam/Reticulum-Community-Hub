"""Generic SQLAlchemy models for telemetry sensors without dedicated schema."""
# ruff: noqa: E402

from __future__ import annotations

from typing import Any, Iterable, Optional

from msgpack import packb, unpackb
from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import Base
from .sensor import Sensor
from .sensor_enum import (
    SID_POWER_CONSUMPTION,
    SID_POWER_PRODUCTION,
    SID_PROCESSOR,
)

DEFAULT_LABEL = "__default__"


class RawSensor(Sensor):
    """Base class for sensors that simply persist packed payloads."""

    __abstract__ = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        sid = getattr(type(self), "SID", None)
        if sid is not None:
            self.sid = sid

    def pack(self) -> Any:  # type: ignore[override]
        if self.data is None:
            return None

        cached = getattr(self, "_cached", None)
        if cached is None:
            cached = unpackb(self.data, strict_map_key=False)
            setattr(self, "_cached", cached)
        return cached

    def unpack(self, packed: Any) -> Any:  # type: ignore[override]
        setattr(self, "_cached", packed)
        self.data = None if packed is None else packb(packed, use_bin_type=True)
        return packed


def _build_sensor_class(name: str, sid: int):
    return type(
        name,
        (RawSensor,),
        {
            "SID": sid,
            "__module__": __name__,
            "__mapper_args__": {"polymorphic_identity": sid, "with_polymorphic": "*"},
        },
    )


class _CollectionEntry(Base):
    """Common columns shared across collection sensor entries."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("Sensor.id", ondelete="CASCADE"))
    type_label: Mapped[str] = mapped_column(
        String, nullable=False, default=DEFAULT_LABEL
    )

    @staticmethod
    def pack_label(label: str) -> Any:
        return 0x00 if label == DEFAULT_LABEL else label

    @staticmethod
    def normalize_label(raw: Any) -> Optional[str]:
        if raw is None:
            return DEFAULT_LABEL
        if isinstance(raw, str):
            return raw
        if isinstance(raw, (bytes, bytearray)):
            try:
                return raw.decode()
            except UnicodeDecodeError:
                return None
        if isinstance(raw, int):
            return DEFAULT_LABEL if raw == 0 else None
        return None

    @classmethod
    def from_packed(cls, label: str, values: Any) -> _CollectionEntry:
        raise NotImplementedError

    def pack_values(self) -> list[Any]:
        raise NotImplementedError


class _CollectionSensor(Sensor):
    """Mixin implementing helpers shared by collection-based sensors."""

    __abstract__ = True

    entry_model: type[_CollectionEntry]

    def _get_or_create_entry(self, label: str) -> _CollectionEntry:
        for entry in self.entries:  # type: ignore[attr-defined]
            if entry.type_label == label:
                return entry
        entry = self.entry_model(type_label=label)
        entry.sensor = self  # type: ignore[attr-defined]
        self.entries.append(entry)  # type: ignore[attr-defined]
        return entry

    def _remove_entry(self, label: str) -> bool:
        for entry in list(self.entries):  # type: ignore[attr-defined]
            if entry.type_label == label:
                self.entries.remove(entry)  # type: ignore[attr-defined]
                return True
        return False

    def _pack_entries(self) -> Optional[list[list[Any]]]:
        packed: list[list[Any]] = []
        for entry in self.entries:  # type: ignore[attr-defined]
            packed.append([entry.pack_label(entry.type_label), entry.pack_values()])
        return packed or None

    def _unpack_entries(self, packed: Any) -> Optional[dict[Any, list[Any]]]:
        self.entries[:] = []  # type: ignore[attr-defined]
        if packed is None:
            return None

        unpacked: dict[Any, list[Any]] = {}
        for record in packed:
            if not isinstance(record, (list, tuple)) or len(record) < 2:
                continue
            raw_label, values = record[0], record[1]
            label = self.entry_model.normalize_label(raw_label)
            if label is None:
                continue
            entry = self.entry_model.from_packed(label, values)
            entry.sensor = self  # type: ignore[attr-defined]
            self.entries.append(entry)  # type: ignore[attr-defined]
            unpacked[self.entry_model.pack_label(label)] = entry.pack_values()
        return unpacked


class PowerConsumption(_CollectionSensor):
    __tablename__ = "PowerConsumption"
    SID = SID_POWER_CONSUMPTION

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    entries: Mapped[list["PowerConsumptionEntry"]] = relationship(
        "PowerConsumptionEntry",
        back_populates="sensor",
        cascade="all, delete-orphan",
        order_by="PowerConsumptionEntry.id",
    )

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_POWER_CONSUMPTION

    def update_consumer(
        self,
        power: Optional[float],
        type_label: Any = None,
        custom_icon: Optional[str] = None,
    ) -> bool:
        label = PowerConsumptionEntry.normalize_label(type_label)
        if label is None:
            return False
        entry = self._get_or_create_entry(label)
        entry.power = power
        entry.custom_icon = custom_icon
        return True

    def remove_consumer(self, type_label: Any = None) -> bool:
        label = PowerConsumptionEntry.normalize_label(type_label)
        if label is None:
            return False
        return self._remove_entry(label)

    def pack(self):  # type: ignore[override]
        return self._pack_entries()

    def unpack(self, packed: Any):  # type: ignore[override]
        return self._unpack_entries(packed)

    __mapper_args__ = {
        "polymorphic_identity": SID_POWER_CONSUMPTION,
        "with_polymorphic": "*",
    }


class PowerConsumptionEntry(_CollectionEntry):
    __tablename__ = "PowerConsumptionEntry"

    power: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    custom_icon: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sensor: Mapped[PowerConsumption] = relationship(
        "PowerConsumption", back_populates="entries"
    )

    def pack_values(self) -> list[Any]:
        return [self.power, self.custom_icon]

    @classmethod
    def from_packed(cls, label: str, values: Any) -> "PowerConsumptionEntry":
        power = None
        custom_icon = None
        if isinstance(values, (list, tuple)):
            if values:
                power = values[0]
            if len(values) > 1:
                custom_icon = values[1]
        return cls(type_label=label, power=power, custom_icon=custom_icon)


PowerConsumption.entry_model = PowerConsumptionEntry  # type: ignore[attr-defined]


class PowerProduction(_CollectionSensor):
    __tablename__ = "PowerProduction"
    SID = SID_POWER_PRODUCTION

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    entries: Mapped[list["PowerProductionEntry"]] = relationship(
        "PowerProductionEntry",
        back_populates="sensor",
        cascade="all, delete-orphan",
        order_by="PowerProductionEntry.id",
    )

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_POWER_PRODUCTION

    def update_producer(
        self,
        power: Optional[float],
        type_label: Any = None,
        custom_icon: Optional[str] = None,
    ) -> bool:
        label = PowerProductionEntry.normalize_label(type_label)
        if label is None:
            return False
        entry = self._get_or_create_entry(label)
        entry.power = power
        entry.custom_icon = custom_icon
        return True

    def remove_producer(self, type_label: Any = None) -> bool:
        label = PowerProductionEntry.normalize_label(type_label)
        if label is None:
            return False
        return self._remove_entry(label)

    def pack(self):  # type: ignore[override]
        return self._pack_entries()

    def unpack(self, packed: Any):  # type: ignore[override]
        return self._unpack_entries(packed)

    __mapper_args__ = {
        "polymorphic_identity": SID_POWER_PRODUCTION,
        "with_polymorphic": "*",
    }


class PowerProductionEntry(_CollectionEntry):
    __tablename__ = "PowerProductionEntry"

    power: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    custom_icon: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sensor: Mapped[PowerProduction] = relationship(
        "PowerProduction", back_populates="entries"
    )

    def pack_values(self) -> list[Any]:
        return [self.power, self.custom_icon]

    @classmethod
    def from_packed(cls, label: str, values: Any) -> "PowerProductionEntry":
        power = None
        custom_icon = None
        if isinstance(values, (list, tuple)):
            if values:
                power = values[0]
            if len(values) > 1:
                custom_icon = values[1]
        return cls(type_label=label, power=power, custom_icon=custom_icon)


PowerProduction.entry_model = PowerProductionEntry  # type: ignore[attr-defined]


class Processor(_CollectionSensor):
    __tablename__ = "Processor"
    SID = SID_PROCESSOR

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    entries: Mapped[list["ProcessorEntry"]] = relationship(
        "ProcessorEntry",
        back_populates="sensor",
        cascade="all, delete-orphan",
        order_by="ProcessorEntry.id",
    )

    def __init__(self) -> None:
        super().__init__(stale_time=5)
        self.sid = SID_PROCESSOR

    def update_entry(
        self,
        current_load: Optional[float] = None,
        load_avgs: Optional[Iterable[Optional[float]]] = None,
        clock: Optional[float] = None,
        type_label: Any = None,
    ) -> bool:
        label = ProcessorEntry.normalize_label(type_label)
        if label is None:
            return False
        entry = self._get_or_create_entry(label)
        entry.current_load = current_load
        if load_avgs is None:
            entry.load_avg_1m = None
            entry.load_avg_5m = None
            entry.load_avg_15m = None
        else:
            try:
                avg_list = list(load_avgs)
            except TypeError:
                avg_list = []
            entry.load_avg_1m = avg_list[0] if len(avg_list) > 0 else None
            entry.load_avg_5m = avg_list[1] if len(avg_list) > 1 else None
            entry.load_avg_15m = avg_list[2] if len(avg_list) > 2 else None
        entry.clock = clock
        return True

    def remove_entry(self, type_label: Any = None) -> bool:
        label = ProcessorEntry.normalize_label(type_label)
        if label is None:
            return False
        return self._remove_entry(label)

    def pack(self):  # type: ignore[override]
        return self._pack_entries()

    def unpack(self, packed: Any):  # type: ignore[override]
        return self._unpack_entries(packed)

    __mapper_args__ = {
        "polymorphic_identity": SID_PROCESSOR,
        "with_polymorphic": "*",
    }


class ProcessorEntry(_CollectionEntry):
    __tablename__ = "ProcessorEntry"

    current_load: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    load_avg_1m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    load_avg_5m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    load_avg_15m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    clock: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sensor: Mapped[Processor] = relationship("Processor", back_populates="entries")

    def pack_values(self) -> list[Any]:
        load_avgs = None
        if any(
            value is not None
            for value in (self.load_avg_1m, self.load_avg_5m, self.load_avg_15m)
        ):
            load_avgs = [self.load_avg_1m, self.load_avg_5m, self.load_avg_15m]
        return [self.current_load, load_avgs, self.clock]

    @classmethod
    def from_packed(cls, label: str, values: Any) -> "ProcessorEntry":
        current_load = None
        load_avg_1m = None
        load_avg_5m = None
        load_avg_15m = None
        clock = None
        if isinstance(values, (list, tuple)):
            if values:
                current_load = values[0]
            if len(values) > 1 and isinstance(values[1], (list, tuple)):
                avgs = list(values[1])
                load_avg_1m = avgs[0] if len(avgs) > 0 else None
                load_avg_5m = avgs[1] if len(avgs) > 1 else None
                load_avg_15m = avgs[2] if len(avgs) > 2 else None
            if len(values) > 2:
                clock = values[2]
        return cls(
            type_label=label,
            current_load=current_load,
            load_avg_1m=load_avg_1m,
            load_avg_5m=load_avg_5m,
            load_avg_15m=load_avg_15m,
            clock=clock,
        )


Processor.entry_model = ProcessorEntry  # type: ignore[attr-defined]


from .generic_collections import Custom
from .generic_collections import CustomEntry
from .generic_collections import Fuel
from .generic_collections import FuelEntry
from .generic_collections import NonVolatileMemory
from .generic_collections import NonVolatileMemoryEntry
from .generic_collections import RandomAccessMemory
from .generic_collections import RandomAccessMemoryEntry
from .generic_collections import Tank
from .generic_collections import TankEntry


__all__ = [
    "Custom",
    "CustomEntry",
    "Fuel",
    "FuelEntry",
    "NonVolatileMemory",
    "NonVolatileMemoryEntry",
    "PowerConsumption",
    "PowerConsumptionEntry",
    "PowerProduction",
    "PowerProductionEntry",
    "Processor",
    "ProcessorEntry",
    "RandomAccessMemory",
    "RandomAccessMemoryEntry",
    "Tank",
    "TankEntry",
]
