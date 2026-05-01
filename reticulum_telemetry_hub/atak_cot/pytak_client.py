"""PyTAK client helpers for sending and receiving Cursor on Target events."""

from __future__ import annotations

import asyncio
import atexit
import weakref
from configparser import ConfigParser, SectionProxy
from threading import Event as ThreadEvent
from threading import Lock
from threading import Thread
from typing import Any, Awaitable, Iterable, Optional, Union, cast

from . import Event
from .pytak_workers import CotPayload
from .pytak_workers import FTSCLITool
from .pytak_workers import PytakWorkerManager
from .pytak_workers import pytak

__all__ = [
    "CotPayload",
    "FTSCLITool",
    "PytakClient",
    "PytakWorkerManager",
    "pytak",
]

def _shutdown_weak(ref: "weakref.ReferenceType[PytakClient]") -> None:
    """Invoke shutdown on a weakly referenced :class:`PytakClient`."""

    client = ref()
    if client is None:
        return
    client._shutdown_sync()  # pylint: disable=protected-access

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
