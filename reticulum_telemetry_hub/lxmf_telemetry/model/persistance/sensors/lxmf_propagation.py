"""SQLAlchemy model for LXMF propagation telemetry data."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import Base
from .sensor import Sensor
from .sensor_enum import SID_LXMF_PROPAGATION


def _decode_hash(value: Any) -> bytes | None:
    """Normalize Sideband hash values to ``bytes``."""

    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            # Sideband transports hashes as hex-encoded strings in some cases
            if len(text) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in text):
                return bytes.fromhex(text)
        except ValueError:
            pass
        return text.encode()
    return None


def _encode_hash(value: bytes | bytearray | memoryview | None) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    return None


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _maybe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "0", "false", "no", "off"}:
            return False
        if lowered in {"1", "true", "yes", "on"}:
            return True
    return bool(value)


class LXMFPropagationPeer(Base):
    """Per-peer telemetry as reported by the LXMF propagation daemon."""

    __tablename__ = "LXMFPropagationPeer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    propagation_id: Mapped[int] = mapped_column(
        ForeignKey("LXMFPropagation.id", ondelete="CASCADE")
    )
    propagation: Mapped["LXMFPropagation"] = relationship(
        "LXMFPropagation", back_populates="peers"
    )

    peer_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    peer_type: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    alive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_heard: Mapped[float | None] = mapped_column(Float, nullable=True)
    next_sync_attempt: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_sync_attempt: Mapped[float | None] = mapped_column(Float, nullable=True)
    sync_backoff: Mapped[float | None] = mapped_column(Float, nullable=True)
    peering_timebase: Mapped[float | None] = mapped_column(Float, nullable=True)
    ler: Mapped[float | None] = mapped_column(Float, nullable=True)
    str_value: Mapped[float | None] = mapped_column("str", Float, nullable=True)
    transfer_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    network_distance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rx_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tx_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    messages_offered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    messages_outgoing: Mapped[int | None] = mapped_column(Integer, nullable=True)
    messages_incoming: Mapped[int | None] = mapped_column(Integer, nullable=True)
    messages_unhandled: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def to_payload(self) -> dict[str, Any]:
        messages = {
            "offered": self.messages_offered,
            "outgoing": self.messages_outgoing,
            "incoming": self.messages_incoming,
            "unhandled": self.messages_unhandled,
        }
        return {
            "type": self.peer_type,
            "state": self.state,
            "alive": bool(self.alive) if self.alive is not None else False,
            "last_heard": self.last_heard,
            "next_sync_attempt": self.next_sync_attempt,
            "last_sync_attempt": self.last_sync_attempt,
            "sync_backoff": self.sync_backoff,
            "peering_timebase": self.peering_timebase,
            "ler": self.ler,
            "str": self.str_value,
            "transfer_limit": self.transfer_limit,
            "network_distance": self.network_distance,
            "rx_bytes": self.rx_bytes,
            "tx_bytes": self.tx_bytes,
            "messages": messages,
        }

    def update_from_payload(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return

        peer_type = payload.get("type")
        if peer_type is not None:
            self.peer_type = str(peer_type)

        state = payload.get("state")
        if state is not None:
            self.state = str(state)

        alive = _maybe_bool(payload.get("alive"))
        self.alive = alive

        self.last_heard = _maybe_float(payload.get("last_heard"))
        self.next_sync_attempt = _maybe_float(payload.get("next_sync_attempt"))
        self.last_sync_attempt = _maybe_float(payload.get("last_sync_attempt"))
        self.sync_backoff = _maybe_float(payload.get("sync_backoff"))
        self.peering_timebase = _maybe_float(payload.get("peering_timebase"))
        self.ler = _maybe_float(payload.get("ler"))
        self.str_value = _maybe_float(payload.get("str"))
        self.transfer_limit = _maybe_int(payload.get("transfer_limit"))
        self.network_distance = _maybe_int(payload.get("network_distance"))
        self.rx_bytes = _maybe_int(payload.get("rx_bytes"))
        self.tx_bytes = _maybe_int(payload.get("tx_bytes"))

        messages = payload.get("messages")
        if isinstance(messages, dict):
            self.messages_offered = _maybe_int(messages.get("offered"))
            self.messages_outgoing = _maybe_int(messages.get("outgoing"))
            self.messages_incoming = _maybe_int(messages.get("incoming"))
            self.messages_unhandled = _maybe_int(messages.get("unhandled"))


class LXMFPropagation(Sensor):
    """Telemetry sensor describing LXMF propagation state."""

    __tablename__ = "LXMFPropagation"

    SID = SID_LXMF_PROPAGATION

    id: Mapped[int] = mapped_column(
        ForeignKey("Sensor.id", ondelete="CASCADE"), primary_key=True
    )
    destination_hash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    identity_hash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    uptime: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    propagation_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    autopeer_maxdepth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_static_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    message_store_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message_store_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message_store_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    client_messages_received: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_messages_served: Mapped[int | None] = mapped_column(Integer, nullable=True)

    unpeered_incoming: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unpeered_rx_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    static_peers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_peers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_peers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_peers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unreachable_peers: Mapped[int | None] = mapped_column(Integer, nullable=True)

    peered_rx_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peered_tx_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peered_offered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peered_outgoing: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peered_incoming: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peered_unhandled: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peered_max_unhandled: Mapped[int | None] = mapped_column(Integer, nullable=True)

    peers: Mapped[list[LXMFPropagationPeer]] = relationship(
        LXMFPropagationPeer,
        back_populates="propagation",
        cascade="all, delete-orphan",
        order_by="LXMFPropagationPeer.id",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if "stale_time" not in kwargs:
            kwargs["stale_time"] = 300
        super().__init__(*args, **kwargs)
        self.sid = self.SID

    def _ensure_peer_aggregates(self) -> dict[str, int]:
        total = len(self.peers)
        active = sum(1 for peer in self.peers if peer.alive)
        rx_sum = sum(peer.rx_bytes or 0 for peer in self.peers)
        tx_sum = sum(peer.tx_bytes or 0 for peer in self.peers)
        offered_sum = sum(peer.messages_offered or 0 for peer in self.peers)
        outgoing_sum = sum(peer.messages_outgoing or 0 for peer in self.peers)
        incoming_sum = sum(peer.messages_incoming or 0 for peer in self.peers)
        unhandled_sum = sum(peer.messages_unhandled or 0 for peer in self.peers)
        max_unhandled = (
            max((peer.messages_unhandled or 0 for peer in self.peers), default=0)
            if self.peers
            else 0
        )

        self.total_peers = total
        self.active_peers = active
        self.unreachable_peers = total - active
        self.peered_rx_bytes = rx_sum
        self.peered_tx_bytes = tx_sum
        self.peered_offered = offered_sum
        self.peered_outgoing = outgoing_sum
        self.peered_incoming = incoming_sum
        self.peered_unhandled = unhandled_sum
        self.peered_max_unhandled = max_unhandled

        return {
            "total_peers": total,
            "active_peers": active,
            "unreachable_peers": total - active,
            "peered_rx_bytes": rx_sum,
            "peered_tx_bytes": tx_sum,
            "peered_offered": offered_sum,
            "peered_outgoing": outgoing_sum,
            "peered_incoming": incoming_sum,
            "peered_unhandled": unhandled_sum,
            "peered_max_unhandled": max_unhandled,
        }

    def _pack_message_store(self) -> dict[str, Any] | None:
        payload = {
            "count": self.message_store_count,
            "bytes": self.message_store_bytes,
            "limit": self.message_store_limit,
        }
        if any(value is not None for value in payload.values()):
            return payload
        return None

    def _pack_clients(self) -> dict[str, Any] | None:
        payload = {
            "client_propagation_messages_received": self.client_messages_received,
            "client_propagation_messages_served": self.client_messages_served,
        }
        if any(value is not None for value in payload.values()):
            return payload
        return None

    def _pack_peers(self) -> dict[bytes, dict[str, Any]]:
        peers: dict[bytes, dict[str, Any]] = {}
        for peer in self.peers:
            key = _encode_hash(peer.peer_hash)
            if key is None:
                continue
            peers[key] = peer.to_payload()
        return peers

    def pack(self) -> dict[str, Any] | None:  # type: ignore[override]
        totals = self._ensure_peer_aggregates()
        peers_payload = self._pack_peers()

        payload: dict[str, Any] = {
            "destination_hash": _encode_hash(self.destination_hash),
            "identity_hash": _encode_hash(self.identity_hash),
            "uptime": self.uptime,
            "delivery_limit": self.delivery_limit,
            "propagation_limit": self.propagation_limit,
            "autopeer_maxdepth": self.autopeer_maxdepth,
            "from_static_only": (
                bool(self.from_static_only)
                if self.from_static_only is not None
                else None
            ),
            "unpeered_propagation_incoming": self.unpeered_incoming,
            "unpeered_propagation_rx_bytes": self.unpeered_rx_bytes,
            "static_peers": self.static_peers,
            "total_peers": totals["total_peers"],
            "active_peers": totals["active_peers"],
            "unreachable_peers": totals["unreachable_peers"],
            "max_peers": self.max_peers,
            "peered_propagation_rx_bytes": totals["peered_rx_bytes"],
            "peered_propagation_tx_bytes": totals["peered_tx_bytes"],
            "peered_propagation_offered": totals["peered_offered"],
            "peered_propagation_outgoing": totals["peered_outgoing"],
            "peered_propagation_incoming": totals["peered_incoming"],
            "peered_propagation_unhandled": totals["peered_unhandled"],
            "peered_propagation_max_unhandled": totals["peered_max_unhandled"],
            "peers": peers_payload,
        }

        message_store = self._pack_message_store()
        if message_store is not None:
            payload["messagestore"] = message_store

        clients = self._pack_clients()
        if clients is not None:
            payload["clients"] = clients

        if (
            all(
                value in (None, {}, [])
                for key, value in payload.items()
                if key not in {"peers", "messagestore", "clients"}
            )
            and not peers_payload
            and message_store is None
            and clients is None
        ):
            return None

        return payload

    def unpack(self, packed: Any) -> Any:  # type: ignore[override]
        if packed is None or not isinstance(packed, dict):
            return None

        self.destination_hash = _decode_hash(packed.get("destination_hash"))
        self.identity_hash = _decode_hash(packed.get("identity_hash"))
        self.uptime = _maybe_int(packed.get("uptime"))
        self.delivery_limit = _maybe_float(packed.get("delivery_limit"))
        self.propagation_limit = _maybe_float(packed.get("propagation_limit"))
        self.autopeer_maxdepth = _maybe_int(packed.get("autopeer_maxdepth"))
        self.from_static_only = _maybe_bool(packed.get("from_static_only"))

        messagestore = packed.get("messagestore")
        if isinstance(messagestore, dict):
            self.message_store_count = _maybe_int(messagestore.get("count"))
            self.message_store_bytes = _maybe_int(messagestore.get("bytes"))
            self.message_store_limit = _maybe_int(messagestore.get("limit"))

        clients = packed.get("clients")
        if isinstance(clients, dict):
            self.client_messages_received = _maybe_int(
                clients.get("client_propagation_messages_received")
            )
            self.client_messages_served = _maybe_int(
                clients.get("client_propagation_messages_served")
            )

        self.unpeered_incoming = _maybe_int(packed.get("unpeered_propagation_incoming"))
        self.unpeered_rx_bytes = _maybe_int(packed.get("unpeered_propagation_rx_bytes"))

        self.static_peers = _maybe_int(packed.get("static_peers"))
        self.max_peers = _maybe_int(packed.get("max_peers"))

        # aggregated values are recomputed below but preserved if provided
        self.total_peers = _maybe_int(packed.get("total_peers"))
        self.active_peers = _maybe_int(packed.get("active_peers"))
        self.unreachable_peers = _maybe_int(packed.get("unreachable_peers"))
        self.peered_rx_bytes = _maybe_int(packed.get("peered_propagation_rx_bytes"))
        self.peered_tx_bytes = _maybe_int(packed.get("peered_propagation_tx_bytes"))
        self.peered_offered = _maybe_int(packed.get("peered_propagation_offered"))
        self.peered_outgoing = _maybe_int(packed.get("peered_propagation_outgoing"))
        self.peered_incoming = _maybe_int(packed.get("peered_propagation_incoming"))
        self.peered_unhandled = _maybe_int(packed.get("peered_propagation_unhandled"))
        self.peered_max_unhandled = _maybe_int(
            packed.get("peered_propagation_max_unhandled")
        )

        peer_payload = packed.get("peers")
        if isinstance(peer_payload, dict):
            existing = {peer.peer_hash: peer for peer in self.peers}
            updated: list[LXMFPropagationPeer] = []
            for key, peer_data in peer_payload.items():
                peer_hash = _decode_hash(key)
                if peer_hash is None:
                    continue
                peer = existing.pop(peer_hash, None)
                if peer is None:
                    peer = LXMFPropagationPeer(peer_hash=peer_hash)
                    peer.propagation = self
                peer.update_from_payload(peer_data)
                updated.append(peer)
            self.peers[:] = updated
        else:
            self.peers[:] = []

        self._ensure_peer_aggregates()

        return packed

    __mapper_args__ = {
        "polymorphic_identity": SID_LXMF_PROPAGATION,
        "with_polymorphic": "*",
    }


__all__ = ["LXMFPropagation", "LXMFPropagationPeer"]
