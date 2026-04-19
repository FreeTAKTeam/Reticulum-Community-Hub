"""Tests for shared northbound pagination helpers."""

from __future__ import annotations

from collections.abc import Iterable

from reticulum_telemetry_hub.api.pagination import PageRequest
from reticulum_telemetry_hub.api.pagination import PaginatedResult
from reticulum_telemetry_hub.northbound.pagination import list_or_paginated_payload


def test_list_or_paginated_payload_uses_paginated_path_only() -> None:
    """Verify requested pagination bypasses legacy full-list loading."""

    calls: list[PageRequest] = []

    def paginated_items(request: PageRequest) -> PaginatedResult[str]:
        calls.append(request)
        return PaginatedResult.from_request(
            items=["alpha", "bravo"],
            request=request,
            total=3,
        )

    def legacy_items() -> Iterable[str]:
        raise AssertionError("legacy list path should not run for paginated requests")

    payload = list_or_paginated_payload(
        page=1,
        per_page=2,
        default_per_page=50,
        max_per_page=100,
        paginated_items=paginated_items,
        legacy_items=legacy_items,
        serializer=lambda item: {"value": item},
    )

    assert calls == [PageRequest(page=1, per_page=2)]
    assert payload == {
        "items": [{"value": "alpha"}, {"value": "bravo"}],
        "page": 1,
        "per_page": 2,
        "total": 3,
        "total_pages": 2,
        "has_next": True,
        "has_previous": False,
    }


def test_list_or_paginated_payload_preserves_legacy_path_only() -> None:
    """Verify unpaged requests preserve the legacy list shape."""

    def paginated_items(request: PageRequest) -> PaginatedResult[str]:
        raise AssertionError(f"paginated path should not run without pagination params: {request}")

    payload = list_or_paginated_payload(
        page=None,
        per_page=None,
        default_per_page=50,
        max_per_page=100,
        paginated_items=paginated_items,
        legacy_items=lambda: ["alpha", "bravo"],
        serializer=lambda item: {"value": item},
    )

    assert payload == [{"value": "alpha"}, {"value": "bravo"}]
