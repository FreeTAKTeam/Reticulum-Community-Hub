"""Filesystem adapter abstractions for attachment operations."""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from pathlib import Path
from typing import BinaryIO


class FileSystemAdapter(ABC):
    """Abstract filesystem interface for attachment persistence."""

    @abstractmethod
    def ensure_directory(self, path: Path) -> None:
        """Ensure a directory exists."""

    @abstractmethod
    def is_file(self, path: Path) -> bool:
        """Return ``True`` when a path points to a file."""

    @abstractmethod
    def resolve(self, path: Path) -> Path:
        """Return the resolved absolute path."""

    @abstractmethod
    def stat_size(self, path: Path) -> int:
        """Return a file size in bytes."""

    @abstractmethod
    def write_bytes(self, path: Path, content: bytes) -> None:
        """Write bytes to disk."""

    @abstractmethod
    def delete_file(self, path: Path) -> None:
        """Delete a file from disk."""

    @abstractmethod
    def open_binary_read(self, path: Path) -> BinaryIO:
        """Open a file in binary mode."""


class LocalFileSystemAdapter(FileSystemAdapter):
    """Pathlib-backed filesystem implementation."""

    def ensure_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def is_file(self, path: Path) -> bool:
        return path.is_file()

    def resolve(self, path: Path) -> Path:
        return path.resolve()

    def stat_size(self, path: Path) -> int:
        return path.stat().st_size

    def write_bytes(self, path: Path, content: bytes) -> None:
        path.write_bytes(content)

    def delete_file(self, path: Path) -> None:
        path.unlink()

    def open_binary_read(self, path: Path) -> BinaryIO:
        return path.open("rb")
