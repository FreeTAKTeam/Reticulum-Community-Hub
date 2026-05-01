"""Configuration coercion, metadata, and backup helpers."""

from __future__ import annotations

import string
from configparser import ConfigParser
from datetime import datetime
from datetime import timezone
from pathlib import Path

from reticulum_telemetry_hub.config.models import HubAppConfig
from reticulum_telemetry_hub.config.models import TakConnectionConfig

_WS_STATUS_FANOUT_MODES = {"event_only", "periodic", "event_plus_periodic"}


class ConfigCoercionMixin:
    """Coerce scalar config values and manage metadata/backups."""

    @staticmethod
    def _coerce_int(value: str | None, default: int) -> int:
        """Return an integer from a string value or fallback."""

        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def _coerce_optional_positive_int(value: str | None) -> int | None:
        """Return a positive integer or ``None`` when unset/invalid."""

        if value is None:
            return None
        compact = str(value).strip()
        if not compact:
            return None
        try:
            parsed = int(compact)
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _coerce_optional_int_min(value: str | None, *, minimum: int = 0) -> int | None:
        """Return an integer constrained to a minimum, or ``None`` when unset."""

        if value is None:
            return None
        compact = str(value).strip()
        if not compact:
            return None
        try:
            parsed = int(compact)
        except ValueError:
            return None
        return parsed if parsed >= minimum else minimum

    @staticmethod
    def _coerce_min_float(
        value: str | None,
        *,
        default: float,
        minimum: float,
    ) -> float:
        """Return a float clamped to ``minimum`` with a fallback default."""

        if value is None:
            return default
        compact = str(value).strip()
        if not compact:
            return default
        try:
            parsed = float(compact)
        except ValueError:
            return default
        return parsed if parsed >= minimum else minimum

    @staticmethod
    def _coerce_csv_list(value: str | None) -> tuple[str, ...]:
        """Return a tuple of non-empty comma-delimited values."""

        if value is None:
            return ()
        return tuple(
            part.strip().lower()
            for part in str(value).split(",")
            if part.strip()
        )

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        """Return a stripped string or ``None`` when the value is blank."""

        if value is None:
            return None
        compact = str(value).strip()
        return compact or None

    @staticmethod
    def _normalize_display_name(value: str | None) -> str | None:
        """Return a trimmed display name or ``None`` when empty."""

        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _normalize_name_token(value: str | None, fallback: str = "unknown") -> str:
        """Return a sanitized token suitable for generated names."""

        if value is None:
            return fallback
        compact = str(value).strip()
        if not compact:
            return fallback
        normalized = "".join(
            ch if ch.isalnum() or ch in {".", "-", "_"} else "_" for ch in compact
        )
        normalized = normalized.strip("._-")
        return normalized or fallback

    @staticmethod
    def _normalize_destination_hash(
        value: bytes | bytearray | memoryview | str | None,
    ) -> str:
        """Return a lowercase destination-hash token for generated names."""

        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value).hex().lower()

        if isinstance(value, str):
            candidate = value.strip().lower()
            if candidate.startswith("0x"):
                candidate = candidate[2:]
            if candidate and all(ch in string.hexdigits for ch in candidate):
                return candidate

        return "unknown"

    @staticmethod
    def _coerce_float(value: str | None, default: float) -> float:
        """Return a float from a string value or fallback."""

        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    @staticmethod
    def _normalize_status_fanout_mode(value: str | None, *, default: str) -> str:
        """Return a supported status fan-out mode."""

        if value is None:
            return default
        normalized = str(value).strip().lower()
        if normalized in _WS_STATUS_FANOUT_MODES:
            return normalized
        return default

    @staticmethod
    def _normalize_propagation_start_mode(value: str | None) -> str:
        """Return a supported propagation startup mode."""

        mode = (value or "background").strip().lower()
        return mode if mode in {"blocking", "background"} else "background"

    @staticmethod
    def _get_bool(section, key: str, default: bool) -> bool:
        """Interpret boolean-like strings from a config section."""
        value = section.get(key)
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _find_interface_section(parser: ConfigParser) -> dict:
        """Find the first TCP interface section in a configuration parser."""
        candidate_sections = [
            name
            for name in parser.sections()
            if name.lower().startswith("interfaces") or "tcp" in name.lower()
        ]
        if candidate_sections:
            return parser[candidate_sections[0]]
        return {}

    @staticmethod
    def _ensure_directory(path: Path) -> Path:
        """
        Guarantee that a directory exists.

        Args:
            path (Path): Directory to create when missing.

        Returns:
            Path: The original path for chaining.
        """

        path.mkdir(parents=True, exist_ok=True)
        return path

    def _load_app_metadata(self) -> tuple[str, str | None, str]:
        """Return human-readable application metadata from ``config.ini``.

        Returns:
            tuple[str, str | None, str]: Name, version, and description for the
            application, preferring the ``[app]`` section when present.
        """

        section = self._get_section("app")
        default_name = "ReticulumTelemetryHub"
        default_version = HubAppConfig._safe_get_version(default_name)  # pylint: disable=protected-access
        name = section.get("name") or section.get("app_name") or default_name
        version = (
            section.get("version")
            or section.get("app_version")
            or section.get("build")
            or default_version
        )
        description = (
            section.get("description")
            or section.get("app_description")
            or section.get("summary")
            or ""
        )
        return name, version, description

    def _load_tak_config(self) -> TakConnectionConfig:
        """Construct the TAK configuration using ``config.ini`` values."""

        defaults = TakConnectionConfig()
        # Prefer the new uppercase [TAK] section; fall back to legacy [tak].
        section = self._get_section("TAK") or self._get_section("tak")

        interval = self._coerce_float(
            section.get("poll_interval_seconds")
            or section.get("interval_seconds")
            or section.get("interval"),
            defaults.poll_interval_seconds,
        )

        keepalive_interval = self._coerce_float(
            section.get("keepalive_interval_seconds")
            or section.get("keepalive_interval")
            or section.get("keepalive"),
            defaults.keepalive_interval_seconds,
        )

        tak_proto = self._coerce_int(section.get("tak_proto"), defaults.tak_proto)
        fts_compat = self._coerce_int(section.get("fts_compat"), defaults.fts_compat)

        return TakConnectionConfig(
            cot_url=section.get("cot_url", defaults.cot_url),
            callsign=section.get("callsign", defaults.callsign),
            poll_interval_seconds=interval,
            keepalive_interval_seconds=keepalive_interval,
            tls_client_cert=section.get("tls_client_cert"),
            tls_client_key=section.get("tls_client_key"),
            tls_ca=section.get("tls_ca"),
            tls_client_password=section.get("tls_client_password"),
            tls_insecure=self._get_bool(section, "tls_insecure", defaults.tls_insecure),
            tak_proto=tak_proto,
            fts_compat=fts_compat,
        )

    def _backup_config(self) -> Path | None:
        """Create a timestamped backup of config.ini when it exists."""

        if not self.config_path.exists():
            return None
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_path = self.config_path.with_suffix(f".ini.bak.{timestamp}")
        content = self.config_path.read_text(encoding="utf-8")
        backup_path.write_text(content, encoding="utf-8")
        return backup_path

    def _latest_backup(self) -> Path | None:
        """Return the most recent config.ini backup file."""

        backups = sorted(self.config_path.parent.glob("config.ini.bak.*"))
        if not backups:
            return None
        return backups[-1]

    def _backup_reticulum_config(self) -> Path | None:
        """Create a timestamped backup of the Reticulum config when it exists."""

        if not self.reticulum_config_path.exists():
            return None
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_path = Path(f"{self.reticulum_config_path}.bak.{timestamp}")
        content = self.reticulum_config_path.read_text(encoding="utf-8")
        backup_path.write_text(content, encoding="utf-8")
        return backup_path

    def _latest_reticulum_backup(self) -> Path | None:
        """Return the most recent Reticulum config backup file."""

        backups = sorted(
            self.reticulum_config_path.parent.glob(
                f"{self.reticulum_config_path.name}.bak.*"
            )
        )
        if not backups:
            return None
        return backups[-1]
