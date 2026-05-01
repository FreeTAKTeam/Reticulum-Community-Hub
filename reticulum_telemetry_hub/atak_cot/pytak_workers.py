"""PyTAK worker classes used by :mod:`pytak_client`."""

from __future__ import annotations

import asyncio
import logging
import sys
import types
import xml.etree.ElementTree as ET
from configparser import ConfigParser
from configparser import SectionProxy
from contextlib import suppress
from importlib.util import find_spec
from typing import Any
from typing import Iterable
from typing import Optional
from typing import Union
from typing import cast

import RNS

if find_spec("aiohttp") is None:
    aiohttp_stub = types.ModuleType("aiohttp")

    class ClientSession:  # pylint: disable=too-few-public-methods
        """Fallback aiohttp ClientSession used for pytak import-time typing."""

    aiohttp_stub.ClientSession = ClientSession
    sys.modules.setdefault("aiohttp", aiohttp_stub)
import pytak

from . import Event

CotPayload = Union[Event, ET.Element, str, bytes, dict]


def _is_iterable_payload(obj: Any) -> bool:
    """Return True when the object should be treated as a payload collection."""

    if isinstance(obj, (Event, ET.Element, str, bytes, dict)):
        return False
    return isinstance(obj, Iterable)


def _payload_to_xml_bytes(payload: CotPayload) -> bytes:
    """Convert supported payload types into ATAK XML bytes."""

    if isinstance(payload, Event):
        return payload.to_xml_bytes()
    if isinstance(payload, ET.Element):
        return ET.tostring(payload, encoding="utf-8")
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if isinstance(payload, dict):
        return Event.from_dict(payload).to_xml_bytes()
    raise TypeError(f"Unsupported payload type: {type(payload)!r}")


class SendWorker(pytak.QueueWorker):
    """pyTAK worker that pushes ATAK CoT XML payloads onto the TX queue."""

    def __init__(
        self,
        queue: asyncio.Queue,
        config: SectionProxy,
        message: Union[CotPayload, Iterable[CotPayload]],
    ) -> None:
        super().__init__(queue, config)
        self._messages: list[CotPayload]
        if _is_iterable_payload(message):
            self._messages = list(cast(Iterable[CotPayload], message))
        else:
            self._messages = [cast(CotPayload, message)]

    async def handle_data(self, data: CotPayload) -> None:
        await self.put_queue(_payload_to_xml_bytes(data))

    async def run(self, number_of_iterations: int = 0):
        _ = number_of_iterations
        for payload in self._messages:
            await self.handle_data(payload)


class ReceiveWorker(pytak.QueueWorker):
    """pyTAK worker that optionally parses incoming CoT XML into Event objects."""

    def __init__(
        self, queue: asyncio.Queue, config: SectionProxy, parse: bool = True
    ) -> None:
        super().__init__(queue, config)
        self._parse = parse
        self.result: Optional[Any] = None

    async def handle_data(self, data: Any) -> None:
        """Parse queue data into an Event when requested."""

        if not self._parse:
            self.result = data
            return
        try:
            self.result = Event.from_xml(data)
        except (ET.ParseError, TypeError, ValueError, AttributeError):
            self.result = data

    async def run(self, number_of_iterations: int = 0) -> None:
        _ = number_of_iterations
        try:
            data = await self.queue.get()
        except (asyncio.CancelledError, RuntimeError):
            return None
        await self.handle_data(data)
        return None


class StreamSendWorker(SendWorker):
    """Continuous send worker that drains an outbound queue."""

    def __init__(
        self,
        queue: asyncio.Queue,
        config: SectionProxy,
        outbound_queue: asyncio.Queue,
        stop_event: asyncio.Event,
    ) -> None:
        super().__init__(queue, config, [])
        self._outbound_queue = outbound_queue
        self._stop_event = stop_event

    async def run(self, number_of_iterations: int = 0):
        iterations = 0
        while not self._stop_event.is_set():
            if number_of_iterations and iterations >= number_of_iterations:
                return None
            try:
                payload = await asyncio.wait_for(
                    self._outbound_queue.get(), timeout=0.2
                )
            except asyncio.TimeoutError:
                continue
            except (asyncio.CancelledError, RuntimeError):
                return None
            await self.handle_data(payload)
            iterations += 1


class FTSCLITool(pytak.CLITool):
    """PyTAK CLI tool wrapper that tracks coroutine tasks for testing."""

    def __init__(
        self,
        config: ConfigParser,
        tx_queue: Union[asyncio.Queue, None] = None,
        rx_queue: Union[asyncio.Queue, None] = None,
    ) -> None:
        self.config_parser = config if isinstance(config, ConfigParser) else None
        section: ConfigParser | SectionProxy
        if isinstance(config, ConfigParser):
            section = (
                config[config.sections()[0]] if config.sections() else config["DEFAULT"]
            )
        else:
            section = config
        super().__init__(section, tx_queue, rx_queue)
        self.section = section
        self.tasks_to_complete = set()
        self.running_c_tasks = set()
        self.results: list[Any] = []

    def add_c_task(self, task):
        """Register a coroutine worker task to run alongside pyTAK tasks."""

        self.tasks_to_complete.add(task)

    def run_c_task(self, task):
        """Schedule a coroutine worker task and keep a handle for teardown."""

        self.running_c_tasks.add(asyncio.ensure_future(task.run()))

    def run_c_tasks(self, tasks=None):
        """Schedule all coroutine worker tasks."""

        tasks = tasks or self.tasks_to_complete
        for task in tasks:
            self.run_c_task(task)

    async def setup(self) -> None:
        """Connect to the configured TAK server and log outcomes."""

        cot_url = self.config.get("COT_URL", "")
        try:
            await super().setup()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self._logger.error(
                "Failed to connect to TAK server at %s: %s", cot_url or "unknown", exc
            )
            RNS.log(
                f"Failed to connect to TAK server at {cot_url or 'unknown'}: {exc}",
                RNS.LOG_ERROR,
            )
            raise
        self._logger.info("Connected to TAK server at %s", cot_url or "unknown")
        RNS.log(f"Connected to TAK server at {cot_url or 'unknown'}", RNS.LOG_INFO)

    async def run(self, number_of_iterations: int = 0) -> None:
        """Runs this Thread and its associated coroutine tasks."""

        _ = number_of_iterations
        self._logger.info("Run: %s", self.__class__)

        self.run_tasks()
        self.run_c_tasks()

        _done, _ = await asyncio.wait(
            self.running_c_tasks, return_when=asyncio.ALL_COMPLETED
        )
        await asyncio.sleep(getattr(self, "min_period", 0.1) or 0.1)

        results: list[Any] = []
        for task in self.tasks_to_complete:
            res = getattr(task, "result", None)
            if res is not None:
                results.append(res)

        for task in self.running_tasks:
            task.cancel()

        self.results = results
        return None


class PytakWorkerManager:  # pylint: disable=too-many-instance-attributes
    """Manage a persistent PyTAK CLI tool and worker queue."""

    def __init__(
        self, cli_tool: FTSCLITool, section: SectionProxy, parse_inbound: bool
    ) -> None:
        self.cli_tool = cli_tool
        self.section = section
        self.parse_inbound = parse_inbound
        self._outbound: asyncio.Queue = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._results: list[Any] = []
        self._task: Optional[asyncio.Task] = None
        self._session_task: Optional[asyncio.Task] = None
        self._logger = getattr(cli_tool, "_logger", logging.getLogger(__name__))
        self._backoff_seconds = 1.0

    async def start(self) -> None:
        """Start the long-running PyTAK session if it is not active."""

        if self._stop_event.is_set():
            self._stop_event = asyncio.Event()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_session())

    async def stop(self) -> None:
        """Stop the PyTAK session and cancel worker tasks."""

        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
            self._session_task = None

    async def enqueue(self, message: CotPayload) -> None:
        """Queue a payload for transmission over the active session."""

        await self._outbound.put(message)

    def results(self) -> list[Any]:
        """Return results collected from the most recent receive worker."""

        return list(self._results)

    async def _run_session(self) -> None:
        """Run a PyTAK session with exponential backoff on failures."""

        while not self._stop_event.is_set():
            send_stop = asyncio.Event()
            try:
                await self.cli_tool.setup()
                self.cli_tool.tasks_to_complete.clear()
                self.cli_tool.running_c_tasks.clear()

                send_worker = StreamSendWorker(
                    cast(asyncio.Queue, self.cli_tool.tx_queue),
                    self.section,
                    self._outbound,
                    send_stop,
                )
                receive_worker = ReceiveWorker(
                    cast(asyncio.Queue, self.cli_tool.rx_queue),
                    self.section,
                    parse=self.parse_inbound,
                )

                self.cli_tool.add_c_task(send_worker)
                self.cli_tool.add_c_task(receive_worker)
                self._results.clear()

                self._session_task = asyncio.create_task(self.cli_tool.run())
                try:
                    await self._session_task
                finally:
                    send_stop.set()
                    if self._session_task:
                        self._session_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await self._session_task

                if getattr(receive_worker, "result", None) is not None:
                    self._results.append(receive_worker.result)
            except asyncio.CancelledError:
                send_stop.set()
                if self._session_task is not None:
                    self._session_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await self._session_task
                raise
            except Exception as exc:  # pragma: no cover - defensive logging  # pylint: disable=broad-exception-caught
                send_stop.set()
                self._logger.error("PyTAK session error: %s", exc)
                await asyncio.sleep(self._backoff_seconds)
                self._backoff_seconds = min(self._backoff_seconds * 2, 30.0)
            else:
                send_stop.set()
                self._backoff_seconds = 1.0
        return None
