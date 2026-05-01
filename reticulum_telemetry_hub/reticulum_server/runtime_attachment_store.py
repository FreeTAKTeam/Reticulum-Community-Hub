"""Attachment storage and reply construction helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path

import LXMF
import RNS

import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.appearance import apply_icon_appearance
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeAttachmentStoreMixin:
    """Attachment storage and reply construction helpers."""

    @staticmethod
    def _first_present_value(entry: dict, keys: list[str]):
        """Return the first key value present in a dictionary.

        Args:
            entry (dict): Attachment metadata map.
            keys (list[str]): Keys to check in order.

        Returns:
            Any: The first matching value or ``None`` when absent.
        """

        lower_lookup = {}
        for key in entry:
            if isinstance(key, str):
                lower_lookup.setdefault(key.lower(), key)
        for key in keys:
            if key in entry:
                return entry.get(key)
            lookup_key = lower_lookup.get(key.lower())
            if lookup_key is not None:
                return entry.get(lookup_key)
        return None

    @staticmethod
    def _decode_base64_payload(payload: str) -> bytes | None:
        """Decode base64 content safely.

        Args:
            payload (str): Base64-encoded string.

        Returns:
            bytes | None: Decoded bytes or ``None`` if decoding fails.
        """

        compact = "".join(payload.split())
        try:
            return base64.b64decode(compact, validate=True)
        except (binascii.Error, ValueError):
            return None

    @staticmethod
    def _should_decode_base64(payload: str) -> bool:
        """Heuristically determine whether a string looks base64 encoded."""

        compact = "".join(payload.split())
        if compact.startswith("data:") and "base64," in compact:
            return True
        if any(marker in compact for marker in ("=", "+", "/")):
            return True
        if len(compact) >= 12 and len(compact) % 4 == 0:
            return bool(re.fullmatch(r"[A-Za-z0-9+/=]+", compact))
        return False

    def _coerce_attachment_data(
        self, data, *, media_type: str | None
    ) -> bytes | None:
        """Normalize attachment data into bytes.

        Args:
            data (Any): Raw attachment data.
            media_type (str | None): Attachment media type.

        Returns:
            bytes | None: Normalized bytes or ``None`` when unsupported.
        """

        if isinstance(data, (bytes, bytearray, memoryview)):
            return bytes(data)

        if isinstance(data, (list, tuple)):
            if all(isinstance(item, int) for item in data):
                try:
                    return bytes(data)
                except ValueError:
                    return None

        if isinstance(data, str):
            payload = data.strip()
            if not payload:
                return b""
            if payload.startswith("data:") and "base64," in payload:
                encoded = payload.split("base64,", 1)[1]
                decoded = self._decode_base64_payload(encoded)
                if decoded is not None:
                    return decoded
            # Reason: attachments may arrive as base64 when sent from JSON-only clients.
            if self._should_decode_base64(payload):
                decoded = self._decode_base64_payload(payload)
                if decoded is not None:
                    return decoded
            return payload.encode("utf-8")

        return None

    def _write_and_record_attachment(
        self,
        *,
        data: bytes,
        name: str,
        media_type: str | None,
        category: str,
        base_path: Path,
        topic_id: str | None,
    ):
        """
        Write an attachment to disk and record it via the API.

        Args:
            data (bytes): Raw attachment data.
            name (str): Attachment filename.
            media_type (str | None): Optional MIME type.
            category (str): Attachment category ("file" or "image").
            base_path (Path): Directory to write the attachment.

        Returns:
            FileAttachment | None: Stored record or None on failure.
        """

        api = getattr(self, "api", None)
        if api is None:
            return None
        try:
            target_path = self._unique_path(base_path, name)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(data)
            if category == "image":
                return api.store_image(
                    target_path,
                    name=target_path.name,
                    media_type=media_type,
                    topic_id=topic_id,
                )
            return api.store_file(
                target_path,
                name=target_path.name,
                media_type=media_type,
                topic_id=topic_id,
            )
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Failed to persist {category} attachment '{name}': {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return None

    def _extract_attachment_topic_id(self, commands: list[dict] | None) -> str | None:
        """Return the TopicID from an AssociateTopicID command if provided."""

        if not commands:
            return None
        command_manager = getattr(self, "command_manager", None)
        normalizer = (
            getattr(command_manager, "_normalize_command_name", None)
            if command_manager is not None
            else None
        )
        for command in commands:
            if not isinstance(command, dict):
                continue
            name = command.get(PLUGIN_COMMAND) or command.get("Command")
            if not name:
                continue
            normalized = normalizer(name) if callable(normalizer) else name
            if normalized == CommandManager.CMD_ASSOCIATE_TOPIC_ID:
                topic_id = CommandManager._extract_topic_id(command)
                if topic_id:
                    return str(topic_id)
        return None

    @staticmethod
    def _unique_path(base_path: Path, name: str) -> Path:
        """Return a unique, non-existing path for the attachment."""

        candidate = base_path / name
        if not candidate.exists():
            return candidate
        index = 1
        stem = candidate.stem
        suffix = candidate.suffix
        while True:
            next_candidate = candidate.with_name(f"{stem}_{index}{suffix}")
            if not next_candidate.exists():
                return next_candidate
            index += 1

    def _attachment_base_path(self, category: str) -> Path | None:
        """Return the configured base path for the given category."""

        api = getattr(self, "api", None)
        if api is None:
            return None
        config_manager = getattr(api, "_config_manager", None)
        if config_manager is None:
            return None
        config = getattr(config_manager, "config", None)
        if config is None:
            return None
        if category == "image":
            return config.image_storage_path
        return config.file_storage_path

    def _build_attachment_reply(
        self, message: LXMF.LXMessage, attachments, *, heading: str
    ) -> LXMF.LXMessage | None:
        """Create an acknowledgement LXMF message for stored attachments."""

        lines = [heading]
        for index, attachment in enumerate(attachments, start=1):
            attachment_id = getattr(attachment, "file_id", None)
            name = getattr(attachment, "name", "<file>")
            id_text = attachment_id if attachment_id is not None else "<pending>"
            lines.append(f"{index}. {name} (ID: {id_text})")
        return self._reply_message(message, "\n".join(lines))

    def _build_attachment_error_reply(
        self, message: LXMF.LXMessage, errors: list[str], *, heading: str
    ) -> LXMF.LXMessage | None:
        """Create an acknowledgement LXMF message for attachment errors."""

        lines = [heading]
        for index, error in enumerate(errors, start=1):
            lines.append(f"{index}. {error}")
        return self._reply_message(message, "\n".join(lines))

    def _reply_message(
        self, message: LXMF.LXMessage, content: str, fields: dict | None = None
    ) -> LXMF.LXMessage | None:
        """Construct a reply LXMF message to the sender."""

        if self.my_lxmf_dest is None:
            return None
        destination = None
        try:
            command_manager = getattr(self, "command_manager", None)
            if command_manager is not None and hasattr(command_manager, "_create_dest"):
                destination = (
                    command_manager._create_dest(  # pylint: disable=protected-access
                        message.source.identity
                    )
                )
        except Exception:
            destination = None
        if destination is None:
            try:
                destination = RNS.Destination(
                    message.source.identity,
                    RNS.Destination.OUT,
                    RNS.Destination.SINGLE,
                    "lxmf",
                    "delivery",
                )
            except Exception as exc:  # pragma: no cover - defensive log
                RNS.log(
                    f"Unable to build reply destination: {exc}",
                    getattr(RNS, "LOG_WARNING", 2),
                )
                return None
        response_fields = self._merge_standard_fields(
            source_fields=message.fields,
            extra_fields=fields,
        )
        if response_fields is None:
            response_fields = {}
        if LXMF.FIELD_EVENT not in response_fields:
            response_fields[LXMF.FIELD_EVENT] = self._build_event_field(
                event_type="rch.reply",
                direction="outbound",
                topic_id=self._extract_target_topic(message.fields),
            )
        return LXMF.LXMessage(
            destination,
            self.my_lxmf_dest,
            content,
            fields=apply_icon_appearance(response_fields),
            desired_method=LXMF.LXMessage.DIRECT,
        )

