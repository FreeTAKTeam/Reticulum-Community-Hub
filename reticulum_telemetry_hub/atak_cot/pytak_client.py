"""PyTAK client helpers for sending and receiving Cursor on Target events."""

from __future__ import annotations

import asyncio
import atexit
import logging
import weakref
import xml.etree.ElementTree as ET
from configparser import ConfigParser, SectionProxy
from contextlib import suppress
from threading import Event as ThreadEvent
from threading import Lock
from threading import Thread
from typing import Any, Awaitable, Iterable, Optional, Union, cast

import RNS
import pytak

from . import Event

CotPayload = Union[Event, ET.Element, str, bytes, dict]


def _shutdown_weak(ref: "weakref.ReferenceType[PytakClient]") -> None:
    """Invoke shutdown on a weakly referenced :class:`PytakClient`."""

    client = ref()
    if client is None:
        return
    client._shutdown_sync()  # pylint: disable=protected-access


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
        # Ensure a concrete list of CotPayload so the type checker knows
        # iterating yields a CotPayload for handle_data(...)
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
        # store parsed or raw data here so callers can inspect worker instances
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
        # store results from the last run here
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

        # Give the TX/RX workers a moment to drain the queues before cancelling
        # them. Without this pause, the main loop could cancel the TX worker
        # before it flushes the enqueued CoT payload.
        await asyncio.sleep(getattr(self, "min_period", 0.1) or 0.1)

        results: list[Any] = []

        # Collect results from worker instances (ReceiveWorker stores parsed data
        # on .result) instead of relying on coroutine return values.
        for task in self.tasks_to_complete:
            res = getattr(task, "result", None)
            if res is not None:
                results.append(res)

        # Close TX and RX workers aka connection to Server
        for task in self.running_tasks:
            task.cancel()

        # store results on the instance and return None to match base class
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


class PytakClient:  # pylint: disable=too-many-instance-attributes
    """Utility wrapper that wires ATAK Event payloads into pyTAK workers."""

    def __init__(self, config: Optional[ConfigParser] = None) -> None:
        self._config = config
        self._cli_tool: Optional[FTSCLITool] = None
        self._worker_manager: Optional[PytakWorkerManager] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[Thread] = None
        self._loop_ready = ThreadEvent()
        self._loop_lock = Lock()
        atexit.register(_shutdown_weak, weakref.ref(self))

    def __del__(self) -> None:
        try:
            self._shutdown_sync()  # pylint: disable=protected-access
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def _setup_config(self) -> ConfigParser:
        """Create config if a custom one is not passed."""
        config = ConfigParser()
        config["fts"] = {
            "COT_URL": "tcp://127.0.0.1:8087",
            "CALLSIGN": "FTS_PYTAK",
            "TAK_PROTO": "0",
            "FTS_COMPAT": "1",
        }
        return config

    def _ensure_config(self, config: Optional[ConfigParser]) -> ConfigParser:
        """
        Ensure a configuration object is present for PyTAK workers.

        Args:
            config (ConfigParser | None): Custom configuration provided by the caller.

        Returns:
            ConfigParser: The configuration to use for PyTAK interactions.
        """
        if config is not None:
            if self._config is None:
                self._config = config
            return config
        if self._config is None:
            self._config = self._setup_config()
        return self._config

    def _config_section(
        self, config: ConfigParser, section: str = "fts"
    ) -> SectionProxy:
        """
        Return the requested section or a fallback from a configuration object.

        Args:
            config (ConfigParser): Configuration containing PyTAK settings.
            section (str): Desired section name. Defaults to ``"fts"``.

        Returns:
            SectionProxy: Section with connection parameters.

        Raises:
            ValueError: If the configuration has no sections.
        """
        if config.has_section(section):
            return config[section]
        sections = config.sections()
        if sections:
            return config[sections[0]]
        raise ValueError("Configuration must contain at least one section.")

    def _ensure_cli_tool(self, config: ConfigParser) -> FTSCLITool:
        """Create or return a cached CLI tool backed by shared queues."""

        if self._cli_tool is None:
            tx_queue: asyncio.Queue = asyncio.Queue()
            rx_queue: asyncio.Queue = asyncio.Queue()
            self._cli_tool = FTSCLITool(config, tx_queue, rx_queue)
        return self._cli_tool

    def _ensure_manager(
        self, config: ConfigParser, parse_inbound: bool
    ) -> "PytakWorkerManager":
        """
        Return a running worker manager with the provided configuration.

        Args:
            config (ConfigParser): PyTAK configuration to apply.
            parse_inbound (bool): Whether inbound CoT data should be parsed.

        Returns:
            PytakWorkerManager: The configured worker manager.
        """

        cli_tool = self._ensure_cli_tool(config)
        if self._worker_manager is None:
            section = self._config_section(config)
            self._worker_manager = PytakWorkerManager(cli_tool, section, parse_inbound)
        else:
            self._worker_manager.parse_inbound = parse_inbound
        return self._worker_manager

    async def create_and_send_message(
        self,
        message: Union[CotPayload, Iterable[CotPayload]],
        config: Optional[ConfigParser] = None,
        parse_inbound: bool = True,
    ) -> list[Any]:
        """
        Send one or more CoT payloads through a PyTAK worker session.

        Args:
            message (CotPayload | Iterable[CotPayload]): Payload(s) to dispatch.
            config (ConfigParser | None): Optional configuration override.
            parse_inbound (bool): Whether to parse inbound data into :class:`Event`.

        Returns:
            list[Any]: Parsed or raw results from the receive worker.
        """
        cfg = self._ensure_config(config)
        manager = self._ensure_manager(cfg, parse_inbound)
        await self._run_in_loop(manager.start())
        await self._run_in_loop(manager.enqueue(message))
        return manager.results()

    async def send_event(
        self,
        event: Event,
        config: Optional[ConfigParser] = None,
        parse_inbound: bool = True,
    ):
        """Convenience helper that sends a single Event."""
        return await self.create_and_send_message(
            event, config=config, parse_inbound=parse_inbound
        )

    @staticmethod
    def _start_loop(
        loop: asyncio.AbstractEventLoop, ready_event: ThreadEvent
    ) -> None:
        """
        Start the event loop on a dedicated thread and signal readiness.

        Args:
            loop (asyncio.AbstractEventLoop): Event loop to run.
            ready_event (ThreadEvent): Event set once the loop is running.
        """
        asyncio.set_event_loop(loop)
        ready_event.set()
        loop.run_forever()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Ensure a background event loop exists for PyTAK tasks."""

        with self._loop_lock:
            if self._loop is not None and self._loop.is_running():
                return self._loop
            loop = asyncio.new_event_loop()
            self._loop = loop
            self._loop_ready.clear()
            thread = Thread(
                target=self._start_loop, args=(loop, self._loop_ready), daemon=True
            )
            self._loop_thread = thread
            thread.start()
        self._loop_ready.wait()
        return cast(asyncio.AbstractEventLoop, self._loop)

    async def _run_in_loop(self, coro: Awaitable[Any]) -> Any:
        """Execute a coroutine on the dedicated event loop and await it."""

        loop = self._ensure_loop()
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is loop:
            return await coro
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return await asyncio.wrap_future(future)

    async def stop(self) -> None:
        """Stop the PyTAK worker manager and background loop."""

        if self._worker_manager is not None:
            await self._run_in_loop(self._worker_manager.stop())
            self._worker_manager = None
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._loop_thread is not None:
                self._loop_thread.join(timeout=1.0)
        self._loop = None
        self._loop_thread = None

    def _shutdown_sync(self) -> None:
        """Best-effort cleanup for interpreter shutdown or GC."""

        if self._loop is None or not self._loop.is_running():
            self._loop = None
            self._loop_thread = None
            self._worker_manager = None
            return

        if self._worker_manager is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._worker_manager.stop(), self._loop
                )
                future.result(timeout=1.0)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            self._worker_manager = None

        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread is not None:
            self._loop_thread.join(timeout=1.0)
        self._loop = None
        self._loop_thread = None
