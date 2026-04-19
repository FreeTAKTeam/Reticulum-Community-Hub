"""FastAPI pagination helpers for northbound routes."""

from __future__ import annotations

from typing import Any
from typing import Callable
from typing import Iterable
from typing import TypeVar

from fastapi import HTTPException

from reticulum_telemetry_hub.api.pagination import PageRequest
from reticulum_telemetry_hub.api.pagination import PaginatedResult


T = TypeVar("T")


def resolve_page_request(
    *,
    page: int | None,
    per_page: int | None,
    default_per_page: int,
    max_per_page: int,
) -> PageRequest | None:
    """Return a page request when pagination query params are present."""

    if page is None and per_page is None:
        return None

    resolved_page = page or 1
    resolved_per_page = per_page or default_per_page
    if resolved_per_page > max_per_page:
        raise HTTPException(
            status_code=422,
            detail=f"per_page must be less than or equal to {max_per_page}",
        )
    try:
        return PageRequest(page=resolved_page, per_page=resolved_per_page)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


def build_paginated_payload(
    result: PaginatedResult[T],
    serializer: Callable[[T], dict[str, Any]],
) -> dict[str, Any]:
    """Serialize a paginated result into the northbound envelope."""

    return {
        "items": [serializer(item) for item in result.items],
        "page": result.page,
        "per_page": result.per_page,
        "total": result.total,
        "total_pages": result.total_pages,
        "has_next": result.has_next,
        "has_previous": result.has_previous,
    }


def list_or_paginated_payload(
    *,
    page: int | None,
    per_page: int | None,
    default_per_page: int,
    max_per_page: int,
    paginated_items: Callable[[PageRequest], PaginatedResult[T]],
    legacy_items: Callable[[], Iterable[T]],
    serializer: Callable[[T], dict[str, Any]],
) -> list[dict[str, Any]] | dict[str, Any]:
    """Return the legacy list shape unless pagination is requested."""

    page_request = resolve_page_request(
        page=page,
        per_page=per_page,
        default_per_page=default_per_page,
        max_per_page=max_per_page,
    )
    if page_request is not None:
        return build_paginated_payload(
            paginated_items(page_request),
            serializer,
        )
    return [serializer(item) for item in legacy_items()]
