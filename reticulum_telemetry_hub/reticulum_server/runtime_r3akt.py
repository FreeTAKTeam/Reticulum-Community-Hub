"""R3AKT capability and identity helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

import time
import sys
from typing import Any

import LXMF
import RNS

from reticulum_telemetry_hub.api.rem_registry_service import REM_CLIENT_TYPE
from reticulum_telemetry_hub.api.rem_registry_service import RemRegistryService
from reticulum_telemetry_hub.message_delivery import normalize_hash
import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeR3aktMixin:
    """R3AKT capability and identity helpers."""

    @staticmethod
    def _build_r3akt_custom_fields(
        *,
        mission_uid: str,
        event_envelope: dict[str, object],
    ) -> dict[int | str, object]:
        event_type = str(event_envelope.get("event_type") or "").strip()
        return {
            R3AKT_CUSTOM_TYPE_FIELD: R3AKT_CUSTOM_TYPE_IDENTIFIER,
            R3AKT_CUSTOM_DATA_FIELD: {
                "mission_uid": mission_uid,
                "event": event_envelope,
            },
            R3AKT_CUSTOM_META_FIELD: {
                "version": R3AKT_CUSTOM_META_VERSION,
                "event_type": event_type,
                "mission_uid": mission_uid,
                "encoding": "json",
                "source": "rch",
            },
        }

    def _augment_r3akt_custom_fields(
        self,
        fields: dict[int | str, object],
    ) -> dict[int | str, object]:
        merged = dict(fields or {})
        mission_uid = self._extract_mission_uid_from_response_fields(merged)
        event_field = merged.get(LXMF.FIELD_EVENT)
        if not mission_uid or not isinstance(event_field, dict):
            return merged
        merged.update(
            self._build_r3akt_custom_fields(
                mission_uid=mission_uid,
                event_envelope=event_field,
            )
        )
        return merged

    def _update_identity_capability_cache(
        self, identity: str, capabilities: set[str]
    ) -> None:
        normalized_identity = str(identity or "").strip().lower()
        if not normalized_identity:
            return
        normalized_caps = {
            str(value or "").strip().lower() for value in capabilities if value
        }
        if not normalized_caps:
            return
        expires_at = time.time() + IDENTITY_CAPABILITY_CACHE_TTL_SECONDS
        self._identity_capability_cache[normalized_identity] = (
            normalized_caps,
            expires_at,
        )

    def _identity_capabilities(self, identity: str) -> set[str]:
        normalized_identity = str(identity or "").strip().lower()
        if not normalized_identity:
            return set()

        cached = self._identity_capability_cache.get(normalized_identity)
        now = time.time()
        if cached is not None:
            values, expires_at = cached
            if now < float(expires_at):
                return set(values)

        api = getattr(self, "api", None)
        if api is None:
            return set()
        try:
            announced = api.list_identity_announce_capabilities(normalized_identity)
        except Exception:
            announced = []
        if announced:
            normalized = {
                str(value or "").strip().lower() for value in announced if value
            }
            self._identity_capability_cache[normalized_identity] = (
                normalized,
                now + IDENTITY_CAPABILITY_CACHE_TTL_SECONDS,
            )
            return normalized
        try:
            grants = api.list_identity_capabilities(normalized_identity)
        except Exception:
            return set()
        normalized = {
            str(value or "").strip().lower() for value in grants if value
        }
        self._identity_capability_cache[normalized_identity] = (
            normalized,
            now + IDENTITY_CAPABILITY_CACHE_TTL_SECONDS,
        )
        return normalized

    def _identity_supports_r3akt(self, identity: str) -> bool:
        capabilities = self._identity_capabilities(identity)
        return "r3akt" in capabilities

    def _identity_client_type(self, identity: str) -> str:
        """Return the normalized client type for a peer identity."""

        return RemRegistryService.classify_client_type(self._identity_capabilities(identity))

    def _identity_is_rem(self, identity: str) -> bool:
        """Return True when an identity announces REM capabilities."""

        return self._identity_client_type(identity) == REM_CLIENT_TYPE

    def _connected_identities(self) -> list[str]:
        """Return normalized identity hashes for current LXMF connections."""

        available = (
            list(self.connections.values())
            if hasattr(self.connections, "values")
            else list(self.connections)
        )
        results: list[str] = []
        for connection in available:
            connection_hex = self._connection_hex(connection)
            if connection_hex:
                results.append(connection_hex)
        return results

    def _rem_fanout_recipients(self) -> dict[str, list[str]]:
        """Return connected-mode REM and generic recipient buckets."""

        api = getattr(self, "api", None)
        if api is None:
            return {"rem": [], "generic": []}
        return api.rem_fanout_recipients(self._connected_identities())

    def _ensure_reachable_identity_destination(self, identity: str) -> None:
        """Recall and cache an LXMF destination for an identity when possible."""

        normalized_identity = normalize_hash(identity)
        if not normalized_identity:
            return
        for connection in (
            list(self.connections.values())
            if hasattr(self.connections, "values")
            else list(self.connections)
        ):
            if self._connection_hex(connection) == normalized_identity:
                self._cache_destination(connection)
                return
        recall_candidates = [normalized_identity]
        api = getattr(self, "api", None)
        if api is not None and hasattr(api, "resolve_identity_destination_hash"):
            try:
                destination_hash = api.resolve_identity_destination_hash(normalized_identity)
            except Exception:
                destination_hash = None
            normalized_destination_hash = normalize_hash(destination_hash)
            if normalized_destination_hash and normalized_destination_hash not in recall_candidates:
                recall_candidates.insert(0, normalized_destination_hash)
        destination = None
        resolved_recall_hash = None
        main_module = sys.modules.get("reticulum_telemetry_hub.reticulum_server.__main__")
        rns = getattr(main_module, "RNS", RNS)
        for recall_hash in recall_candidates:
            try:
                recalled = rns.Identity.recall(bytes.fromhex(recall_hash))
                if recalled is None:
                    continue
                destination = rns.Destination(
                    recalled,
                    rns.Destination.OUT,
                    rns.Destination.SINGLE,
                    "lxmf",
                    "delivery",
                )
                resolved_recall_hash = recall_hash
                break
            except Exception:
                continue
        if destination is None:
            return
        setattr(destination, "_rch_cold_cache", True)
        if resolved_recall_hash and resolved_recall_hash != normalized_identity:
            try:
                setattr(destination, "_rch_delivery_destination_hash", bytes.fromhex(resolved_recall_hash))
            except ValueError:
                pass
        self.connections[destination.identity.hash] = destination
        self._cache_destination(destination)

    def _prune_mission_change_fanout_cache(self) -> None:
        now = time.time()
        stale = [
            uid
            for uid, expires_at in self._mission_change_fanout_cache.items()
            if now >= float(expires_at)
        ]
        for uid in stale:
            self._mission_change_fanout_cache.pop(uid, None)

    def _mark_mission_change_fanned_out(self, mission_change_uid: str) -> None:
        uid = str(mission_change_uid or "").strip()
        if not uid:
            return
        self._prune_mission_change_fanout_cache()
        self._mission_change_fanout_cache[uid] = time.time() + 24 * 60 * 60

    def _has_mission_change_been_fanned_out(self, mission_change_uid: str) -> bool:
        uid = str(mission_change_uid or "").strip()
        if not uid:
            return False
        self._prune_mission_change_fanout_cache()
        expires_at = self._mission_change_fanout_cache.get(uid)
        if expires_at is None:
            return False
        return time.time() < float(expires_at)

    @staticmethod
    def _build_mission_change_event_field(
        *,
        mission_uid: str,
        mission_change_uid: str,
        change_type: str | None,
    ) -> dict[str, object]:
        return {
            "event_type": "mission.registry.mission_change.upserted",
            "payload": {
                "mission_uid": mission_uid,
                "mission_change_uid": mission_change_uid,
                "change_type": change_type,
            },
        }

    @staticmethod
    def _build_r3akt_delta_custom_fields(
        *,
        mission_uid: str,
        mission_change: dict[str, Any],
        delta: dict[str, Any],
    ) -> dict[int | str, object]:
        return {
            R3AKT_CUSTOM_TYPE_FIELD: R3AKT_CUSTOM_TYPE_IDENTIFIER,
            R3AKT_CUSTOM_DATA_FIELD: {
                "mission_uid": mission_uid,
                "mission_change": mission_change,
                "delta": delta,
            },
            R3AKT_CUSTOM_META_FIELD: {
                "version": R3AKT_CUSTOM_META_VERSION,
                "event_type": "mission.registry.mission_change.upserted",
                "mission_uid": mission_uid,
                "encoding": "json",
                "source": "rch",
            },
        }

