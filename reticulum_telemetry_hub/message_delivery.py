"""Shared delivery-contract helpers for topic routing and message envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import uuid
from typing import Any


DELIVERY_ENVELOPE_FIELD = "RTHDelivery"
DELIVERY_SCHEMA_VERSION = "1"
DEFAULT_TTL_SECONDS = 300
DEFAULT_PRIORITY = 0
MAX_CLOCK_SKEW_SECONDS = 300
ACCEPTED_CONTENT_TYPES = frozenset(
    {
        "text/plain; schema=lxmf.chat.v1",
        "application/json; schema=event.v1",
        "application/cbor; schema=lxmf.v1",
    }
)
REQUIRED_ENVELOPE_FIELDS = frozenset(
    {
        "Content-Type",
        "Schema-Version",
        "TTL",
        "Priority",
        "Sender",
        "Message-ID",
        "Born",
    }
)


class DeliveryContractError(ValueError):
    """Raised when delivery metadata violates the contract."""


@dataclass(frozen=True)
class DeliveryEnvelope:
    """Normalized outbound/inbound delivery metadata."""

    message_id: str
    content_type: str
    schema_version: str
    ttl_seconds: int
    priority: int
    sender: str
    born_at_ms: int
    created_at: str | None = None
    topic_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a transport-safe dictionary representation."""

        payload: dict[str, object] = {
            "Message-ID": self.message_id,
            "Content-Type": self.content_type,
            "Schema-Version": self.schema_version,
            "TTL": self.ttl_seconds,
            "Priority": self.priority,
            "Sender": self.sender,
            "Born": self.born_at_ms,
        }
        if self.created_at:
            payload["Created-At"] = self.created_at
        if self.topic_id:
            payload["TopicID"] = self.topic_id
        return payload


def normalize_topic_id(value: object) -> str | None:
    """Return the canonical string form for a TopicID."""

    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value.hex
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        if not data:
            return None
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return data.hex()
        normalized = text.strip()
        return normalized or None
    text = str(value).strip()
    if not text:
        return None
    try:
        return uuid.UUID(text).hex
    except (ValueError, AttributeError, TypeError):
        return text


def serialize_topic_id(value: object) -> bytes:
    """Serialize a TopicID into UTF-8 bytes using the canonical string form."""

    topic_id = normalize_topic_id(value)
    if topic_id is None:
        raise DeliveryContractError("TopicID is required")
    return topic_id.encode("utf-8")


def deserialize_topic_id(payload: bytes) -> str:
    """Deserialize UTF-8 TopicID bytes back into canonical string form."""

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DeliveryContractError("TopicID payload must be UTF-8") from exc
    topic_id = normalize_topic_id(text)
    if topic_id is None:
        raise DeliveryContractError("TopicID payload is empty")
    return topic_id


def normalize_message_id(value: object | None = None) -> str:
    """Return a stable Message-ID string."""

    if value is None:
        return uuid.uuid4().hex
    if isinstance(value, uuid.UUID):
        return value.hex
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        if data:
            return data.hex()
        return uuid.uuid4().hex
    text = str(value).strip()
    if not text:
        return uuid.uuid4().hex
    try:
        return uuid.UUID(text).hex
    except (ValueError, AttributeError, TypeError):
        return text.lower()


def classify_delivery_mode(
    *,
    topic_id: str | None,
    destination: str | None,
) -> str:
    """Return the routing mode for the provided delivery coordinates."""

    normalized_topic = normalize_topic_id(topic_id)
    normalized_destination = normalize_hash(destination)
    if normalized_topic and normalized_destination:
        raise DeliveryContractError(
            "topic_id and destination are mutually exclusive routing modes"
        )
    if normalized_destination:
        return "targeted"
    if normalized_topic:
        return "fanout"
    return "broadcast"


def normalize_hash(value: object) -> str | None:
    """Return a lowercase hex or trimmed string hash representation."""

    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return data.hex().lower() if data else None
    text = str(value).strip().lower()
    return text or None


def utc_now_ms() -> int:
    """Return the current UTC timestamp in epoch milliseconds."""

    return int(datetime.now(timezone.utc).timestamp() * 1000)


def utc_now_rfc3339() -> str:
    """Return the current UTC timestamp as RFC3339."""

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_delivery_envelope(
    *,
    sender: str,
    message_id: str | None = None,
    topic_id: str | None = None,
    content_type: str = "text/plain; schema=lxmf.chat.v1",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    priority: int = DEFAULT_PRIORITY,
    born_at_ms: int | None = None,
    created_at: str | None = None,
) -> DeliveryEnvelope:
    """Create a validated delivery envelope."""

    normalized_sender = normalize_hash(sender)
    if normalized_sender is None:
        raise DeliveryContractError("Sender is required")
    normalized_content_type = str(content_type or "").strip().lower()
    if normalized_content_type not in ACCEPTED_CONTENT_TYPES:
        raise DeliveryContractError(
            f"Unsupported Content-Type '{content_type}'"
        )
    ttl_value = int(ttl_seconds)
    if ttl_value <= 0:
        raise DeliveryContractError("TTL must be greater than zero")
    priority_value = int(priority)
    born_value = int(born_at_ms if born_at_ms is not None else utc_now_ms())
    envelope = DeliveryEnvelope(
        message_id=normalize_message_id(message_id),
        content_type=normalized_content_type,
        schema_version=DELIVERY_SCHEMA_VERSION,
        ttl_seconds=ttl_value,
        priority=priority_value,
        sender=normalized_sender,
        born_at_ms=born_value,
        created_at=created_at or utc_now_rfc3339(),
        topic_id=normalize_topic_id(topic_id),
    )
    validate_delivery_envelope(envelope.to_dict(), now_ms=born_value)
    return envelope


def extract_delivery_envelope(fields: dict | None) -> dict[str, Any] | None:
    """Return the raw delivery envelope when present."""

    if not isinstance(fields, dict):
        return None
    payload = fields.get(DELIVERY_ENVELOPE_FIELD)
    if isinstance(payload, dict):
        return dict(payload)
    return None


def attach_delivery_envelope(
    fields: dict | None,
    envelope: DeliveryEnvelope,
) -> dict[str | int, object]:
    """Return fields merged with the delivery envelope."""

    merged: dict[str | int, object] = dict(fields or {})
    merged[DELIVERY_ENVELOPE_FIELD] = envelope.to_dict()
    return merged


def validate_delivery_envelope(
    payload: dict[str, Any] | None,
    *,
    now_ms: int | None = None,
    max_clock_skew_seconds: int = MAX_CLOCK_SKEW_SECONDS,
) -> DeliveryEnvelope | None:
    """Validate a raw delivery envelope payload."""

    if payload is None:
        return None
    missing = sorted(REQUIRED_ENVELOPE_FIELDS.difference(payload))
    if missing:
        raise DeliveryContractError(
            "Missing delivery fields: " + ", ".join(missing)
        )
    content_type = str(payload.get("Content-Type") or "").strip().lower()
    if content_type not in ACCEPTED_CONTENT_TYPES:
        raise DeliveryContractError(
            f"Unsupported Content-Type '{payload.get('Content-Type')}'"
        )
    schema_version = str(payload.get("Schema-Version") or "").strip()
    if schema_version != DELIVERY_SCHEMA_VERSION:
        raise DeliveryContractError(
            f"Unsupported Schema-Version '{schema_version}'"
        )
    ttl_seconds = int(payload.get("TTL"))
    if ttl_seconds <= 0:
        raise DeliveryContractError("TTL must be greater than zero")
    priority = int(payload.get("Priority"))
    sender = normalize_hash(payload.get("Sender"))
    if sender is None:
        raise DeliveryContractError("Sender is required")
    message_id = normalize_message_id(payload.get("Message-ID"))
    born_at_ms = int(payload.get("Born"))
    current_ms = int(now_ms if now_ms is not None else utc_now_ms())
    future_skew_ms = born_at_ms - current_ms
    if future_skew_ms > max_clock_skew_seconds * 1000:
        raise DeliveryContractError("Clock skew exceeds delivery budget")
    age_ms = current_ms - born_at_ms
    if age_ms > ttl_seconds * 1000:
        raise DeliveryContractError("Message exceeded TTL")
    created_at = payload.get("Created-At")
    if created_at is not None:
        created_at_text = str(created_at).strip()
        if not created_at_text:
            created_at = None
        else:
            _parse_rfc3339_utc(created_at_text)
            created_at = created_at_text
    return DeliveryEnvelope(
        message_id=message_id,
        content_type=content_type,
        schema_version=schema_version,
        ttl_seconds=ttl_seconds,
        priority=priority,
        sender=sender,
        born_at_ms=born_at_ms,
        created_at=created_at,
        topic_id=normalize_topic_id(payload.get("TopicID")),
    )


def _parse_rfc3339_utc(value: str) -> datetime:
    """Parse an RFC3339 UTC timestamp or raise a contract error."""

    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise DeliveryContractError("Created-At must be RFC3339 UTC") from exc
    if parsed.tzinfo is None:
        raise DeliveryContractError("Created-At must include a UTC offset")
    return parsed.astimezone(timezone.utc)
