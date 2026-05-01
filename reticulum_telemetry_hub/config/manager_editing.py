"""Configuration text editing and rollback helpers."""

from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path


class ConfigEditingMixin:
    """Validate, apply, and roll back editable config text."""

    def get_config_text(self) -> str:
        """Return the raw config.ini content when present."""

        if not self.config_path.exists():
            return ""
        return self.config_path.read_text(encoding="utf-8")

    def get_reticulum_config_text(self) -> str:
        """Return the raw Reticulum configuration content when present."""

        if not self.reticulum_config_path.exists():
            return ""
        return self.reticulum_config_path.read_text(encoding="utf-8")

    def _reload_external_config_paths(self) -> None:
        """Refresh Reticulum and LXMF config file paths from overrides/defaults."""

        reticulum_path_override = self.runtime_config.reticulum_config_path
        lxmf_path_override = self.runtime_config.lxmf_router_config_path

        self.reticulum_config_path = (
            self._reticulum_config_override
            or reticulum_path_override
            or Path.home() / ".reticulum" / "config"
        )
        self.lxmf_router_config_path = (
            self._lxmf_router_config_override
            or lxmf_path_override
            or self.storage_path / "lxmf-router.ini"
        )

    def validate_config_text(self, config_text: str) -> dict:
        """Validate a config.ini payload without applying it.

        Args:
            config_text (str): Raw ini contents to validate.

        Returns:
            dict: Validation result with ``valid`` and ``errors`` keys.
        """

        parser = ConfigParser()
        errors: list[str] = []
        try:
            parser.read_string(config_text)
        except Exception as exc:  # pragma: no cover - defensive parsing
            errors.append(str(exc))
        return {"valid": not errors, "errors": errors}

    def validate_reticulum_config_text(self, config_text: str) -> dict:
        """Validate a Reticulum configuration payload without applying it.

        Args:
            config_text (str): Raw ini contents to validate.

        Returns:
            dict: Validation result with ``valid`` and ``errors`` keys.
        """

        parser = ConfigParser()
        errors: list[str] = []
        try:
            parser.read_string(config_text)
        except Exception as exc:  # pragma: no cover - defensive parsing
            errors.append(str(exc))
        return {"valid": not errors, "errors": errors}

    def apply_config_text(self, config_text: str) -> dict:
        """Persist the provided config.ini content and keep a backup.

        Args:
            config_text (str): Raw ini content to persist.

        Returns:
            dict: Details about the persisted backup and target path.
        """

        validation = self.validate_config_text(config_text)
        if not validation.get("valid"):
            errors = validation.get("errors") or []
            details = "; ".join(str(error) for error in errors if error)
            message = "Invalid configuration payload"
            if details:
                message = f"{message}: {details}"
            raise ValueError(message)
        backup_path = self._backup_config()
        self.config_path.write_text(config_text, encoding="utf-8")
        return {
            "applied": True,
            "config_path": str(self.config_path),
            "backup_path": str(backup_path) if backup_path else None,
        }

    def apply_reticulum_config_text(self, config_text: str) -> dict:
        """Persist the provided Reticulum configuration content and keep a backup.

        Args:
            config_text (str): Raw ini content to persist.

        Returns:
            dict: Details about the persisted backup and target path.
        """

        validation = self.validate_reticulum_config_text(config_text)
        if not validation.get("valid"):
            errors = validation.get("errors") or []
            details = "; ".join(str(error) for error in errors if error)
            message = "Invalid Reticulum configuration payload"
            if details:
                message = f"{message}: {details}"
            raise ValueError(message)
        backup_path = self._backup_reticulum_config()
        self.reticulum_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.reticulum_config_path.write_text(config_text, encoding="utf-8")
        return {
            "applied": True,
            "config_path": str(self.reticulum_config_path),
            "backup_path": str(backup_path) if backup_path else None,
        }

    def rollback_config_text(self, backup_path: str | None = None) -> dict:
        """Restore the config.ini file from a backup.

        Args:
            backup_path (str | None): Optional backup path override.

        Returns:
            dict: Details about the restored backup.
        """

        target_backup = Path(backup_path) if backup_path else self._latest_backup()
        if target_backup is None or not target_backup.exists():
            return {"rolled_back": False, "error": "No backup available"}
        content = target_backup.read_text(encoding="utf-8")
        self.config_path.write_text(content, encoding="utf-8")
        return {"rolled_back": True, "backup_path": str(target_backup)}

    def rollback_reticulum_config_text(self, backup_path: str | None = None) -> dict:
        """Restore the Reticulum configuration file from a backup.

        Args:
            backup_path (str | None): Optional backup path override.

        Returns:
            dict: Details about the restored backup.
        """

        target_backup = (
            Path(backup_path) if backup_path else self._latest_reticulum_backup()
        )
        if target_backup is None or not target_backup.exists():
            return {"rolled_back": False, "error": "No backup available"}
        content = target_backup.read_text(encoding="utf-8")
        self.reticulum_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.reticulum_config_path.write_text(content, encoding="utf-8")
        return {"rolled_back": True, "backup_path": str(target_backup)}

    # ------------------------------------------------------------------ #
    # private helpers
    # ------------------------------------------------------------------ #
