"""Client, REM, and rights service methods."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import List

from .models import Client
from .models import RemPeer
from .pagination import PageRequest
from .pagination import PaginatedResult
from .rem_registry_service import DEFAULT_REM_MODE


class ApiClientRightsMixin:
    """Client, REM, and rights service methods."""

    def join(self, identity: str) -> bool:
        """Register a client with the Reticulum Telemetry Hub.

        Args:
            identity (str): Unique Reticulum identity string.

        Returns:
            bool: ``True`` when the identity is recorded or updated.

        Raises:
            ValueError: If ``identity`` is empty.

        Examples:
            >>> api.join("ABCDE")
            True
        """
        if not identity:
            raise ValueError("identity is required")
        self._storage.upsert_client(identity)
        return True

    def leave(self, identity: str) -> bool:
        """Remove a client from the hub.

        Args:
            identity (str): Identity previously joined to the hub.

        Returns:
            bool: ``True`` if the client existed and was removed; ``False``
                otherwise.

        Raises:
            ValueError: If ``identity`` is empty.
        """
        if not identity:
            raise ValueError("identity is required")
        return self._storage.remove_client(identity)

    # ------------------------------------------------------------------ #
    # Client operations
    # ------------------------------------------------------------------ #
    def list_clients(self) -> List[Client]:
        """Return all clients that have joined the hub.

        Returns:
            List[Client]: All persisted client records in insertion order.
        """
        return [
            self._rem_registry.annotate_client(client)
            for client in self._storage.list_clients()
        ]

    def list_clients_paginated(self, page_request: PageRequest) -> PaginatedResult[Client]:
        """Return a page of clients that have joined the hub."""

        return self._storage.paginate_clients(page_request).map_items(
            self._rem_registry.annotate_client
        )

    def count_clients(self) -> int:
        """Return the number of clients that have joined the hub."""

        return self._storage.count_clients()

    def has_client(self, identity: str) -> bool:
        """Return ``True`` when the client is registered with the hub.

        Args:
            identity (str): Identity to look up.

        Returns:
            bool: ``True`` if the identity exists in the client registry.
        """
        if not identity:
            return False
        return self._storage.get_client(identity) is not None

    def record_identity_announce(
        self,
        identity: str,
        *,
        announced_identity_hash: str | None = None,
        display_name: str | None = None,
        source_interface: str | None = None,
        announce_capabilities: object = None,
    ) -> None:
        """Persist announce metadata for a Reticulum identity.

        Args:
            identity (str): Destination hash in hex form.
            display_name (str | None): Optional display name from announce data.
            source_interface (str | None): Optional source interface label.
        """

        if not identity:
            raise ValueError("identity is required")
        identity = identity.lower()
        self._rem_registry.record_identity_announce(
            identity,
            announced_identity_hash=announced_identity_hash,
            display_name=display_name,
            source_interface=source_interface,
            announce_capabilities=announce_capabilities,
        )

    def resolve_identity_display_name(self, identity: str) -> str | None:
        """Return the stored display name for an identity when available."""

        if not identity:
            return None
        record = self._storage.get_identity_announce(identity.lower())
        if record is None:
            return None
        return record.display_name

    def resolve_identity_announce_last_seen(self, identity: str) -> datetime | None:
        """Return the most recent announce timestamp for an identity when available."""

        if not identity:
            return None
        record = self._storage.get_canonical_identity_announce(identity.lower())
        if record is None or record.last_seen is None:
            return None
        if record.last_seen.tzinfo is None:
            return record.last_seen.replace(tzinfo=timezone.utc)
        return record.last_seen.astimezone(timezone.utc)

    def resolve_identity_destination_hash(self, identity: str) -> str | None:
        """Return the best-known LXMF delivery destination hash for an identity."""

        if not identity:
            return None
        return self._storage.resolve_identity_destination_hash(identity.lower())

    def resolve_identity_display_names_bulk(
        self,
        identities: list[str],
    ) -> dict[str, str | None]:
        """Return display names for a batch of identity hashes."""

        if not identities:
            return {}
        return self._storage.resolve_identity_display_names_bulk(identities)

    def list_identity_capabilities(self, identity: str) -> List[str]:
        """Return active capabilities for an identity."""

        if not identity:
            return []
        return self._rights.resolve_effective_operations(identity, mission_uid=None)

    def list_identity_announce_capabilities(self, identity: str) -> List[str]:
        """Return normalized announce capabilities for an identity."""

        if not identity:
            return []
        record = self._storage.get_identity_announce(identity.lower())
        if record is None or not isinstance(record.announce_capabilities_json, list):
            return []
        return [
            str(item).strip().lower()
            for item in record.announce_capabilities_json
            if str(item).strip()
        ]

    def get_rem_mode(self, identity: str) -> str:
        """Return the persisted or default REM mode for an identity."""

        if not identity:
            return DEFAULT_REM_MODE
        return self._rem_registry.get_rem_mode(identity)

    def set_rem_mode(self, identity: str, mode: str) -> dict[str, object]:
        """Persist and return a REM mode registration result."""

        return self._rem_registry.set_rem_mode(identity, mode=mode)

    def list_rem_peers(self) -> list[RemPeer]:
        """Return active REM-capable peers."""

        return self._rem_registry.list_active_rem_peers()

    def rem_peer_registry(self) -> dict[str, object]:
        """Return the canonical REM peer registry payload."""

        return self._rem_registry.build_peer_list_payload()

    def effective_rem_connected_mode(self) -> bool:
        """Return True when connected REM mode is currently enabled."""

        return self._rem_registry.effective_connected_mode()

    def rem_fanout_recipients(
        self,
        joined_identities: list[str],
    ) -> dict[str, list[str]]:
        """Return mode-aware REM/generic fanout recipient buckets."""

        return self._rem_registry.fanout_recipients(joined_identities)

    def list_capability_grants(self, identity: str | None = None) -> List[dict]:
        """Return persisted capability grant entries."""

        if identity:
            records = self._rights.list_operation_rights(
                subject_type="identity",
                subject_id=identity,
                scope_type="global",
                scope_id="",
            )
        else:
            records = self._rights.list_operation_rights(
                subject_type="identity",
                scope_type="global",
                scope_id="",
            )
        return [
            {
                "grant_uid": record["grant_uid"],
                "identity": record["subject_id"],
                "capability": record["operation"],
                "granted": bool(record["granted"]),
                "granted_by": record["granted_by"],
                "granted_at": record["granted_at"],
                "expires_at": record["expires_at"],
                "updated_at": record["updated_at"],
            }
            for record in records
        ]

    def grant_identity_capability(
        self,
        identity: str,
        capability: str,
        *,
        granted_by: str | None = None,
        expires_at: datetime | None = None,
    ) -> dict:
        """Grant a capability to an identity."""

        if not identity:
            raise ValueError("identity is required")
        if not capability:
            raise ValueError("capability is required")
        record = self._rights.grant_operation_right(
            "identity",
            identity,
            capability,
            scope_type="global",
            scope_id="",
            granted_by=granted_by,
            expires_at=expires_at,
        )
        return {
            "grant_uid": record["grant_uid"],
            "identity": record["subject_id"],
            "capability": record["operation"],
            "granted": bool(record["granted"]),
        }

    def revoke_identity_capability(
        self,
        identity: str,
        capability: str,
        *,
        granted_by: str | None = None,
    ) -> dict:
        """Revoke a capability from an identity."""

        if not identity:
            raise ValueError("identity is required")
        if not capability:
            raise ValueError("capability is required")
        record = self._rights.revoke_operation_right(
            "identity",
            identity,
            capability,
            scope_type="global",
            scope_id="",
            granted_by=granted_by,
        )
        return {
            "grant_uid": record["grant_uid"],
            "identity": record["subject_id"],
            "capability": record["operation"],
            "granted": bool(record["granted"]),
        }

    def grant_operation_right(
        self,
        subject_type: str,
        subject_id: str,
        operation: str,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
        granted_by: str | None = None,
        expires_at: datetime | None = None,
    ) -> dict:
        """Grant an operation right to an identity or team member."""

        return self._rights.grant_operation_right(
            subject_type,
            subject_id,
            operation,
            scope_type=scope_type,
            scope_id=scope_id,
            granted_by=granted_by,
            expires_at=expires_at,
        )

    def revoke_operation_right(
        self,
        subject_type: str,
        subject_id: str,
        operation: str,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
        granted_by: str | None = None,
    ) -> dict:
        """Revoke an operation right from an identity or team member."""

        return self._rights.revoke_operation_right(
            subject_type,
            subject_id,
            operation,
            scope_type=scope_type,
            scope_id=scope_id,
            granted_by=granted_by,
        )

    def list_operation_rights(
        self,
        *,
        subject_type: str | None = None,
        subject_id: str | None = None,
        operation: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> List[dict]:
        """Return persisted subject-aware operation rights."""

        return self._rights.list_operation_rights(
            subject_type=subject_type,
            subject_id=subject_id,
            operation=operation,
            scope_type=scope_type,
            scope_id=scope_id,
        )

    def assign_mission_access_role(
        self,
        mission_uid: str,
        subject_type: str,
        subject_id: str,
        *,
        role: str | None = None,
        assigned_by: str | None = None,
    ) -> dict:
        """Assign a standard mission access role."""

        return self._rights.assign_mission_access_role(
            mission_uid,
            subject_type,
            subject_id,
            role=role,
            assigned_by=assigned_by,
        )

    def revoke_mission_access_role(
        self,
        mission_uid: str,
        subject_type: str,
        subject_id: str,
    ) -> dict:
        """Remove a mission access role assignment."""

        return self._rights.revoke_mission_access_role(
            mission_uid,
            subject_type,
            subject_id,
        )

    def list_mission_access_assignments(
        self,
        *,
        mission_uid: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> List[dict]:
        """Return mission access role assignments."""

        return self._rights.list_mission_access_assignments(
            mission_uid=mission_uid,
            subject_type=subject_type,
            subject_id=subject_id,
        )

    def list_team_member_subjects(
        self,
        *,
        mission_uid: str | None = None,
    ) -> List[dict]:
        """Return team members as assignable rights subjects."""

        return self._rights.list_team_member_subjects(mission_uid=mission_uid)

    def resolve_effective_operations(
        self,
        identity: str,
        mission_uid: str | None = None,
    ) -> List[str]:
        """Resolve effective operations for an identity."""

        return self._rights.resolve_effective_operations(identity, mission_uid=mission_uid)

    def authorize(
        self,
        identity: str,
        operation: str,
        mission_uid: str | None = None,
    ) -> bool:
        """Return whether an identity is authorized for an operation."""

        return self._rights.authorize(identity, operation, mission_uid=mission_uid)

    # ------------------------------------------------------------------ #
    # File operations
    # ------------------------------------------------------------------ #
