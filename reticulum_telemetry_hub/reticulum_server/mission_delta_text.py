"""Shared text helpers for mission-delta markdown rendering."""

from __future__ import annotations

from typing import Any


DEFAULT_MAX_MARKDOWN_BYTES = 700


def clean_text(value: Any) -> str:
    """Return a flattened, trimmed text value."""

    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())


def clip_text(value: Any, max_chars: int) -> str:
    """Return a clipped text value."""

    text = clean_text(value)
    if not text:
        return ""
    limit = max(1, int(max_chars))
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[: limit - 3].rstrip()}..."


def status_label(value: Any) -> str:
    """Return a human-readable status string."""

    status = clean_text(value)
    return status.upper() if status else "UNKNOWN"


def bytes_len(text: str) -> int:
    """Return UTF-8 byte length for text."""

    return len(text.encode("utf-8"))
