"""Startup message-store pruning helpers for embedded LXMD."""

from __future__ import annotations

import os
from pathlib import Path
import time

import RNS


class EmbeddedStartupPruneMixin:
    """Manage optional propagation message-store pruning at startup."""

    def _message_store_path(self) -> Path | None:
        storage_path = getattr(self.router, "storagepath", None)
        if storage_path is None:
            return None
        return Path(str(storage_path)) / "messagestore"

    @staticmethod
    def _parse_store_filename(filename: str) -> float | None:
        components = filename.split("_")
        if len(components) < 3:
            return None

        expected_hash_hex_length = (RNS.Identity.HASHLENGTH // 8) * 2
        if len(components[0]) != expected_hash_hex_length:
            return None

        try:
            received = float(components[1])
            if received <= 0:
                return None
            int(components[2])
        except (TypeError, ValueError):
            return None

        return received

    def _remove_startup_files(
        self,
        paths: list[str],
        *,
        reason: str,
    ) -> int:
        removed = 0
        for path in paths:
            try:
                os.unlink(path)
                removed += 1
            except FileNotFoundError:
                continue
            except Exception as exc:  # pragma: no cover - defensive logging
                self._report_propagation_exception(
                    f"Failed to remove {reason} startup message file '{path}': {exc}",
                    exc,
                    metadata={
                        "operation": "startup_prune",
                        "reason": reason,
                        "path": path,
                    },
                    log_level=RNS.LOG_WARNING,
                )
        return removed

    def _prune_message_store_at_startup(self) -> dict[str, int] | None:
        if not self.config.propagation_startup_prune_enabled:
            return None

        message_store = self._message_store_path()
        if message_store is None or not message_store.is_dir():
            return {
                "scanned": 0,
                "kept": 0,
                "removed_invalid": 0,
                "removed_expired": 0,
                "removed_overflow": 0,
            }

        max_messages = self.config.propagation_startup_max_messages
        max_age_days = self.config.propagation_startup_max_age_days
        now = time.time()
        expiry_seconds = max_age_days * 24 * 60 * 60 if max_age_days else None
        cutoff = (now - expiry_seconds) if expiry_seconds else None

        scanned = 0
        valid_entries: list[tuple[float, str]] = []
        invalid_paths: list[str] = []

        with os.scandir(message_store) as iterator:
            for entry in iterator:
                if not entry.is_file():
                    continue
                scanned += 1
                received = self._parse_store_filename(entry.name)
                if received is None:
                    invalid_paths.append(entry.path)
                    continue
                valid_entries.append((received, entry.path))

        removed_invalid = self._remove_startup_files(
            invalid_paths,
            reason="invalid",
        )

        removed_expired = 0
        filtered_entries = valid_entries
        if cutoff is not None:
            expired_paths = [
                path for received, path in filtered_entries if received < cutoff
            ]
            filtered_entries = [
                (received, path)
                for received, path in filtered_entries
                if received >= cutoff
            ]
            removed_expired = self._remove_startup_files(
                expired_paths,
                reason="expired",
            )

        removed_overflow = 0
        if max_messages is not None and len(filtered_entries) > max_messages:
            filtered_entries.sort(key=lambda item: item[0], reverse=True)
            overflow_paths = [path for _, path in filtered_entries[max_messages:]]
            filtered_entries = filtered_entries[:max_messages]
            removed_overflow = self._remove_startup_files(
                overflow_paths,
                reason="overflow",
            )

        return {
            "scanned": scanned,
            "kept": len(filtered_entries),
            "removed_invalid": removed_invalid,
            "removed_expired": removed_expired,
            "removed_overflow": removed_overflow,
        }
