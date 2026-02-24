"""Helpers for building announce capability payloads."""

from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Callable
from typing import Iterable
from typing import Mapping
from typing import Optional

import msgpack
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator


CAPABILITY_APP = "rch"
CAPABILITY_SCHEMA = 1
CAPABILITY_PRIORITY = [
    "topic_broker",
    "group_chat",
    "telemetry_relay",
    "attachments",
    "tak_bridge",
    "federation",
]
OPTIONAL_FIELDS_ORDER = ["ts", "roles", "rch_version"]
_CAPABILITY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class AnnounceCapabilitiesConfig:
    """Configuration toggles for capability announces."""

    enabled: bool
    max_bytes: int
    include_version: bool
    include_timestamp: bool


@dataclass(frozen=True)
class CapabilityEncoder:
    """Container for capability payload encoding."""

    name: str
    encode: Callable[[Mapping[str, object]], bytes]
    decode: Callable[[bytes], Mapping[str, object]]


@dataclass(frozen=True)
class CapabilityEncodingResult:
    """Snapshot of the encoded capability payload."""

    payload: dict[str, object]
    encoded: bytes
    encoded_size_bytes: int
    truncated: bool
    encoder: str


class AnnounceCapabilitiesPayload(BaseModel):
    """Schema for RCH announce capability payloads."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    app: str = Field(default=CAPABILITY_APP)
    schema_version: int = Field(default=CAPABILITY_SCHEMA, alias="schema")
    rch_version: Optional[str] = None
    caps: list[str] = Field(default_factory=list)
    roles: Optional[list[str]] = None
    ts: Optional[int] = None

    @field_validator("app")
    @classmethod
    def _validate_app(cls, value: str) -> str:
        """Ensure the app marker stays constant."""

        if value != CAPABILITY_APP:
            raise ValueError("app must be 'rch'")
        return value

    @field_validator("schema_version")
    @classmethod
    def _validate_schema(cls, value: int) -> int:
        """Ensure schema versions are positive integers."""

        if value < 1:
            raise ValueError("schema must be >= 1")
        return value

    @field_validator("caps", mode="before")
    @classmethod
    def _validate_caps(cls, value: object) -> list[str]:
        """Normalize and validate capability identifiers."""

        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("caps must be a list of strings")
        normalized: list[str] = []
        for entry in value:
            if not isinstance(entry, str):
                raise TypeError("caps entries must be strings")
            cleaned = entry.strip().lower()
            if not cleaned:
                continue
            if not _CAPABILITY_NAME_PATTERN.fullmatch(cleaned):
                raise ValueError("caps entries must be lowercase snake_case")
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @field_validator("roles", mode="before")
    @classmethod
    def _validate_roles(cls, value: object) -> Optional[list[str]]:
        """Normalize optional role identifiers."""

        if value is None:
            return None
        if not isinstance(value, list):
            raise TypeError("roles must be a list of strings")
        cleaned: list[str] = []
        for entry in value:
            if not isinstance(entry, str):
                raise TypeError("roles entries must be strings")
            role = entry.strip()
            if not role:
                continue
            if role not in cleaned:
                cleaned.append(role)
        return cleaned or None


def select_capability_encoder() -> CapabilityEncoder:
    """Return the preferred capability encoder."""

    try:  # pragma: no cover - optional dependency
        import cbor2  # type: ignore
    except ImportError:
        return _msgpack_encoder()

    def _encode(payload: Mapping[str, object]) -> bytes:
        return cbor2.dumps(payload, canonical=True)

    def _decode(raw: bytes) -> Mapping[str, object]:
        return cbor2.loads(raw)

    return CapabilityEncoder(name="cbor", encode=_encode, decode=_decode)


def _msgpack_encoder() -> CapabilityEncoder:
    """Return the msgpack capability encoder."""

    def _encode(payload: Mapping[str, object]) -> bytes:
        return msgpack.packb(payload, use_bin_type=True)

    def _decode(raw: bytes) -> Mapping[str, object]:
        return msgpack.unpackb(raw, raw=False)

    return CapabilityEncoder(name="msgpack", encode=_encode, decode=_decode)


def normalize_capability_list(
    capabilities: Iterable[str],
    *,
    priority: Iterable[str] | None = None,
) -> list[str]:
    """Normalize capability identifiers into a deterministic list.

    Args:
        capabilities (Iterable[str]): Raw capability identifiers.
        priority (Iterable[str] | None): Optional priority ordering.

    Returns:
        list[str]: Deterministic capability ordering.
    """

    requested: list[str] = []
    seen: set[str] = set()
    for entry in capabilities:
        if not isinstance(entry, str):
            continue
        cleaned = entry.strip().lower()
        if not cleaned or cleaned in seen:
            continue
        requested.append(cleaned)
        seen.add(cleaned)

    if priority is None:
        return requested

    ordered: list[str] = []
    priority_list = list(priority)
    for entry in priority_list:
        if entry in seen:
            ordered.append(entry)
            seen.remove(entry)

    if seen:
        extras = sorted(seen)
        ordered.extend(extras)

    return ordered


def build_capability_payload(
    *,
    rch_version: Optional[str],
    caps: Iterable[str],
    roles: Optional[Iterable[str]],
    include_timestamp: bool,
    timestamp: Optional[int] = None,
) -> AnnounceCapabilitiesPayload:
    """Build a validated capability payload model.

    Args:
        rch_version (Optional[str]): Optional RCH version string.
        caps (Iterable[str]): Capability identifiers to include.
        roles (Optional[Iterable[str]]): Optional role identifiers.
        include_timestamp (bool): Whether to include epoch timestamp.
        timestamp (Optional[int]): Optional timestamp override.

    Returns:
        AnnounceCapabilitiesPayload: Validated capability payload model.
    """

    normalized_caps = normalize_capability_list(caps, priority=CAPABILITY_PRIORITY)
    normalized_roles = None
    if roles is not None:
        normalized_roles = normalize_capability_list(list(roles))
    ts_value = None
    if include_timestamp:
        ts_value = int(timestamp if timestamp is not None else time.time())
    return AnnounceCapabilitiesPayload(
        app=CAPABILITY_APP,
        schema_version=CAPABILITY_SCHEMA,
        rch_version=rch_version or None,
        caps=normalized_caps,
        roles=normalized_roles,
        ts=ts_value,
    )


def encode_capability_payload(
    payload: AnnounceCapabilitiesPayload,
    *,
    encoder: CapabilityEncoder,
    max_bytes: int,
) -> CapabilityEncodingResult:
    """Encode a capability payload with size truncation.

    Args:
        payload (AnnounceCapabilitiesPayload): Capability payload model.
        encoder (CapabilityEncoder): Encoder to use.
        max_bytes (int): Maximum encoded payload size.

    Returns:
        CapabilityEncodingResult: Encoded payload metadata.
    """

    limit = max(1, int(max_bytes))
    working_payload = payload.model_dump(exclude_none=True, by_alias=True)
    encoded = encoder.encode(working_payload)
    if len(encoded) <= limit:
        return CapabilityEncodingResult(
            payload=working_payload,
            encoded=encoded,
            encoded_size_bytes=len(encoded),
            truncated=False,
            encoder=encoder.name,
        )

    truncated = True
    working_payload = dict(working_payload)

    for field_name in OPTIONAL_FIELDS_ORDER:
        if field_name in working_payload:
            working_payload.pop(field_name, None)
            encoded = encoder.encode(working_payload)
            if len(encoded) <= limit:
                return CapabilityEncodingResult(
                    payload=working_payload,
                    encoded=encoded,
                    encoded_size_bytes=len(encoded),
                    truncated=truncated,
                    encoder=encoder.name,
                )

    caps = list(working_payload.get("caps", []))
    for count in range(len(caps), -1, -1):
        working_payload["caps"] = caps[:count]
        encoded = encoder.encode(working_payload)
        if len(encoded) <= limit:
            return CapabilityEncodingResult(
                payload=working_payload,
                encoded=encoded,
                encoded_size_bytes=len(encoded),
                truncated=truncated,
                encoder=encoder.name,
            )

    encoded = encoder.encode(working_payload)
    return CapabilityEncodingResult(
        payload=working_payload,
        encoded=encoded,
        encoded_size_bytes=len(encoded),
        truncated=truncated,
        encoder=encoder.name,
    )


def append_capabilities_to_announce_app_data(
    app_data: bytes | bytearray | memoryview | None,
    capability_payload: bytes,
) -> bytes:
    """Return announce app data with capabilities appended.

    Args:
        app_data (bytes | bytearray | memoryview | None): Existing announce payload.
        capability_payload (bytes): Encoded capability payload to append.

    Returns:
        bytes: Msgpack-encoded announce app data.
    """

    base_list = _decode_announce_list(app_data)
    base_list = list(base_list[:2])
    if len(base_list) < 2:
        base_list.extend([None] * (2 - len(base_list)))
    base_list.append(capability_payload)
    return msgpack.packb(base_list, use_bin_type=True)


def _decode_announce_list(
    app_data: bytes | bytearray | memoryview | None,
) -> list[object]:
    """Decode announce app data into a list of fields.

    Args:
        app_data (bytes | bytearray | memoryview | None): Raw announce data.

    Returns:
        list[object]: Decoded announce list.
    """

    if app_data is None:
        return [None, None]
    if isinstance(app_data, memoryview):
        app_data = app_data.tobytes()
    if not app_data:
        return [None, None]
    if isinstance(app_data, (bytes, bytearray)):
        try:
            decoded = msgpack.unpackb(app_data, raw=False)
        except Exception:
            decoded = None
        if isinstance(decoded, list):
            return list(decoded)
        return [bytes(app_data), None]
    return [None, None]


def decode_inbound_capability_payload(
    payload: object,
) -> Mapping[str, object] | None:
    """Decode an inbound announce capability payload.

    Args:
        payload (object): Raw payload in announce app-data slot index ``2``.

    Returns:
        Mapping[str, object] | None: Normalized capability payload when valid.
    """

    raw: bytes | None = None
    if isinstance(payload, memoryview):
        raw = payload.tobytes()
    elif isinstance(payload, (bytes, bytearray)):
        raw = bytes(payload)
    if not raw:
        return None

    decoders: list[Callable[[bytes], object]] = []
    try:  # pragma: no cover - optional dependency
        import cbor2  # type: ignore
    except ImportError:
        cbor2 = None

    if cbor2 is not None:  # pragma: no branch
        decoders.append(lambda value: cbor2.loads(value))
    decoders.append(lambda value: msgpack.unpackb(value, raw=False))

    for decode in decoders:
        try:
            decoded = decode(raw)
        except Exception:
            continue
        if not isinstance(decoded, Mapping):
            continue
        candidate = dict(decoded)
        raw_caps = candidate.get("caps")
        if isinstance(raw_caps, list):
            candidate["caps"] = [
                str(item).strip().lower()
                for item in raw_caps
                if str(item).strip()
            ]
        try:
            normalized = AnnounceCapabilitiesPayload.model_validate(candidate)
        except Exception:
            continue
        return normalized.model_dump(exclude_none=True, by_alias=True)
    return None
