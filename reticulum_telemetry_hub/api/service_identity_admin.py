"""Identity administration and private attachment helpers."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import Optional

from reticulum_telemetry_hub.message_delivery import normalize_topic_id
from .models import FileAttachment
from .models import IdentityStatus


class ApiIdentityAdminMixin:
    """Identity administration and private attachment helpers."""

    def ban_identity(self, identity: str) -> IdentityStatus:
        """Mark an identity as banned."""

        if not identity:
            raise ValueError("identity is required")
        state = self._storage.upsert_identity_state(identity, is_banned=True)
        client = self._storage.get_client(identity)
        announce = self._storage.get_identity_announce(identity.lower())
        display_name = announce.display_name if announce else None
        metadata = dict(client.metadata if client else {})
        if display_name and "display_name" not in metadata:
            metadata["display_name"] = display_name
        last_seen = announce.last_seen if announce else None
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        return self._rem_registry.annotate_identity_status(
            IdentityStatus(
            identity=identity,
            status="banned",
            last_seen=last_seen or (client.last_seen if client else None),
            display_name=display_name,
            metadata=metadata,
            is_banned=state.is_banned,
            is_blackholed=state.is_blackholed,
            client_type=str(announce.client_type or "generic_lxmf").strip().lower()
            if announce is not None
            else "generic_lxmf",
            announce_capabilities=list(announce.announce_capabilities_json or [])
            if announce is not None and isinstance(announce.announce_capabilities_json, list)
            else [],
            )
        )

    def unban_identity(self, identity: str) -> IdentityStatus:
        """Clear ban/blackhole flags for an identity."""

        if not identity:
            raise ValueError("identity is required")
        state = self._storage.upsert_identity_state(
            identity, is_banned=False, is_blackholed=False
        )
        client = self._storage.get_client(identity)
        announce = self._storage.get_identity_announce(identity.lower())
        display_name = announce.display_name if announce else None
        metadata = dict(client.metadata if client else {})
        if display_name and "display_name" not in metadata:
            metadata["display_name"] = display_name
        last_seen = announce.last_seen if announce else None
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        status = "inactive"
        if last_seen and last_seen >= datetime.now(timezone.utc) - timedelta(minutes=60):
            status = "active"
        return self._rem_registry.annotate_identity_status(
            IdentityStatus(
            identity=identity,
            status=status,
            last_seen=last_seen or (client.last_seen if client else None),
            display_name=display_name,
            metadata=metadata,
            is_banned=state.is_banned,
            is_blackholed=state.is_blackholed,
            client_type=str(announce.client_type or "generic_lxmf").strip().lower()
            if announce is not None
            else "generic_lxmf",
            announce_capabilities=list(announce.announce_capabilities_json or [])
            if announce is not None and isinstance(announce.announce_capabilities_json, list)
            else [],
            )
        )

    def blackhole_identity(self, identity: str) -> IdentityStatus:
        """Mark an identity as blackholed."""

        if not identity:
            raise ValueError("identity is required")
        state = self._storage.upsert_identity_state(identity, is_blackholed=True)
        client = self._storage.get_client(identity)
        announce = self._storage.get_identity_announce(identity.lower())
        display_name = announce.display_name if announce else None
        metadata = dict(client.metadata if client else {})
        if display_name and "display_name" not in metadata:
            metadata["display_name"] = display_name
        last_seen = announce.last_seen if announce else None
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        return self._rem_registry.annotate_identity_status(
            IdentityStatus(
            identity=identity,
            status="blackholed",
            last_seen=last_seen or (client.last_seen if client else None),
            display_name=display_name,
            metadata=metadata,
            is_banned=state.is_banned,
            is_blackholed=state.is_blackholed,
            client_type=str(announce.client_type or "generic_lxmf").strip().lower()
            if announce is not None
            else "generic_lxmf",
            announce_capabilities=list(announce.announce_capabilities_json or [])
            if announce is not None and isinstance(announce.announce_capabilities_json, list)
            else [],
            )
        )

    def _store_attachment(  # pylint: disable=too-many-arguments
        self,
        *,
        file_path: str | Path,
        name: Optional[str],
        media_type: str | None,
        topic_id: Optional[str],
        category: str,
        base_path: Path,
    ) -> FileAttachment:
        """Validate inputs and persist file metadata."""

        if category not in {self._file_category, self._image_category}:
            raise ValueError("unsupported category")
        if not file_path:
            raise ValueError("file_path is required")
        path_obj = Path(file_path)
        if not self._filesystem.is_file(path_obj):
            raise ValueError(f"File '{file_path}' does not exist")
        resolved_name = name or path_obj.name
        if not resolved_name:
            raise ValueError("name is required")
        self._filesystem.ensure_directory(base_path)
        resolved_base_path = self._filesystem.resolve(base_path)
        resolved_path = self._filesystem.resolve(path_obj)
        try:
            resolved_path.relative_to(resolved_base_path)
        except ValueError as exc:
            raise ValueError(
                f"File '{file_path}' must be stored within '{resolved_base_path}'"
            ) from exc
        timestamp = datetime.now(timezone.utc)
        attachment = FileAttachment(
            name=resolved_name,
            path=str(resolved_path),
            category=category,
            size=self._filesystem.stat_size(resolved_path),
            media_type=media_type,
            topic_id=topic_id,
            created_at=timestamp,
            updated_at=timestamp,
        )
        return self._storage.create_file_record(attachment)

    def _delete_attachment(
        self,
        record_id: int,
        *,
        expected_category: str,
    ) -> FileAttachment:
        """Delete an attachment record and its on-disk file.

        The persisted attachment record already contains the canonical on-disk
        path. Deletion should therefore use the stored path directly instead of
        re-validating it against the *current* configuration, which can change
        after the record was created or differ from older attachment layouts.
        When the stored path itself cannot be inspected cleanly (for example
        due to legacy malformed values on a different platform), the metadata
        record is still removed so the operator is not blocked by a stale entry.
        """

        record = self._retrieve_attachment(record_id, expected_category=expected_category)
        path_value = record.path
        if isinstance(path_value, str) and path_value:
            stored_path = Path(path_value)
            try:
                if self._filesystem.is_file(stored_path):
                    self._filesystem.delete_file(stored_path)
            except ValueError:
                pass
        deleted = self._storage.delete_file_record(record_id)
        if deleted is None:
            raise KeyError(f"File '{record_id}' not found")
        return deleted

    def _retrieve_attachment(self, record_id: int, *, expected_category: str) -> FileAttachment:
        """Return an attachment by ID, ensuring it matches the category."""

        record = self._storage.get_file_record(record_id)
        if not record or record.category != expected_category:
            raise KeyError(f"File '{record_id}' not found")
        return record

    def _update_attachment_topic(
        self,
        record_id: int,
        *,
        expected_category: str,
        topic_id: Optional[str],
    ) -> FileAttachment:
        """Persist a topic association change for an existing attachment."""

        self._retrieve_attachment(record_id, expected_category=expected_category)
        updated = self._storage.update_file_record_topic(
            record_id,
            topic_id=normalize_topic_id(topic_id),
        )
        if updated is None or updated.category != expected_category:
            raise KeyError(f"File '{record_id}' not found")
        return updated
