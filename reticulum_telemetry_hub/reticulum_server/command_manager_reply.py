"""Reply field composition and command event helpers."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from typing import Optional
import json

import LXMF
import RNS

from reticulum_telemetry_hub.api.models import Client
from reticulum_telemetry_hub.api.models import FileAttachment
from reticulum_telemetry_hub.message_delivery import normalize_topic_id
from reticulum_telemetry_hub.reticulum_server.appearance import apply_icon_appearance


class CommandReplyMixin:
    """Reply field composition and command event helpers."""

    @staticmethod
    def _identity_hex(identity: RNS.Identity) -> str:
        hash_bytes = getattr(identity, "hash", b"") or b""
        return hash_bytes.hex()

    def _resolve_identity_label(self, identity: str) -> tuple[str | None, str]:
        display_name = None
        if hasattr(self.api, "resolve_identity_display_name"):
            try:
                display_name = self.api.resolve_identity_display_name(identity)
            except Exception:  # pragma: no cover - defensive
                display_name = None
        if display_name:
            return display_name, f"{display_name} ({identity})"
        return None, identity

    @staticmethod
    def _format_client_entry(client: Client) -> str:
        metadata = client.metadata or {}
        metadata_str = json.dumps(metadata, sort_keys=True)
        try:
            identity_bytes = bytes.fromhex(client.identity)
            identity_value = RNS.prettyhexrep(identity_bytes)
        except (ValueError, TypeError):
            identity_value = client.identity
        return f"{identity_value}|{metadata_str}"

    def _reply(
        self, message: LXMF.LXMessage, content: str, *, fields: Optional[dict] = None
    ) -> LXMF.LXMessage:
        dest = self._create_dest(message.source.identity)
        resolved_fields = self._compose_reply_fields(
            message=message,
            content=content,
            fields=fields,
        )
        return LXMF.LXMessage(
            dest,
            self.my_lxmf_dest,
            content,
            fields=apply_icon_appearance(resolved_fields),
            desired_method=LXMF.LXMessage.DIRECT,
        )

    def _finalize_command_response(
        self,
        response: Optional[LXMF.LXMessage],
        *,
        command_name: str | None,
        status: str,
    ) -> Optional[LXMF.LXMessage]:
        """Ensure command replies include structured event metadata."""

        if response is None:
            return None
        if not hasattr(response, "fields"):
            return response
        response_fields = dict(response.fields or {})
        response_fields[LXMF.FIELD_EVENT] = self._build_event_field(
            event_type=self._EVENT_TYPE_COMMAND_RESULT,
            command_name=command_name,
            status=status,
        )
        response.fields = apply_icon_appearance(response_fields)
        return response

    def _compose_reply_fields(
        self,
        *,
        message: LXMF.LXMessage,
        content: str,
        fields: Optional[dict],
    ) -> dict:
        """Return reply fields with context metadata and command results."""

        merged: dict = {}
        source_fields = message.fields if isinstance(message.fields, dict) else {}
        for key in self._REPLY_CONTEXT_FIELDS:
            if key in source_fields and source_fields.get(key) is not None:
                merged[key] = source_fields.get(key)
        if fields:
            merged.update(fields)
        if LXMF.FIELD_RESULTS not in merged:
            merged[LXMF.FIELD_RESULTS] = self._build_results_field(content)
        if LXMF.FIELD_EVENT not in merged:
            merged[LXMF.FIELD_EVENT] = self._build_event_field(
                event_type=self._EVENT_TYPE_REPLY,
                command_name=None,
                status="ok",
            )
        return merged

    @classmethod
    def _build_results_field(cls, content: str):
        """Return a compact FIELD_RESULTS payload for command replies."""

        text = str(content or "")
        stripped = text.strip()
        if stripped:
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if parsed is not None:
                return parsed

        encoded_len = len(text.encode("utf-8", errors="ignore"))
        if encoded_len <= cls._MAX_RESULT_TEXT_BYTES:
            return text

        return {
            "truncated": True,
            "content_length_bytes": encoded_len,
            "preview": text[: cls._MAX_RESULT_TEXT_BYTES],
        }

    @staticmethod
    def _build_event_field(
        *,
        event_type: str,
        command_name: str | None,
        status: str,
    ) -> dict[str, object]:
        """Return a structured event payload for FIELD_EVENT."""

        payload: dict[str, object] = {
            "event_type": event_type,
            "status": status,
            "ts": int(time.time()),
            "source": "rch",
        }
        if command_name:
            payload["command"] = command_name
        return payload

    @staticmethod
    def _markdown_renderer_value() -> int:
        """Return the FIELD_RENDERER value for markdown content."""

        return int(getattr(LXMF, "RENDERER_MARKDOWN", 0x02))

    @staticmethod
    def _extract_topic_id(command: dict) -> Optional[str]:
        return normalize_topic_id(
            command.get("TopicID")
            or command.get("topic_id")
            or command.get("id")
            or command.get("ID")
        )

    @staticmethod
    def _extract_subscriber_id(command: dict) -> Optional[str]:
        return (
            command.get("SubscriberID")
            or command.get("subscriber_id")
            or command.get("id")
            or command.get("ID")
        )

    def _extract_file_id(self, command: dict) -> Optional[Any]:
        for field in ("FileID", "ImageID", "ID"):
            value = self._field_value(command, field)
            if value is not None:
                return value
        return None

    @staticmethod
    def _extract_identity(command: dict) -> Optional[str]:
        """Return identity hash from a command payload."""

        return (
            command.get("Identity")
            or command.get("identity")
            or command.get("Destination")
            or command.get("destination")
        )

    @staticmethod
    def _coerce_int_id(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _attachment_payload(self, attachment: FileAttachment) -> list:
        """Build a list payload compatible with Sideband/MeshChat clients."""

        file_path = Path(attachment.path)
        data = file_path.read_bytes()
        if attachment.media_type:
            return [attachment.name, data, attachment.media_type]
        return [attachment.name, data]

    def _build_attachment_fields(self, attachment: FileAttachment) -> dict:
        """Return LXMF fields carrying attachment content."""

        payload = self._attachment_payload(attachment)
        category = (attachment.category or "").lower()
        if category == "image":
            return {
                LXMF.FIELD_IMAGE: payload,
                LXMF.FIELD_FILE_ATTACHMENTS: [payload],
            }
        return {LXMF.FIELD_FILE_ATTACHMENTS: [payload]}

    def _record_event(
        self, event_type: str, message: str, *, metadata: Optional[dict] = None
    ) -> None:
        """Emit an event log entry when a log sink is configured."""

        if self.event_log is None:
            return
        self.event_log.add_event(event_type, message, metadata=metadata)
