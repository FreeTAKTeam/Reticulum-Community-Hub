"""Reply and attachment persistence helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

from pathlib import Path

import LXMF
import RNS

from reticulum_telemetry_hub.api.models import FileAttachment
import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeReplyMixin:
    """Reply and attachment persistence helpers."""

    def _reply_with_app_info(self, message: LXMF.LXMessage) -> None:
        """Send an application info reply to the given message source.

        Args:
            message (LXMF.LXMessage): Message requiring an informational reply.
        """

        self._reply_with_command_handler(
            message, "_handle_get_app_info", "app info reply"
        )

    def _reply_with_help(self, message: LXMF.LXMessage) -> None:
        """Send a help reply to the given message source.

        Args:
            message (LXMF.LXMessage): Message requiring a help reply.
        """

        self._reply_with_command_handler(message, "_handle_help", "help reply")

    def _reply_with_command_handler(
        self,
        message: LXMF.LXMessage,
        handler_name: str,
        response_label: str,
    ) -> None:
        """Reply using a command manager handler when available."""

        command_manager = getattr(self, "command_manager", None)
        router = getattr(self, "lxm_router", None)
        if command_manager is None or router is None:
            return
        handler = getattr(command_manager, handler_name, None)
        if handler is None:
            return
        try:
            response = handler(message)
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Unable to build {response_label}: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return
        try:
            router.handle_outbound(response)
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Unable to send {response_label}: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _persist_attachments_from_fields(
        self, message: LXMF.LXMessage, *, topic_id: str | None = None
    ) -> tuple[list[LXMF.LXMessage], list[FileAttachment]]:
        """
        Persist file and image attachments from LXMF fields.

        Args:
            message (LXMF.LXMessage): Incoming LXMF message that may include
                ``FIELD_FILE_ATTACHMENTS`` or ``FIELD_IMAGE`` entries.

        Returns:
            tuple[list[LXMF.LXMessage], list[FileAttachment]]: Replies acknowledging
                stored attachments and the stored attachment records.
        """

        if not message.fields:
            return [], []
        stored_files, file_errors = self._store_attachment_payloads(
            message.fields.get(LXMF.FIELD_FILE_ATTACHMENTS),
            category="file",
            default_prefix="file",
            topic_id=topic_id,
        )
        stored_images, image_errors = self._store_attachment_payloads(
            message.fields.get(LXMF.FIELD_IMAGE),
            category="image",
            default_prefix="image",
            topic_id=topic_id,
        )
        stored_attachments = stored_files + stored_images
        attachment_errors = file_errors + image_errors
        acknowledgements: list[LXMF.LXMessage] = []
        if stored_files:
            reply = self._build_attachment_reply(
                message, stored_files, heading="Stored files:"
            )
            if reply:
                acknowledgements.append(reply)
        if stored_images:
            reply = self._build_attachment_reply(
                message, stored_images, heading="Stored images:"
            )
            if reply:
                acknowledgements.append(reply)
        if attachment_errors:
            reply = self._build_attachment_error_reply(
                message, attachment_errors, heading="Attachment errors:"
            )
            if reply:
                acknowledgements.append(reply)
        return acknowledgements, stored_attachments

    def _store_attachment_payloads(
        self, payload, *, category: str, default_prefix: str, topic_id: str | None = None
    ) -> tuple[list[FileAttachment], list[str]]:
        """
        Normalize and store incoming attachments.

        Args:
            payload: Raw LXMF field payload (bytes, dict, or list).
            category (str): Attachment category ("file" or "image").
            default_prefix (str): Filename prefix when no name is supplied.

        Returns:
            tuple[list, list[str]]: Stored attachment records from the API and
                any errors encountered while parsing.
        """

        if payload in (None, {}, []):
            return [], []
        api = getattr(self, "api", None)
        base_path = self._attachment_base_path(category)
        if api is None or base_path is None:
            return [], []
        entries = self._normalize_attachment_payloads(
            payload, category=category, default_prefix=default_prefix
        )
        stored: list[FileAttachment] = []
        errors: list[str] = []
        for entry in entries:
            if entry.get("error"):
                errors.append(entry["error"])
                continue
            stored_entry = self._write_and_record_attachment(
                data=entry["data"],
                name=entry["name"],
                media_type=entry.get("media_type"),
                category=category,
                base_path=base_path,
                topic_id=topic_id,
            )
            if stored_entry is not None:
                stored.append(stored_entry)
        return stored, errors

    def _attachment_payload(self, attachment: FileAttachment) -> list:
        """Return an LXMF-compatible attachment payload list."""

        file_path = Path(attachment.path)
        data = file_path.read_bytes()
        if attachment.media_type:
            return [attachment.name, data, attachment.media_type]
        return [attachment.name, data]

    def _build_lxmf_attachment_fields(
        self, attachments: list[FileAttachment]
    ) -> dict | None:
        """Build LXMF fields for outbound attachments."""

        if not attachments:
            return None
        file_payloads: list[list] = []
        image_payloads: list[list] = []
        for attachment in attachments:
            payload = self._attachment_payload(attachment)
            category = (attachment.category or "").lower()
            if category == "image":
                image_payloads.append(payload)
                file_payloads.append(payload)
            else:
                file_payloads.append(payload)
        fields: dict = {}
        if file_payloads:
            fields[LXMF.FIELD_FILE_ATTACHMENTS] = file_payloads
        if image_payloads:
            fields[LXMF.FIELD_IMAGE] = image_payloads
        return fields

