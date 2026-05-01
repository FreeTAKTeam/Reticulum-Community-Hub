"""WebSocket delivery queue primitives and metrics helpers."""
# pylint: disable=import-error

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from dataclasses import field
from typing import Awaitable
from typing import Callable
from typing import Dict
from typing import Optional
from typing import TypeAlias

DEFAULT_WS_DELIVERY_QUEUE_SIZE = 64

def _metrics_increment(metrics: object | None, key: str, value: int = 1) -> None:
    """Increment a runtime metric counter when supported by ``metrics``."""

    if metrics is None:
        return
    increment = getattr(metrics, "increment", None)
    if callable(increment):
        increment(key, value)


def _metrics_set_gauge(metrics: object | None, key: str, value: float) -> None:
    """Set a runtime metric gauge when supported by ``metrics``."""

    if metrics is None:
        return
    setter = getattr(metrics, "set_gauge", None)
    if callable(setter):
        setter(key, value)


def _metrics_observe_ms(metrics: object | None, key: str, value_ms: float) -> None:
    """Record a runtime timer metric (in milliseconds) when supported."""

    if metrics is None:
        return
    observer = getattr(metrics, "observe_ms", None)
    if callable(observer):
        observer(key, value_ms)


# Contract: providers used by websocket handlers must be non-blocking
# (async-native or internally offloaded with ``asyncio.to_thread``).
TelemetrySnapshotProvider: TypeAlias = Callable[
    [int, Optional[str]],
    Awaitable[list[Dict[str, object]]],
]


@dataclass(eq=False)
class _QueuedDelivery:
    """Bounded delivery queue for a websocket subscriber callback."""

    callback: Callable[[Dict[str, object]], Awaitable[None]]
    loop: Optional[asyncio.AbstractEventLoop]
    queue_size: int = DEFAULT_WS_DELIVERY_QUEUE_SIZE
    on_terminal_failure: Optional[Callable[["_QueuedDelivery", Exception], None]] = None
    on_drop_oldest: Optional[Callable[[], None]] = None
    _queue: asyncio.Queue[object] | None = field(
        init=False, default=None, repr=False, compare=False
    )
    _worker: asyncio.Task[None] | None = field(
        init=False, default=None, repr=False, compare=False
    )
    _closed: bool = field(init=False, default=False, repr=False, compare=False)
    _failed: bool = field(init=False, default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Initialize the worker queue when a loop is available."""

        if self.loop is None:
            return
        self._queue = asyncio.Queue(maxsize=max(int(self.queue_size), 1))
        self._worker = self.loop.create_task(self._run())

    async def _run(self) -> None:
        """Drain queued entries sequentially for a subscriber."""

        if self._queue is None:
            return
        while True:
            item = await self._queue.get()
            try:
                if item is None:
                    return
                await self.callback(item)
            except Exception as exc:
                self._handle_terminal_failure(exc)
                return
            finally:
                self._queue.task_done()

    def enqueue(self, entry: Dict[str, object]) -> None:
        """Queue an entry for bounded delivery."""

        if self._closed:
            return
        if self._queue is None or self.loop is None or not self.loop.is_running():
            self._dispatch_direct(entry)
            return
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is self.loop:
            self._enqueue_on_loop(entry)
            return
        self.loop.call_soon_threadsafe(self._enqueue_on_loop, entry)

    def _enqueue_on_loop(self, entry: Dict[str, object]) -> None:
        """Enqueue an entry on the subscriber loop, dropping oldest on overflow."""

        if self._closed or self._queue is None:
            return
        if self._queue.full():
            with suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
                self._queue.task_done()
                callback = self.on_drop_oldest
                if callback is not None:
                    callback()
        with suppress(asyncio.QueueFull):
            self._queue.put_nowait(entry)

    def _dispatch_direct(self, entry: Dict[str, object]) -> None:
        """Fallback direct dispatch when no loop-backed queue exists."""

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self.callback(entry))

        def _on_done(completed: asyncio.Task[None]) -> None:
            with suppress(asyncio.CancelledError):
                exc = completed.exception()
                if exc is not None:
                    self._handle_terminal_failure(exc)

        task.add_done_callback(_on_done)

    def _handle_terminal_failure(self, exc: Exception) -> None:
        """Signal terminal callback failure once for this subscriber."""

        if self._failed:
            return
        self._failed = True
        callback = self.on_terminal_failure
        if callback is None:
            return
        callback(self, exc)

    def close(self) -> None:
        """Stop the worker queue for this subscriber."""

        if self._closed:
            return
        self._closed = True
        if self._queue is None or self.loop is None or not self.loop.is_running():
            if self._worker is not None:
                self._worker.cancel()
            return
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is self.loop:
            self._close_on_loop()
            return
        self.loop.call_soon_threadsafe(self._close_on_loop)

    def _close_on_loop(self) -> None:
        """Close the queue on its owning event loop."""

        if self._queue is None:
            if self._worker is not None:
                self._worker.cancel()
            return
        while self._queue.full():
            with suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
                self._queue.task_done()
        with suppress(asyncio.QueueFull):
            self._queue.put_nowait(None)


@dataclass(eq=False)
class _TelemetrySubscriber:
    """Configuration for a telemetry WebSocket subscriber."""

    delivery: _QueuedDelivery
    allowed_destinations: Optional[frozenset[str]]


@dataclass(eq=False)
class _MessageSubscriber:
    """Configuration for a message WebSocket subscriber."""

    delivery: _QueuedDelivery
    topic_id: Optional[str]
    source_hash: Optional[str]


