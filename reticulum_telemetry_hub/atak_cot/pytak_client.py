from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Union, Optional, Any, cast
import xml.etree.ElementTree as ET
from configparser import ConfigParser, SectionProxy

try:
    import pytak
except ImportError as exc:  # pragma: no cover - dependency guidance
    raise ImportError(
        "PyTAK is required. Install it with 'python -m pip install pytak'. "
        "See https://pypi.org/project/pytak/ for release details."
    ) from exc

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

    async def run(self, number_of_iterations: int = 0) -> None:
        data = await self.queue.get()
        if not self._parse:
            self.result = data
            return None
        try:
            self.result = Event.from_xml(data)
        except Exception:
            self.result = data
        return None


class FTSCLITool(pytak.CLITool):
    def __init__(
        self,
        config: ConfigParser,
        tx_queue: Union[asyncio.Queue, None] = None,
        rx_queue: Union[asyncio.Queue, None] = None,
    ) -> None:
        super().__init__(config, tx_queue, rx_queue)
        self.tasks_to_complete = set()
        self.running_c_tasks = set()
        # store results from the last run here
        self.results: list[Any] = []

    def add_c_task(self, task):
        self.tasks_to_complete.add(task)

    def run_c_task(self, task):
        self.running_c_tasks.add(asyncio.ensure_future(task.run()))

    def run_c_tasks(self, tasks=None):
        tasks = tasks or self.tasks_to_complete
        for task in tasks:
            self.run_c_task(task)

    async def run(self, number_of_iterations: int = 0) -> None:
        """Runs this Thread and its associated coroutine tasks."""
        self._logger.info("Run: %s", self.__class__)

        self.run_tasks()
        self.run_c_tasks()

        done, _ = await asyncio.wait(
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


class PytakClient:
    """Utility wrapper that wires ATAK Event payloads into pyTAK workers."""

    def __init__(self, config: Optional[ConfigParser] = None) -> None:
        self._config = config

    def _setup_config(self) -> ConfigParser:
        """Create config if a custom one is not passed."""
        config = ConfigParser()
        config["fts"] = {
            "COT_URL": "tcp://127.0.0.1:8087",
            "CALLSIGN": "FTS_PYTAK",
        }
        return config

    def _ensure_config(self, config: Optional[ConfigParser]) -> ConfigParser:
        if config is not None:
            return config
        if self._config is None:
            self._config = self._setup_config()
        return self._config

    def _config_section(
        self, config: ConfigParser, section: str = "fts"
    ) -> SectionProxy:
        if config.has_section(section):
            return config[section]
        sections = config.sections()
        if sections:
            return config[sections[0]]
        raise ValueError("Configuration must contain at least one section.")

    async def create_and_send_message(
        self,
        message: Union[CotPayload, Iterable[CotPayload]],
        config: Optional[ConfigParser] = None,
        parse_inbound: bool = True,
    ):
        cfg = self._ensure_config(config)
        section = self._config_section(cfg)

        # pyTAK's CLITool expects a section-level view so option lookups do not
        # require a section name. Passing the SectionProxy avoids calling
        # ConfigParser.get(section, option) with missing arguments.
        cli_tool = FTSCLITool(section)
        await cli_tool.setup()

        cli_tool.add_c_task(
            SendWorker(cast(asyncio.Queue, cli_tool.tx_queue), section, message)
        )
        cli_tool.add_c_task(
            ReceiveWorker(
                cast(asyncio.Queue, cli_tool.rx_queue), section, parse=parse_inbound
            )
        )

        await cli_tool.run()
        return cli_tool.results

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
