"""Transport-agnostic internal API buses with an in-process async queue."""

from __future__ import annotations

import asyncio
import copy
import inspect
import logging
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from typing import Awaitable
from typing import Callable
from typing import Generic
from typing import Optional
from typing import TypeVar
from typing import Union

from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandResult
from reticulum_telemetry_hub.internal_api.v1.schemas import EventEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryResult


_LOGGER = logging.getLogger(__name__)

TEnvelope = TypeVar("TEnvelope")
TResult = TypeVar("TResult")

CommandHandler = Callable[
    [CommandEnvelope],
    Union[CommandResult, Awaitable[CommandResult]],
]
QueryHandler = Callable[
    [QueryEnvelope],
    Union[QueryResult, Awaitable[QueryResult]],
]
EventHandler = Callable[
    [EventEnvelope],
    Union[None, Awaitable[None]],
]


@dataclass
class _WorkItem(Generic[TEnvelope, TResult]):
    """Envelope plus awaiting future for queue dispatch."""

    envelope: TEnvelope
    future: asyncio.Future[TResult]


async def _maybe_await(result: Union[TResult, Awaitable[TResult]]) -> TResult:
    """Await coroutine results while leaving sync values untouched."""

    if inspect.isawaitable(result):
        return await result
    return result


def _copy_envelope(envelope: TEnvelope) -> TEnvelope:
    """Return a defensive copy of the envelope to avoid shared state."""

    copy_method = getattr(envelope, "model_copy", None)
    if callable(copy_method):
        return copy_method(deep=True)
    return copy.deepcopy(envelope)


class CommandBus(ABC):
    """Abstract command bus for synchronous command execution."""

    @abstractmethod
    def register_handler(self, handler: CommandHandler) -> None:
        """Register a command handler."""

    @abstractmethod
    async def start(self) -> None:
        """Start background processing."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop background processing."""

    @abstractmethod
    async def send(self, command: CommandEnvelope) -> CommandResult:
        """Dispatch a command and await its result."""


class QueryBus(ABC):
    """Abstract query bus for synchronous query execution."""

    @abstractmethod
    def register_handler(self, handler: QueryHandler) -> None:
        """Register a query handler."""

    @abstractmethod
    async def start(self) -> None:
        """Start background processing."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop background processing."""

    @abstractmethod
    async def execute(self, query: QueryEnvelope) -> QueryResult:
        """Dispatch a query and await its result."""


class EventBus(ABC):
    """Abstract event bus for asynchronous event publication."""

    @abstractmethod
    def subscribe(self, handler: EventHandler) -> Callable[[], None]:
        """Subscribe to events and return an unsubscribe callback."""

    @abstractmethod
    async def start(self) -> None:
        """Start background processing."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop background processing."""

    @abstractmethod
    async def publish(self, event: EventEnvelope) -> None:
        """Publish an event for asynchronous delivery."""


class _InProcessHandlerBus(Generic[TEnvelope, TResult]):
    """Shared in-process queue handling for command/query buses."""

    def __init__(self, max_queue_size: int) -> None:
        """Initialize the in-process bus."""

        self._max_queue_size = max(max_queue_size, 1)
        self._queue: Optional[asyncio.Queue[Union[_WorkItem[TEnvelope, TResult], object]]] = (
            None
        )
        self._handler: Optional[
            Callable[[TEnvelope], Union[TResult, Awaitable[TResult]]]
        ] = None
        self._worker: Optional[asyncio.Task[None]] = None
        self._running = False
        self._stop_sentinel = object()

    def register_handler(
        self, handler: Callable[[TEnvelope], Union[TResult, Awaitable[TResult]]]
    ) -> None:
        """Register the handler for incoming messages."""

        self._handler = handler

    async def start(self) -> None:
        """Start the queue worker."""

        if self._running:
            return
        self._queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._running = True
        self._worker = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """Stop the queue worker after draining items."""

        if not self._running:
            return
        self._running = False
        if self._queue is not None:
            await self._queue.put(self._stop_sentinel)
        if self._worker is not None:
            await self._worker
        self._worker = None

    async def dispatch(self, envelope: TEnvelope) -> TResult:
        """Dispatch an envelope and await the handler result."""

        if not self._running or self._queue is None:
            raise RuntimeError("Bus is not running")
        if self._handler is None:
            raise RuntimeError("Bus handler is not registered")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[TResult] = loop.create_future()
        await self._queue.put(_WorkItem(envelope=_copy_envelope(envelope), future=future))
        return await future

    async def _worker_loop(self) -> None:
        """Process queued work items sequentially."""

        if self._queue is None:
            return
        while True:
            item = await self._queue.get()
            if item is self._stop_sentinel:
                self._queue.task_done()
                break

            try:
                if self._handler is None:
                    raise RuntimeError("Bus handler is not registered")
                result = await _maybe_await(self._handler(item.envelope))
                if not item.future.cancelled():
                    item.future.set_result(result)
            except Exception as exc:
                if not item.future.cancelled():
                    item.future.set_exception(exc)
            finally:
                self._queue.task_done()


class InProcessCommandBus(CommandBus):
    """In-process command bus using an asyncio queue."""

    def __init__(self, *, max_queue_size: int = 64) -> None:
        """Initialize the command bus."""

        self._bus = _InProcessHandlerBus[CommandEnvelope, CommandResult](max_queue_size)

    def register_handler(self, handler: CommandHandler) -> None:
        """Register a command handler."""

        self._bus.register_handler(handler)

    async def start(self) -> None:
        """Start background processing."""

        await self._bus.start()

    async def stop(self) -> None:
        """Stop background processing."""

        await self._bus.stop()

    async def send(self, command: CommandEnvelope) -> CommandResult:
        """Dispatch a command and await its result."""

        return await self._bus.dispatch(command)


class InProcessQueryBus(QueryBus):
    """In-process query bus using an asyncio queue."""

    def __init__(self, *, max_queue_size: int = 64) -> None:
        """Initialize the query bus."""

        self._bus = _InProcessHandlerBus[QueryEnvelope, QueryResult](max_queue_size)

    def register_handler(self, handler: QueryHandler) -> None:
        """Register a query handler."""

        self._bus.register_handler(handler)

    async def start(self) -> None:
        """Start background processing."""

        await self._bus.start()

    async def stop(self) -> None:
        """Stop background processing."""

        await self._bus.stop()

    async def execute(self, query: QueryEnvelope) -> QueryResult:
        """Dispatch a query and await its result."""

        return await self._bus.dispatch(query)


class InProcessEventBus(EventBus):
    """In-process event bus using an asyncio queue."""

    def __init__(self, *, max_queue_size: int = 64) -> None:
        """Initialize the event bus."""

        self._max_queue_size = max(max_queue_size, 1)
        self._queue: Optional[asyncio.Queue[Union[EventEnvelope, object]]] = None
        self._worker: Optional[asyncio.Task[None]] = None
        self._running = False
        self._stop_sentinel = object()
        self._subscribers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> Callable[[], None]:
        """Subscribe to events and return an unsubscribe callback."""

        self._subscribers.append(handler)

        def _unsubscribe() -> None:
            if handler in self._subscribers:
                self._subscribers.remove(handler)

        return _unsubscribe

    async def start(self) -> None:
        """Start background processing."""

        if self._running:
            return
        self._queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._running = True
        self._worker = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """Stop background processing."""

        if not self._running:
            return
        self._running = False
        if self._queue is not None:
            await self._queue.put(self._stop_sentinel)
        if self._worker is not None:
            await self._worker
        self._worker = None

    async def publish(self, event: EventEnvelope) -> None:
        """Publish an event for asynchronous delivery."""

        if not self._running or self._queue is None:
            raise RuntimeError("Event bus is not running")
        await self._queue.put(_copy_envelope(event))

    async def _worker_loop(self) -> None:
        """Dispatch events to subscribers sequentially."""

        if self._queue is None:
            return
        while True:
            item = await self._queue.get()
            if item is self._stop_sentinel:
                self._queue.task_done()
                break

            for handler in list(self._subscribers):
                try:
                    await _maybe_await(handler(_copy_envelope(item)))
                except Exception:
                    _LOGGER.exception(
                        "Event handler failed",
                        extra={
                            "event_id": str(item.event_id),
                            "event_type": item.event_type.value,
                        },
                    )
            self._queue.task_done()
