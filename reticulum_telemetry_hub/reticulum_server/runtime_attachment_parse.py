"""Attachment payload parsing helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

from datetime import datetime
import mimetypes
import re
import time
import uuid
from pathlib import Path

import RNS

import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeAttachmentParseMixin:
    """Attachment payload parsing helpers."""

    def _normalize_attachment_payloads(
        self, payload, *, category: str, default_prefix: str
    ) -> list[dict]:
        """
        Convert the raw LXMF payload into attachment dictionaries.

        Args:
            payload: Raw LXMF field value.
            category (str): Attachment category ("file" or "image").
            default_prefix (str): Prefix for generated filenames.

        Returns:
            list[dict]: Normalized payload entries.
        """

        entries = payload
        if isinstance(payload, (list, tuple)):
            if self._is_single_attachment_sequence(payload):
                entries = [payload]
        else:
            entries = [payload]
        normalized: list[dict] = []
        for index, entry in enumerate(entries):
            parsed = self._parse_attachment_entry(
                entry, category=category, default_prefix=default_prefix, index=index
            )
            if parsed is not None:
                normalized.append(parsed)
        return normalized
    @staticmethod
    def _is_single_attachment_sequence(payload: list | tuple) -> bool:
        """Return True when a sequence most likely represents one attachment entry."""

        if not payload:
            return False
        if all(isinstance(item, int) for item in payload):
            return True
        first = payload[0]
        if isinstance(first, (dict, list, tuple)):
            return False
        if any(
            RuntimeAttachmentParseMixin._is_binary_attachment_candidate(item)
            for item in payload
        ):
            return True
        if len(payload) == 1:
            return True
        if len(payload) <= 3 and isinstance(first, str):
            return True
        return False

    def _parse_attachment_entry(
        self, entry, *, category: str, default_prefix: str, index: int
    ) -> dict | None:
        """
        Extract attachment data, name, and media type from an entry.

        Args:
            entry: Raw attachment value (dict, bytes, or string).
            category (str): Attachment category ("file" or "image").
            default_prefix (str): Prefix for generated filenames.
            index (int): Entry index for uniqueness.

        Returns:
            dict | None: Parsed attachment info when data is available.
        """

        data = None
        media_type = None
        name = None
        extension_hint = None
        if isinstance(entry, dict):
            data = self._first_present_value(
                entry, ["data", "bytes", "content", "blob"]
            )
            media_type = self._first_present_value(
                entry, ["media_type", "mime", "mime_type", "type"]
            )
            name = self._first_present_value(
                entry, ["name", "filename", "file_name", "title"]
            )
        elif isinstance(entry, (bytes, bytearray, memoryview)):
            data = bytes(entry)
        elif isinstance(entry, str):
            data = entry
        elif isinstance(entry, (list, tuple)):
            parsed = self._parse_sequence_attachment_entry(entry)
            if parsed:
                data = parsed.get("data")
                media_type = parsed.get("media_type")
                name = parsed.get("name")
                extension_hint = parsed.get("extension_hint")

        if data is None:
            reason = "Missing attachment data"
            attachment_name = name or f"{category}-{index + 1}"
            RNS.log(
                f"Ignoring attachment without data (category={category}).",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return {"error": f"{reason}: {attachment_name}"}

        if isinstance(media_type, str):
            media_type = media_type.strip() or None
        data = self._coerce_attachment_data(data, media_type=media_type)
        if data is None:
            reason = "Unsupported attachment data format"
            attachment_name = name or f"{category}-{index + 1}"
            RNS.log(
                f"Ignoring attachment with unsupported data format (category={category}).",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return {"error": f"{reason}: {attachment_name}"}
        if not data:
            reason = "Empty attachment data"
            attachment_name = name or f"{category}-{index + 1}"
            RNS.log(
                f"Ignoring empty attachment payload (category={category}).",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return {"error": f"{reason}: {attachment_name}"}
        if not media_type and category == "image":
            media_type = self._infer_image_media_type(data)
        if not media_type and category == "image" and extension_hint:
            media_type = self._guess_image_media_type_from_extension(extension_hint)
        generated_name = None
        if category == "image" and not name and extension_hint:
            generated_name = self._image_name_from_extension(extension_hint)
        safe_name = self._sanitize_attachment_name(
            name
            or generated_name
            or self._default_attachment_name(default_prefix, index, media_type)
        )
        if media_type and not Path(safe_name).suffix:
            extension = self._guess_media_type_extension(media_type)
            if extension:
                safe_name = f"{safe_name}{extension}"
        media_type = media_type or self._guess_media_type(safe_name, category)
        return {"data": data, "name": safe_name, "media_type": media_type}

    def _parse_sequence_attachment_entry(self, entry: list | tuple) -> dict:
        """Parse list/tuple attachment formats into name/data/media_type parts."""

        if not entry:
            return {}

        if all(isinstance(item, int) for item in entry):
            return {"data": list(entry), "name": None, "media_type": None}

        data_index = None
        for index, item in enumerate(entry):
            if self._is_binary_attachment_candidate(item):
                data_index = index
                break

        if data_index is None:
            data_index = 1 if len(entry) >= 2 else 0

        data = entry[data_index]

        string_tokens: list[tuple[int, str]] = []
        for index, item in enumerate(entry):
            if index == data_index or not isinstance(item, str):
                continue
            token = item.strip()
            if token:
                string_tokens.append((index, token))

        media_type = None
        for _, token in string_tokens:
            if self._looks_like_media_type(token):
                media_type = token
                break

        name = self._select_attachment_name_token(
            string_tokens, media_type=media_type
        )
        extension_hint = self._extract_extension_hint_from_tokens(string_tokens)

        return {
            "data": data,
            "name": name,
            "media_type": media_type,
            "extension_hint": extension_hint,
        }

    @staticmethod
    def _is_binary_attachment_candidate(value) -> bool:
        """Return True for values that are likely raw attachment bytes."""

        if isinstance(value, (bytes, bytearray, memoryview)):
            return True
        return isinstance(value, (list, tuple)) and bool(value) and all(
            isinstance(item, int) for item in value
        )

    @staticmethod
    def _looks_like_media_type(value: str) -> bool:
        """Return True when a token resembles a MIME media type."""

        return bool(
            re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*",
                value,
            )
        )

    @staticmethod
    def _looks_like_extension_label(value: str) -> bool:
        """Return True when a token looks like an extension-only label."""

        token = value.strip().lstrip(".").lower()
        return token in {
            "jpg",
            "jpeg",
            "png",
            "gif",
            "bmp",
            "webp",
            "tif",
            "tiff",
            "heic",
            "heif",
        }

    @staticmethod
    def _looks_like_filename_token(value: str) -> bool:
        """Return True when a token is likely an actual filename."""

        candidate = Path(value).name
        if not candidate:
            return False
        if any(separator in value for separator in ("/", "\\")):
            return True
        if Path(candidate).suffix:
            return True
        return False

    def _select_attachment_name_token(
        self,
        string_tokens: list[tuple[int, str]],
        *,
        media_type: str | None,
    ) -> str | None:
        """Pick the most likely filename token from string values."""

        if not string_tokens:
            return None
        non_media_tokens = [
            token for _, token in string_tokens if not media_type or token != media_type
        ]
        if not non_media_tokens:
            return None

        for token in non_media_tokens:
            if self._looks_like_filename_token(token):
                return token

        for token in non_media_tokens:
            if not self._looks_like_extension_label(token):
                return token

        return None

    def _extract_extension_hint_from_tokens(
        self, string_tokens: list[tuple[int, str]]
    ) -> str | None:
        """Return an image extension hint from string tokens when present."""

        if not string_tokens:
            return None
        for _, token in string_tokens:
            normalized = self._normalize_extension_token(token)
            if normalized:
                return normalized
        return None

    @staticmethod
    def _normalize_extension_token(value: str) -> str | None:
        """Normalize a token into an extension string without a leading dot."""

        token = value.strip().lower()
        if not token:
            return None
        if "/" in token and RuntimeAttachmentParseMixin._looks_like_media_type(token):
            guessed = RuntimeAttachmentParseMixin._guess_media_type_extension(token)
            if guessed:
                token = guessed.lstrip(".").lower()
        token = token.lstrip(".")
        if not token:
            return None
        if re.fullmatch(r"[a-z0-9]{2,8}", token):
            return token
        return None

    @staticmethod
    def _image_name_from_extension(extension: str) -> str:
        """Build timestamped image name from an extension hint."""

        timestamp = datetime.now().strftime("Image_%Y_%m_%d_%H_%M_%S")
        return f"{timestamp}.{extension}"

    @staticmethod
    def _guess_image_media_type_from_extension(extension: str) -> str | None:
        """Return an image media type from a file extension."""

        normalized = extension.strip().lstrip(".").lower()
        if not normalized:
            return None
        guessed, _ = mimetypes.guess_type(f"image.{normalized}")
        if guessed:
            return guessed
        fallback = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "bmp": "image/bmp",
            "webp": "image/webp",
        }
        return fallback.get(normalized)

    @staticmethod
    def _sanitize_attachment_name(name: str) -> str:
        """Return a filename-safe attachment name."""

        candidate = Path(name).name or "attachment"
        return candidate

    def _default_attachment_name(
        self, prefix: str, index: int, media_type: str | None
    ) -> str:
        """Return a unique attachment name using the prefix and media type."""

        suffix = ""
        guessed = self._guess_media_type_extension(media_type)
        if guessed:
            suffix = guessed
        unique_id = uuid.uuid4().hex[:8]
        return f"{prefix}-{int(time.time())}-{index}-{unique_id}{suffix}"

    @staticmethod
    def _guess_media_type(name: str, category: str) -> str | None:
        """Guess the media type from the name or category."""

        guessed, _ = mimetypes.guess_type(name)
        if guessed:
            return guessed
        if category == "image":
            return "image/octet-stream"
        return "application/octet-stream"

    @staticmethod
    def _infer_image_media_type(data: bytes) -> str | None:
        """Infer an image media type from raw bytes.

        Args:
            data (bytes): Raw image bytes.

        Returns:
            str | None: MIME type when recognized, otherwise ``None``.
        """

        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if data.startswith(b"BM"):
            return "image/bmp"
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return "image/webp"
        return None

    @staticmethod
    def _guess_media_type_extension(media_type: str | None) -> str:
        """Guess a file extension from the supplied media type."""

        if not media_type:
            return ""
        guessed = mimetypes.guess_extension(media_type) or ""
        if guessed:
            return guessed
        fallback = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
            "image/webp": ".webp",
        }
        guessed = fallback.get(media_type.lower(), "")
        return guessed
