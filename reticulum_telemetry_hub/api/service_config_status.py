"""Config, app info, and identity status service methods."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import List

from .models import Client
from .models import IdentityStatus
from .models import ReticulumInfo
from .storage_models import IdentityAnnounceRecord


class ApiConfigStatusMixin:
    """Config, app info, and identity status service methods."""

    def get_app_info(self) -> ReticulumInfo:
        """Return the current Reticulum configuration snapshot.

        Returns:
            ReticulumInfo: Configuration values sourced from the configuration
            manager, including the app name, version, and description.
        """
        info_dict = self._config_manager.reticulum_info_snapshot()
        return self._build_reticulum_info(info_dict)

    def get_config_text(self) -> str:
        """Return the raw hub configuration file content."""

        return self._config_manager.get_config_text()

    def get_reticulum_config_text(self) -> str:
        """Return the raw Reticulum configuration file content."""

        return self._config_manager.get_reticulum_config_text()

    def validate_config_text(self, config_text: str) -> dict:
        """Validate the provided configuration payload."""

        return self._config_manager.validate_config_text(config_text)

    def validate_reticulum_config_text(self, config_text: str) -> dict:
        """Validate the provided Reticulum configuration payload."""

        return self._config_manager.validate_reticulum_config_text(config_text)

    def apply_config_text(self, config_text: str) -> dict:
        """Persist a new configuration payload and reload."""

        result = self._config_manager.apply_config_text(config_text)
        config = self._config_manager.reload()
        self._notify_config_reload(config)
        return result

    def apply_reticulum_config_text(self, config_text: str) -> dict:
        """Persist a new Reticulum configuration payload and reload."""

        result = self._config_manager.apply_reticulum_config_text(config_text)
        config = self._config_manager.reload()
        self._notify_config_reload(config)
        return result

    def rollback_config_text(self, backup_path: str | None = None) -> dict:
        """Rollback configuration from the latest backup."""

        result = self._config_manager.rollback_config_text(backup_path=backup_path)
        config = self._config_manager.reload()
        self._notify_config_reload(config)
        return result

    def rollback_reticulum_config_text(self, backup_path: str | None = None) -> dict:
        """Rollback Reticulum configuration from the latest backup."""

        result = self._config_manager.rollback_reticulum_config_text(
            backup_path=backup_path
        )
        config = self._config_manager.reload()
        self._notify_config_reload(config)
        return result

    def reload_config(self) -> ReticulumInfo:
        """Reload the configuration from disk."""

        config = self._config_manager.reload()
        self._notify_config_reload(config)
        return self._build_reticulum_info(config.to_reticulum_info_dict())

    def list_identity_statuses(self) -> List[IdentityStatus]:
        """Return identity statuses merged with client data."""

        clients: dict[str, Client] = {}
        for client in self._storage.list_clients():
            if not client.identity:
                continue
            identity_key = client.identity.strip().lower()
            if not identity_key:
                continue
            existing = clients.get(identity_key)
            if existing is None or client.last_seen > existing.last_seen:
                clients[identity_key] = client

        states: dict[str, dict[str, object]] = {}
        for state in self._storage.list_identity_states():
            identity_value = getattr(state, "identity", None)
            if not identity_value:
                continue
            identity_key = identity_value.strip().lower()
            if not identity_key:
                continue
            entry = states.get(identity_key)
            if entry is None:
                states[identity_key] = {
                    "identity": identity_value,
                    "is_banned": bool(state.is_banned),
                    "is_blackholed": bool(state.is_blackholed),
                    "updated_at": state.updated_at,
                }
                continue
            entry["is_banned"] = bool(entry["is_banned"]) or bool(state.is_banned)
            entry["is_blackholed"] = bool(entry["is_blackholed"]) or bool(
                state.is_blackholed
            )
            updated_at = state.updated_at
            existing_updated_at = entry.get("updated_at")
            if updated_at is None:
                continue
            if existing_updated_at is None or updated_at >= existing_updated_at:
                entry["identity"] = identity_value
                entry["updated_at"] = updated_at

        announces: dict[str, IdentityAnnounceRecord] = {}
        announce_sources: dict[str, str | None] = {}
        for record in self._storage.list_canonical_identity_announces():
            identity_key = str(
                record.announced_identity_hash or record.destination_hash or ""
            ).strip().lower()
            if not identity_key:
                continue
            source = str(record.source_interface or "").strip().lower() or None
            announces[identity_key] = record
            announce_sources[identity_key] = source
        identities = sorted(
            set(clients.keys()) | set(states.keys()) | set(announces.keys())
        )
        statuses: List[IdentityStatus] = []
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
        for identity_key in identities:
            client = clients.get(identity_key)
            state_entry = states.get(identity_key)
            announce = announces.get(identity_key)
            display_name = announce.display_name if announce else None
            metadata = dict(client.metadata if client else {})
            if display_name and "display_name" not in metadata:
                metadata["display_name"] = display_name
            is_banned = bool(state_entry.get("is_banned")) if state_entry else False
            is_blackholed = (
                bool(state_entry.get("is_blackholed")) if state_entry else False
            )
            announce_last_seen = None
            if announce and announce.last_seen:
                announce_last_seen = announce.last_seen
                if announce_last_seen.tzinfo is None:
                    announce_last_seen = announce_last_seen.replace(tzinfo=timezone.utc)
            last_seen = announce_last_seen or (client.last_seen if client else None)
            status = "inactive"
            if announce_last_seen and announce_last_seen >= cutoff:
                status = "active"
            if is_blackholed:
                status = "blackholed"
            elif is_banned:
                status = "banned"
            identity_value = identity_key
            if client and client.identity:
                identity_value = client.identity
            elif state_entry and state_entry.get("identity"):
                identity_value = str(state_entry.get("identity"))
            elif announce and announce.destination_hash:
                identity_value = announce.destination_hash
            statuses.append(
                self._rem_registry.annotate_identity_status(
                    IdentityStatus(
                    identity=identity_value,
                    status=status,
                    last_seen=last_seen,
                    display_name=display_name,
                    metadata=metadata,
                    is_banned=is_banned,
                    is_blackholed=is_blackholed,
                    client_type=str(announce.client_type or "generic_lxmf").strip().lower()
                    if announce is not None
                    else "generic_lxmf",
                    announce_capabilities=list(announce.announce_capabilities_json or [])
                    if announce is not None and isinstance(announce.announce_capabilities_json, list)
                    else [],
                    )
                )
            )
        return self._dedupe_identity_statuses(
            statuses,
            announce_sources=announce_sources,
            client_keys=set(clients.keys()),
            state_keys=set(states.keys()),
        )

    def _dedupe_identity_statuses(
        self,
        statuses: List[IdentityStatus],
        *,
        announce_sources: dict[str, str | None],
        client_keys: set[str],
        state_keys: set[str],
    ) -> List[IdentityStatus]:
        """Collapse duplicate identity statuses with matching display metadata.

        Args:
            statuses (List[IdentityStatus]): Raw identity status entries.
            announce_sources (dict[str, str | None]): Announce source tags keyed by
                identity hash.
            client_keys (set[str]): Identities currently joined to the hub.
            state_keys (set[str]): Identities with moderation state records.

        Returns:
            List[IdentityStatus]: Deduplicated status list for UI consumption.
        """

        results: List[IdentityStatus] = []
        index_by_key: dict[tuple[object, ...], int] = {}
        for status in statuses:
            display_name = (status.display_name or "").strip()
            if not display_name:
                results.append(status)
                continue
            key = (
                display_name.lower(),
                status.status,
                self._identity_status_bucket(status.last_seen),
                bool(status.is_banned),
                bool(status.is_blackholed),
            )
            existing_index = index_by_key.get(key)
            if existing_index is None:
                index_by_key[key] = len(results)
                results.append(status)
                continue
            existing = results[existing_index]
            if self._identity_status_preferred(
                status,
                existing,
                announce_sources=announce_sources,
                client_keys=client_keys,
                state_keys=state_keys,
            ):
                results[existing_index] = status
        return results

    @staticmethod
    def _identity_status_bucket(last_seen: datetime | None) -> int | None:
        """Return a bucketed timestamp for deduping announce entries.

        Args:
            last_seen (datetime | None): Timestamp to bucket.

        Returns:
            int | None: A 5-second bucket epoch timestamp or ``None`` when missing.
        """

        if not last_seen:
            return None
        timestamp = int(last_seen.timestamp())
        return timestamp - (timestamp % 5)

    @staticmethod
    def _identity_status_rank(
        identity_key: str,
        *,
        announce_sources: dict[str, str | None],
        client_keys: set[str],
        state_keys: set[str],
    ) -> int:
        """Return a preference rank for selecting a canonical identity entry.

        Args:
            identity_key (str): Normalized identity hash.
            announce_sources (dict[str, str | None]): Announce source tags keyed by
                identity hash.
            client_keys (set[str]): Joined identities.
            state_keys (set[str]): Moderated identities.

        Returns:
            int: Preference rank where higher values are preferred.
        """

        if identity_key in client_keys or identity_key in state_keys:
            return 3
        source = announce_sources.get(identity_key)
        if source == "identity":
            return 2
        if source == "destination":
            return 1
        return 0

    @classmethod
    def _identity_status_preferred(
        cls,
        candidate: IdentityStatus,
        current: IdentityStatus,
        *,
        announce_sources: dict[str, str | None],
        client_keys: set[str],
        state_keys: set[str],
    ) -> bool:
        """Return True when the candidate status should replace the current one.

        Args:
            candidate (IdentityStatus): Proposed replacement entry.
            current (IdentityStatus): Existing entry in the deduped list.
            announce_sources (dict[str, str | None]): Announce source tags keyed by
                identity hash.
            client_keys (set[str]): Joined identities.
            state_keys (set[str]): Moderated identities.

        Returns:
            bool: ``True`` if the candidate should replace the current entry.
        """

        candidate_key = (candidate.identity or "").strip().lower()
        current_key = (current.identity or "").strip().lower()
        candidate_rank = cls._identity_status_rank(
            candidate_key,
            announce_sources=announce_sources,
            client_keys=client_keys,
            state_keys=state_keys,
        )
        current_rank = cls._identity_status_rank(
            current_key,
            announce_sources=announce_sources,
            client_keys=client_keys,
            state_keys=state_keys,
        )
        if candidate_rank != current_rank:
            return candidate_rank > current_rank
        if candidate_key and current_key and candidate_key != current_key:
            return candidate_key < current_key
        return False

