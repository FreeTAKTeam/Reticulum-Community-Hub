"""REM peer registry, classification, and fanout selection helpers."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Iterable

from reticulum_telemetry_hub.api.models import Client
from reticulum_telemetry_hub.api.models import IdentityStatus
from reticulum_telemetry_hub.api.models import RemPeer
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.api.storage_models import IdentityAnnounceRecord


REM_CLIENT_TYPE = "rem"
GENERIC_LXMF_CLIENT_TYPE = "generic_lxmf"
DEFAULT_REM_MODE = "autonomous"
REM_CONNECTED_MODE = "connected"
REM_REQUIRED_CAPABILITIES = frozenset({"r3akt", "emergencymessages"})
VALID_REM_MODES = frozenset({"autonomous", "semi_autonomous", "connected"})
DEFAULT_ACTIVE_WINDOW = timedelta(minutes=60)


def _ensure_aware(value: datetime | None) -> datetime | None:
    """Return an aware UTC datetime when a value exists."""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


def _dt_ms(value: datetime | None) -> int:
    """Return a Unix epoch in milliseconds for ``value``."""

    resolved = _ensure_aware(value) or _utcnow()
    return int(resolved.timestamp() * 1000)


class RemRegistryService:
    """Source of truth for REM peer classification and mode state."""

    def __init__(self, storage: HubStorage) -> None:
        """Store the shared hub storage used for peer registry lookups."""

        self._storage = storage

    @staticmethod
    def normalize_capabilities(raw_capabilities: object) -> list[str]:
        """Normalize announce capabilities from structured or plain-string input."""

        items: list[str] = []
        if raw_capabilities is None:
            return items
        if isinstance(raw_capabilities, str):
            parts = raw_capabilities.replace(";", ",").replace("|", ",").split(",")
            items.extend(parts)
        elif isinstance(raw_capabilities, (list, tuple, set, frozenset)):
            for item in raw_capabilities:
                if item is not None:
                    items.append(str(item))
        else:
            items.append(str(raw_capabilities))

        normalized: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = str(item or "").strip().lower()
            if not text or text in seen:
                continue
            normalized.append(text)
            seen.add(text)
        return normalized

    @classmethod
    def classify_client_type(cls, capabilities: Iterable[str] | None) -> str:
        """Return the normalized LXMF client type for a capability set."""

        normalized = {str(item or "").strip().lower() for item in capabilities or [] if item}
        if REM_REQUIRED_CAPABILITIES.issubset(normalized):
            return REM_CLIENT_TYPE
        return GENERIC_LXMF_CLIENT_TYPE

    @staticmethod
    def normalize_mode(mode: str | None) -> str:
        """Validate and normalize a REM operating mode."""

        normalized = str(mode or "").strip().lower()
        if normalized not in VALID_REM_MODES:
            raise ValueError(
                "mode must be one of: autonomous, semi_autonomous, connected"
            )
        return normalized

    def record_identity_announce(
        self,
        identity: str,
        *,
        announced_identity_hash: str | None = None,
        display_name: str | None = None,
        source_interface: str | None = None,
        announce_capabilities: object = None,
    ) -> None:
        """Persist announce metadata, normalized capabilities, and client type."""

        capabilities = self.normalize_capabilities(announce_capabilities)
        client_type = self.classify_client_type(capabilities)
        self._storage.upsert_identity_announce(
            identity,
            announced_identity_hash=announced_identity_hash,
            display_name=display_name,
            source_interface=source_interface,
            announce_capabilities=capabilities if announce_capabilities is not None else None,
            client_type=client_type if capabilities else None,
        )

    def get_rem_mode(self, identity: str) -> str:
        """Return the persisted or default REM mode for an identity."""

        record = self._storage.get_identity_rem_mode(identity)
        if record is None:
            return DEFAULT_REM_MODE
        return str(record.mode or DEFAULT_REM_MODE).strip().lower() or DEFAULT_REM_MODE

    def set_rem_mode(self, identity: str, *, mode: str) -> dict[str, object]:
        """Persist a REM mode registration and return the canonical result shape."""

        normalized_identity = str(identity or "").strip().lower()
        if not normalized_identity:
            raise ValueError("identity is required")
        record = self._storage.upsert_identity_rem_mode(
            normalized_identity,
            mode=self.normalize_mode(mode),
        )
        return {
            "identity": normalized_identity,
            "mode": str(record.mode or DEFAULT_REM_MODE).strip().lower() or DEFAULT_REM_MODE,
            "effective_connected_mode": self.effective_connected_mode(),
            "registered_at_ms": _dt_ms(getattr(record, "requested_at", None)),
            "updated_at_ms": _dt_ms(getattr(record, "updated_at", None)),
        }

    def effective_connected_mode(self) -> bool:
        """Return True when any persisted REM registration has enabled connected mode."""

        for record in self._storage.list_identity_rem_modes():
            if str(record.mode or "").strip().lower() == REM_CONNECTED_MODE:
                return True
        return False

    def annotate_client(self, client: Client) -> Client:
        """Attach REM mode and capability flags to a client model."""

        normalized_identity = str(client.identity or "").strip().lower()
        client.client_type = str(client.client_type or GENERIC_LXMF_CLIENT_TYPE).strip().lower() or GENERIC_LXMF_CLIENT_TYPE
        client.announce_capabilities = self.normalize_capabilities(client.announce_capabilities)
        client.is_rem_capable = client.client_type == REM_CLIENT_TYPE
        client.rem_mode = (
            self.get_rem_mode(normalized_identity)
            if normalized_identity and client.is_rem_capable
            else None
        )
        return client

    def annotate_identity_status(self, status: IdentityStatus) -> IdentityStatus:
        """Attach REM mode and capability flags to an identity status model."""

        normalized_identity = str(status.identity or "").strip().lower()
        status.client_type = str(status.client_type or GENERIC_LXMF_CLIENT_TYPE).strip().lower() or GENERIC_LXMF_CLIENT_TYPE
        status.announce_capabilities = self.normalize_capabilities(status.announce_capabilities)
        status.is_rem_capable = status.client_type == REM_CLIENT_TYPE
        status.rem_mode = (
            self.get_rem_mode(normalized_identity)
            if normalized_identity and status.is_rem_capable
            else None
        )
        return status

    def list_active_rem_peers(
        self,
        *,
        active_window: timedelta = DEFAULT_ACTIVE_WINDOW,
    ) -> list[RemPeer]:
        """Return active REM-capable peers that are safe to use as fanout targets."""

        cutoff = _utcnow() - active_window
        moderation = {
            str(record.identity or "").strip().lower(): record
            for record in self._storage.list_identity_states()
            if str(record.identity or "").strip()
        }
        candidates: dict[str, tuple[IdentityAnnounceRecord, str]] = {}
        for record in self._storage.list_identity_announces():
            identity = str(
                record.announced_identity_hash or record.destination_hash or ""
            ).strip().lower()
            if not identity:
                continue
            last_seen = _ensure_aware(getattr(record, "last_seen", None))
            if last_seen is None or last_seen < cutoff:
                continue
            client_type = str(record.client_type or GENERIC_LXMF_CLIENT_TYPE).strip().lower()
            if client_type != REM_CLIENT_TYPE:
                continue
            state = moderation.get(identity)
            if state is not None and (bool(state.is_banned) or bool(state.is_blackholed)):
                continue
            source = str(record.source_interface or "").strip().lower() or "identity"
            existing = candidates.get(identity)
            existing_source = existing[1] if existing is not None else ""
            if existing is None or (
                source == "destination" and existing_source != "destination"
            ):
                candidates[identity] = (record, source)
        peers: list[RemPeer] = []
        for identity, (record, source) in candidates.items():
            capabilities = self.normalize_capabilities(record.announce_capabilities_json)
            destination_hash = str(record.destination_hash or identity).strip().lower()
            if source != "destination":
                destination_hash = identity
            peers.append(
                RemPeer(
                    identity=identity,
                    destination_hash=destination_hash,
                    display_name=str(record.display_name or "").strip() or None,
                    announce_capabilities=capabilities,
                    client_type=str(record.client_type or GENERIC_LXMF_CLIENT_TYPE).strip().lower(),
                    registered_mode=self.get_rem_mode(identity),
                    last_seen=_ensure_aware(getattr(record, "last_seen", None)),
                    status="active",
                )
            )
        return peers

    def build_peer_list_payload(self) -> dict[str, object]:
        """Return the canonical northbound/southbound REM peer list payload."""

        items = [peer.to_dict() for peer in self.list_active_rem_peers()]
        return {
            "effective_connected_mode": self.effective_connected_mode(),
            "items": items,
        }

    def fanout_recipients(self, joined_identities: Iterable[str]) -> dict[str, list[str]]:
        """Return REM and generic recipient buckets for connected-mode fanout."""

        if not self.effective_connected_mode():
            return {"rem": [], "generic": []}

        rem_identities = [peer.identity for peer in self.list_active_rem_peers()]
        rem_set = set(rem_identities)
        moderation = {
            str(record.identity or "").strip().lower(): record
            for record in self._storage.list_identity_states()
            if str(record.identity or "").strip()
        }
        generic: list[str] = []
        seen_generic: set[str] = set()
        for identity in joined_identities:
            normalized = str(identity or "").strip().lower()
            if not normalized or normalized in rem_set or normalized in seen_generic:
                continue
            state = moderation.get(normalized)
            if state is not None and (bool(state.is_banned) or bool(state.is_blackholed)):
                continue
            seen_generic.add(normalized)
            generic.append(normalized)
        return {"rem": rem_identities, "generic": generic}
