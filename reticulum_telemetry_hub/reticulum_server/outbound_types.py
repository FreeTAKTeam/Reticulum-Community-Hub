"""Outbound queue payload and pending-work records."""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from dataclasses import field
from typing import NamedTuple

import RNS

@dataclass
class OutboundPayload:
    """
    Message payload scheduled for outbound delivery.

    Args:
        connection (RNS.Destination): Destination to deliver the message to.
        message_text (str): Plaintext message body to deliver.
        destination_hash (bytes | None): Raw destination hash for diagnostics.
        destination_hex (str | None): Hex-encoded destination hash for logging.
        fields (dict | None): Optional LXMF fields to include with the message.
        sender (RNS.Destination): Sender identity for the message.
        chat_message_id (str | None): Optional persisted chat message identifier.
        message_id (str | None): Canonical transport Message-ID.
        topic_id (str | None): Canonical TopicID used for fan-out.
        route_type (str): ``"broadcast"``, ``"fanout"``, or ``"targeted"``.
        attempts (int): Number of direct-delivery failures observed so far.
        next_attempt_at (float): Monotonic timestamp before the next attempt.
        delivery_mode (str): ``"direct"`` or ``"propagated"``.
        delivery_policy_reason (str | None): Policy reason for the selected mode.
        propagation_node_hash (bytes | None): Selected propagation-node hash.
        propagation_node_hex (str | None): Selected propagation-node hash as hex.
    """

    connection: RNS.Destination
    message_text: str
    destination_hash: bytes | None
    destination_hex: str | None
    fields: dict | None = None
    sender: RNS.Destination | None = None
    chat_message_id: str | None = None
    message_id: str | None = None
    topic_id: str | None = None
    route_type: str = "broadcast"
    attempts: int = 0
    next_attempt_at: float = field(default_factory=time.monotonic)
    enqueued_at: float = field(default_factory=time.monotonic)
    delivery_mode: str = "direct"
    delivery_policy_reason: str | None = None
    propagation_node_hash: bytes | None = None
    propagation_node_hex: str | None = None
    local_propagation_fallback: bool = False
    _attempt_sequence: int = field(default=0, init=False, repr=False)
    _active_attempt_id: int = field(default=0, init=False, repr=False)
    _attempt_lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
        compare=False,
    )


class _PendingReceipt(NamedTuple):
    payload: OutboundPayload
    attempt_id: int
    deadline: float
    registered_at: float


class _PendingDispatch(NamedTuple):
    payload: OutboundPayload
    attempt_id: int
    future: Future[None]
    timed_out_at: float


