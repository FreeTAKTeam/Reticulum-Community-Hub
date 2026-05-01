"""Shared helpers for R3AKT route parsing."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from fastapi import status


def expand_tokens(value: str | None) -> set[str]:
    """Return lowercase comma-separated tokens from a query parameter."""
    if not value:
        return set()
    return {
        item.strip().lower()
        for item in value.split(",")
        if item and item.strip()
    }


def parse_iso_datetime(value: object) -> datetime | None:
    """Parse an optional ISO-8601 datetime route value."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="expires_at must be ISO-8601",
        ) from exc
