"""Pagination helpers for API list operations."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Callable
from typing import Generic
from typing import TypeVar


T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True)
class PageRequest:
    """Validated page request for list operations."""

    page: int
    per_page: int

    def __post_init__(self) -> None:
        """Validate page bounds."""

        if self.page < 1:
            raise ValueError("page must be greater than or equal to 1")
        if self.per_page < 1:
            raise ValueError("per_page must be greater than or equal to 1")

    @property
    def offset(self) -> int:
        """Return the database offset for this page."""

        return (self.page - 1) * self.per_page


@dataclass(frozen=True)
class PaginatedResult(Generic[T]):
    """A page of items plus pagination metadata."""

    items: list[T]
    page: int
    per_page: int
    total: int

    @classmethod
    def from_request(
        cls,
        *,
        items: list[T],
        request: PageRequest,
        total: int,
    ) -> "PaginatedResult[T]":
        """Build a paginated result from a validated request."""

        return cls(
            items=items,
            page=request.page,
            per_page=request.per_page,
            total=max(0, total),
        )

    @property
    def total_pages(self) -> int:
        """Return the number of available pages."""

        if self.total == 0:
            return 0
        return ceil(self.total / self.per_page)

    @property
    def has_next(self) -> bool:
        """Return whether a later page exists."""

        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        """Return whether an earlier page exists."""

        return self.page > 1

    def map_items(self, transform: Callable[[T], U]) -> "PaginatedResult[U]":
        """Return a result with transformed items and unchanged metadata."""

        return PaginatedResult(
            items=[transform(item) for item in self.items],
            page=self.page,
            per_page=self.per_page,
            total=self.total,
        )
