"""SQLAlchemy model for Reticulum transport telemetry."""

from __future__ import annotations

from typing import Any

from msgpack import packb, unpackb
from sqlalchemy import Boolean, Float, ForeignKey, Integer, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from .sensor import Sensor
from .sensor_enum import SID_RNS_TRANSPORT


def _encode_payload(payload: Any) -> bytes | None:
    """Serialize ``payload`` with msgpack if it is not ``None``."""

    if payload is None:
        return None
    return packb(payload, use_bin_type=True)


def _decode_payload(blob: bytes | None) -> Any:
    """Deserialize msgpack ``blob`` into Python objects."""

    if blob is None:
        return None
    return unpackb(blob, strict_map_key=False)


class RNSTransport(Sensor):
    """Telemetry sensor describing the local Reticulum transport state."""

    __tablename__ = "RNSTransport"

    SID = SID_RNS_TRANSPORT

    id: Mapped[int] = mapped_column(
        ForeignKey("Sensor.id", ondelete="CASCADE"), primary_key=True
    )
    transport_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    transport_identity: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    transport_uptime: Mapped[int | None] = mapped_column(Integer, nullable=True)
    traffic_rxb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    traffic_txb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speed_rx: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_tx: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_rx_inst: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_tx_inst: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_used: Mapped[float | None] = mapped_column(Float, nullable=True)
    interface_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    link_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    interfaces_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    path_table_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    ifstats_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    extra_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if "stale_time" not in kwargs:
            kwargs["stale_time"] = 60
        super().__init__(*args, **kwargs)
        self.sid = self.SID

    @property
    def interfaces(self) -> Any:
        """Return the decoded interface list or mapping."""

        return _decode_payload(self.interfaces_blob)

    @interfaces.setter
    def interfaces(self, value: Any) -> None:
        self.interfaces_blob = _encode_payload(value)

    @property
    def path_table(self) -> Any:
        return _decode_payload(self.path_table_blob)

    @path_table.setter
    def path_table(self, value: Any) -> None:
        self.path_table_blob = _encode_payload(value)

    @property
    def ifstats(self) -> Any:
        return _decode_payload(self.ifstats_blob)

    @ifstats.setter
    def ifstats(self, value: Any) -> None:
        self.ifstats_blob = _encode_payload(value)

    @property
    def extras(self) -> Any:
        return _decode_payload(self.extra_blob)

    @extras.setter
    def extras(self, value: Any) -> None:
        self.extra_blob = _encode_payload(value)

    def _populate_counts(self, interfaces: Any) -> None:
        if self.interface_count is not None or interfaces is None:
            return
        if hasattr(interfaces, "__len__"):
            try:
                self.interface_count = len(interfaces)  # type: ignore[arg-type]
                return
            except TypeError:
                pass
        try:
            self.interface_count = sum(1 for _ in interfaces)  # type: ignore[arg-type]
        except TypeError:
            pass

    def pack(self) -> dict[str, Any] | None:  # type: ignore[override]
        extras = self.extras or {}
        payload: dict[str, Any] = dict(extras)

        interfaces = self.interfaces
        path_table = self.path_table
        ifstats = self.ifstats

        if ifstats is not None and interfaces is not None:
            if isinstance(ifstats, dict) and "interfaces" not in ifstats:
                merged = dict(ifstats)
                merged["interfaces"] = interfaces
                ifstats = merged
        elif interfaces is not None:
            ifstats = {"interfaces": interfaces}

        interface_count = self.interface_count
        if interface_count is None and isinstance(interfaces, list):
            interface_count = len(interfaces)

        payload.update(
            {
                "transport_enabled": bool(self.transport_enabled),
                "transport_identity": (
                    bytes(self.transport_identity) if self.transport_identity else None
                ),
                "transport_uptime": self.transport_uptime,
                "traffic_rxb": self.traffic_rxb,
                "traffic_txb": self.traffic_txb,
                "speed_rx": self.speed_rx,
                "speed_tx": self.speed_tx,
                "speed_rx_inst": self.speed_rx_inst,
                "speed_tx_inst": self.speed_tx_inst,
                "memory_used": self.memory_used,
                "interface_count": interface_count,
                "link_count": self.link_count,
            }
        )

        if interfaces is not None:
            payload["interfaces"] = interfaces
        if path_table is not None:
            payload["path_table"] = path_table
        if ifstats is not None:
            payload["ifstats"] = ifstats

        return payload

    def unpack(self, packed: Any) -> Any:  # type: ignore[override]
        if packed is None or not isinstance(packed, dict):
            return None

        data = dict(packed)

        interfaces = data.pop("interfaces", None)
        ifstats = data.pop("ifstats", None)
        path_table = data.pop("path_table", None)

        if interfaces is None and isinstance(ifstats, dict):
            maybe_interfaces = ifstats.get("interfaces")
            if maybe_interfaces is not None:
                interfaces = maybe_interfaces

        self.interfaces = interfaces
        self.ifstats = ifstats
        self.path_table = path_table

        self.transport_enabled = bool(
            data.pop("transport_enabled", self.transport_enabled)
        )
        self.transport_identity = data.pop(
            "transport_identity", self.transport_identity
        )
        self.transport_uptime = data.pop("transport_uptime", self.transport_uptime)
        self.traffic_rxb = data.pop("traffic_rxb", self.traffic_rxb)
        self.traffic_txb = data.pop("traffic_txb", self.traffic_txb)
        self.speed_rx = data.pop("speed_rx", self.speed_rx)
        self.speed_tx = data.pop("speed_tx", self.speed_tx)
        self.speed_rx_inst = data.pop("speed_rx_inst", self.speed_rx_inst)
        self.speed_tx_inst = data.pop("speed_tx_inst", self.speed_tx_inst)
        self.memory_used = data.pop("memory_used", self.memory_used)
        self.interface_count = data.pop("interface_count", self.interface_count)
        self.link_count = data.pop("link_count", self.link_count)

        self._populate_counts(interfaces)

        self.extras = data if data else None

        return packed

    __mapper_args__ = {
        "polymorphic_identity": SID_RNS_TRANSPORT,
        "with_polymorphic": "*",
    }


__all__ = ["RNSTransport"]
