"""Identity announce, REM mode, and capability storage methods."""

from __future__ import annotations

from typing import List
import uuid

from sqlalchemy import case
from sqlalchemy import or_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .storage_models import IdentityAnnounceRecord
from .storage_models import IdentityCapabilityGrantRecord
from .storage_models import IdentityRemModeRecord
from .storage_models import IdentityStateRecord
from .storage_models import _utcnow


class IdentityStorageMixin:
    """Identity announce, REM mode, and capability storage methods."""

    def upsert_identity_state(
        self,
        identity: str,
        *,
        is_banned: bool | None = None,
        is_blackholed: bool | None = None,
    ) -> IdentityStateRecord:
        """Insert or update the moderation state for an identity."""

        with self._session_scope() as session:
            record = session.get(IdentityStateRecord, identity)
            if record is None:
                record = IdentityStateRecord(identity=identity)
                session.add(record)
            if is_banned is not None:
                record.is_banned = bool(is_banned)
            if is_blackholed is not None:
                record.is_blackholed = bool(is_blackholed)
            record.updated_at = _utcnow()
            session.commit()
            return record

    def upsert_identity_announce(
        self,
        identity: str,
        *,
        announced_identity_hash: str | None = None,
        display_name: str | None = None,
        source_interface: str | None = None,
        announce_capabilities: list[str] | None = None,
        client_type: str | None = None,
    ) -> IdentityAnnounceRecord:
        """Insert or update Reticulum announce metadata."""

        identity = identity.lower()
        normalized_announced_identity = (
            announced_identity_hash.strip().lower()
            if isinstance(announced_identity_hash, str) and announced_identity_hash.strip()
            else None
        )
        now = _utcnow()
        with self._session_scope() as session:
            insert_values = {
                "destination_hash": identity,
                "announced_identity_hash": normalized_announced_identity,
                "display_name": display_name,
                "announce_capabilities": list(announce_capabilities or []) or None,
                "client_type": client_type,
                "first_seen": now,
                "last_seen": now,
                "last_capability_seen_at": now if announce_capabilities is not None else None,
                "source_interface": source_interface,
            }
            update_values = {"last_seen": now}
            if normalized_announced_identity:
                update_values["announced_identity_hash"] = normalized_announced_identity
            if display_name:
                update_values["display_name"] = display_name
            if source_interface:
                update_values["source_interface"] = source_interface
            if announce_capabilities is not None:
                update_values["announce_capabilities"] = list(announce_capabilities)
                update_values["last_capability_seen_at"] = now
            if client_type:
                update_values["client_type"] = client_type
            stmt = sqlite_insert(IdentityAnnounceRecord.__table__).values(**insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[IdentityAnnounceRecord.destination_hash],
                set_=update_values,
            )
            session.execute(stmt)
            session.commit()
            record = session.get(IdentityAnnounceRecord, identity)
            if record is None:  # pragma: no cover - defensive
                raise RuntimeError("Failed to upsert identity announce record")
            return record

    def get_identity_announce(self, identity: str) -> IdentityAnnounceRecord | None:
        """Return announce metadata for an identity when present."""

        with self._session_scope() as session:
            return self._identity_announce_for_identity(session, identity)

    def get_canonical_identity_announce(self, identity: str) -> IdentityAnnounceRecord | None:
        """Return merged announce metadata keyed by canonical identity."""

        normalized_identity = str(identity or "").strip().lower()
        if not normalized_identity:
            return None
        with self._session_scope() as session:
            return self._identity_announce_map(
                session,
                identities=[normalized_identity],
            ).get(normalized_identity)

    def resolve_identity_destination_hash(self, identity: str) -> str | None:
        """Return the best-known LXMF destination hash for an identity."""

        normalized_identity = str(identity or "").strip().lower()
        if not normalized_identity:
            return None
        with self._session_scope() as session:
            record = (
                session.query(IdentityAnnounceRecord)
                .filter(
                    or_(
                        IdentityAnnounceRecord.destination_hash == normalized_identity,
                        IdentityAnnounceRecord.announced_identity_hash == normalized_identity,
                    )
                )
                .order_by(
                    case(
                        (IdentityAnnounceRecord.source_interface == "destination", 0),
                        (IdentityAnnounceRecord.destination_hash == normalized_identity, 1),
                        else_=2,
                    ),
                    IdentityAnnounceRecord.last_seen.desc(),
                )
                .first()
            )
        if record is None or not record.destination_hash:
            return None
        return str(record.destination_hash).strip().lower() or None

    def resolve_identity_display_names_bulk(
        self,
        identities: list[str],
    ) -> dict[str, str | None]:
        """Resolve display names for many identities with one database roundtrip."""

        normalized_identities = [
            str(identity).strip().lower()
            for identity in identities
            if str(identity).strip()
        ]
        if not normalized_identities:
            return {}
        requested = set(normalized_identities)
        canonical_announces: dict[str, IdentityAnnounceRecord] = {}
        keys_by_canonical: dict[str, set[str]] = {}
        with self._session_scope() as session:
            records = (
                session.query(IdentityAnnounceRecord)
                .filter(
                    or_(
                        IdentityAnnounceRecord.destination_hash.in_(requested),
                        IdentityAnnounceRecord.announced_identity_hash.in_(requested),
                    )
                )
                .all()
            )
            for record in records:
                destination_hash = str(record.destination_hash or "").strip().lower()
                announced_identity_hash = str(record.announced_identity_hash or "").strip().lower()
                canonical_key = announced_identity_hash or destination_hash
                if not canonical_key:
                    continue
                canonical_announces[canonical_key] = self._merge_identity_announce_records(
                    canonical_announces.get(canonical_key),
                    record,
                )
                keys = keys_by_canonical.setdefault(canonical_key, set())
                if destination_hash in requested:
                    keys.add(destination_hash)
                if announced_identity_hash in requested:
                    keys.add(announced_identity_hash)
        resolved_display_names: dict[str, str | None] = {}
        for canonical_key, keys in keys_by_canonical.items():
            display_name = canonical_announces.get(canonical_key).display_name
            for key in keys:
                resolved_display_names[key] = display_name

        return {identity: resolved_display_names.get(identity) for identity in normalized_identities}

    def list_identity_announces(self) -> List[IdentityAnnounceRecord]:
        """Return all announce metadata records."""

        with self._session_scope() as session:
            return session.query(IdentityAnnounceRecord).all()

    def list_canonical_identity_announces(self) -> List[IdentityAnnounceRecord]:
        """Return announce metadata merged by canonical announced identity."""

        with self._session_scope() as session:
            return list(self._identity_announce_map(session).values())

    def upsert_identity_rem_mode(
        self,
        identity: str,
        *,
        mode: str,
    ) -> IdentityRemModeRecord:
        """Insert or update a persisted REM mode registration."""

        normalized_identity = identity.strip().lower()
        normalized_mode = mode.strip().lower()
        now = _utcnow()
        with self._session_scope() as session:
            insert_values = {
                "identity": normalized_identity,
                "mode": normalized_mode,
                "requested_at": now,
                "updated_at": now,
            }
            stmt = sqlite_insert(IdentityRemModeRecord).values(**insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[IdentityRemModeRecord.identity],
                set_={
                    "mode": normalized_mode,
                    "updated_at": now,
                },
            )
            session.execute(stmt)
            session.commit()
            record = session.get(IdentityRemModeRecord, normalized_identity)
            if record is None:  # pragma: no cover - defensive
                raise RuntimeError("Failed to persist identity REM mode")
            return record

    def get_identity_rem_mode(self, identity: str) -> IdentityRemModeRecord | None:
        """Return the persisted REM mode registration for an identity."""

        with self._session_scope() as session:
            return session.get(IdentityRemModeRecord, identity.strip().lower())

    def list_identity_rem_modes(self) -> List[IdentityRemModeRecord]:
        """Return all persisted REM mode registrations."""

        with self._session_scope() as session:
            return (
                session.query(IdentityRemModeRecord)
                .order_by(IdentityRemModeRecord.identity.asc())
                .all()
            )

    def upsert_identity_capability(
        self,
        identity: str,
        capability: str,
        *,
        granted: bool = True,
        granted_by: str | None = None,
        expires_at=None,
    ) -> IdentityCapabilityGrantRecord:
        """Insert or update a capability grant for an identity."""

        identity = identity.strip().lower()
        capability = capability.strip()
        now = _utcnow()
        with self._session_scope() as session:
            insert_values = {
                "grant_uid": uuid.uuid4().hex,
                "identity": identity,
                "capability": capability,
                "granted": bool(granted),
                "granted_by": granted_by,
                "granted_at": now,
                "expires_at": expires_at,
                "updated_at": now,
            }
            update_values = {
                "granted": bool(granted),
                "granted_by": granted_by,
                "updated_at": now,
                "expires_at": expires_at,
            }
            if granted:
                update_values["granted_at"] = now
            stmt = sqlite_insert(IdentityCapabilityGrantRecord).values(**insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    IdentityCapabilityGrantRecord.identity,
                    IdentityCapabilityGrantRecord.capability,
                ],
                set_=update_values,
            )
            session.execute(stmt)
            session.commit()
            record = (
                session.query(IdentityCapabilityGrantRecord)
                .filter(
                    IdentityCapabilityGrantRecord.identity == identity,
                    IdentityCapabilityGrantRecord.capability == capability,
                )
                .first()
            )
            if record is None:  # pragma: no cover - defensive
                raise RuntimeError("Failed to persist identity capability grant")
            return record

    def list_identity_capabilities(self, identity: str) -> List[str]:
        """Return active capabilities granted to an identity."""

        identity = identity.strip().lower()
        now = _utcnow()
        with self._session_scope() as session:
            rows = (
                session.query(IdentityCapabilityGrantRecord.capability)
                .filter(
                    IdentityCapabilityGrantRecord.identity == identity,
                    IdentityCapabilityGrantRecord.granted.is_(True),
                    or_(
                        IdentityCapabilityGrantRecord.expires_at.is_(None),
                        IdentityCapabilityGrantRecord.expires_at > now,
                    ),
                )
                .all()
            )
            return sorted({row[0] for row in rows})

    def list_identity_capability_grants(
        self, identity: str | None = None
    ) -> List[IdentityCapabilityGrantRecord]:
        """Return persisted capability grants."""

        with self._session_scope() as session:
            query = session.query(IdentityCapabilityGrantRecord)
            if identity:
                query = query.filter(
                    IdentityCapabilityGrantRecord.identity == identity.strip().lower()
                )
            return (
                query.order_by(
                    IdentityCapabilityGrantRecord.identity,
                    IdentityCapabilityGrantRecord.capability,
                )
                .all()
            )

