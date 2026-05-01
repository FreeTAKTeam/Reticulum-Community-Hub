"""Runtime support helpers for the Reticulum telemetry hub."""

from __future__ import annotations

import asyncio
import msgpack
import queue
import string
import threading
from contextlib import suppress
from datetime import datetime
from datetime import timezone
from typing import Callable

import RNS

from reticulum_telemetry_hub.api.rem_registry_service import RemRegistryService
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.config.manager_paths import _expand_user_path
from reticulum_telemetry_hub.lxmf_daemon.LXMF import display_name_from_app_data
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import decode_inbound_capability_payload
from reticulum_telemetry_hub.reticulum_server.runtime_constants import APP_NAME


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _resolve_interval(value: int | None, fallback: int) -> int:
    """Return the positive interval derived from CLI/config values."""

    if value is not None:
        return max(0, int(value))

    return max(0, int(fallback))


def _resolve_reticulum_config_dir(
    config_manager: HubConfigurationManager | None,
) -> str | None:
    """Return the Reticulum config directory inferred from manager settings."""

    if config_manager is None:
        return None

    config_path = getattr(config_manager, "reticulum_config_path", None)
    if config_path is None:
        return None

    resolved_path = _expand_user_path(config_path)
    if resolved_path.exists():
        target_dir = resolved_path if resolved_path.is_dir() else resolved_path.parent
        return str(target_dir)

    # For non-existing values, treat ".../config" as file path shorthand.
    if resolved_path.name.lower() == "config":
        return str(resolved_path.parent)

    return str(resolved_path)


def _build_reticulum_init_kwargs(
    *,
    loglevel: int,
    config_manager: HubConfigurationManager | None,
) -> dict[str, object]:
    """Build kwargs passed to ``RNS.Reticulum``."""

    kwargs: dict[str, object] = {"loglevel": loglevel}
    config_dir = _resolve_reticulum_config_dir(config_manager)
    if config_dir:
        kwargs["configdir"] = config_dir
    return kwargs


def _dispatch_coroutine(coroutine) -> None:
    """Execute ``coroutine`` on the active event loop or create one if needed.

    Args:
        coroutine: Awaitable object to schedule or run synchronously.
    """

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coroutine)
        return

    loop.create_task(coroutine)


class _AsyncTaskRunner:
    """Dedicated async-loop runner for scheduling hub coroutines safely."""

    def __init__(self, *, name: str) -> None:
        self._name = name
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._stopped = threading.Event()

    def start(self) -> None:
        """Start the runner thread and event loop once."""

        if self._thread is not None and self._thread.is_alive():
            return
        self._started.clear()
        self._stopped.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=self._name,
            daemon=True,
        )
        self._thread.start()
        self._started.wait(timeout=1.0)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._started.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                with suppress(Exception):
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            loop.close()
            self._stopped.set()

    def submit(self, coroutine) -> None:
        """Submit a coroutine to the runner loop when active."""

        if coroutine is None:
            return
        if self._loop is None or self._thread is None or not self._thread.is_alive():
            _dispatch_coroutine(coroutine)
            return
        try:
            asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        except Exception:
            _dispatch_coroutine(coroutine)

    def stop(self, *, timeout: float = 1.0) -> None:
        """Stop the runner loop and wait for thread exit."""

        loop = self._loop
        if loop is not None:
            with suppress(Exception):
                loop.call_soon_threadsafe(loop.stop)
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None
        self._loop = None


class AnnounceHandler:
    """Track simple metadata about peers announcing on the Reticulum bus."""

    _DEFAULT_PERSIST_QUEUE_SIZE = 1024
    _DROP_LOG_INTERVAL = 100

    def __init__(
        self,
        identities: dict[str, str],
        api: ReticulumTelemetryHubAPI | None = None,
        *,
        persist_queue_size: int = _DEFAULT_PERSIST_QUEUE_SIZE,
        capability_callback: Callable[[str, set[str]], None] | None = None,
        presence_callback: Callable[[str], None] | None = None,
        aspect_filter: str = APP_NAME,
        decode_display_name: bool = True,
    ):
        self.aspect_filter = aspect_filter
        self.identities = identities
        self._api = api
        self._capability_callback = capability_callback
        self._presence_callback = presence_callback
        self._decode_display_name_enabled = decode_display_name
        self._persist_queue: queue.Queue[
            tuple[str, str | None, str | None, str | None, list[str] | None]
        ] = queue.Queue(
            maxsize=max(1, int(persist_queue_size))
        )
        self._persist_stop_event = threading.Event()
        self._persist_worker: threading.Thread | None = None
        self._persist_worker_lock = threading.Lock()
        self._dropped_persist_count = 0

    def close(self, *, timeout: float = 2.0) -> None:
        """Stop the background persistence worker."""

        worker = self._persist_worker
        if worker is None:
            return
        self._persist_stop_event.set()
        worker.join(timeout=timeout)
        self._persist_worker = None

    def _ensure_persist_worker(self) -> None:
        """Start the background persistence worker once."""

        worker = self._persist_worker
        if worker is not None and worker.is_alive():
            return
        with self._persist_worker_lock:
            worker = self._persist_worker
            if worker is not None and worker.is_alive():
                return
            self._persist_stop_event.clear()
            self._persist_worker = threading.Thread(
                target=self._persist_worker_loop,
                daemon=True,
            )
            self._persist_worker.start()

    def _persist_worker_loop(self) -> None:
        """Persist announce metadata from the bounded queue."""

        while True:
            if self._persist_stop_event.is_set() and self._persist_queue.empty():
                return
            try:
                destination_hash, announced_identity_hash, display_name, source_interface, capabilities = self._persist_queue.get(
                    timeout=0.2
                )
            except queue.Empty:
                continue

            try:
                api = self._api
                if api is None:
                    continue
                api.record_identity_announce(
                    destination_hash,
                    announced_identity_hash=announced_identity_hash,
                    display_name=display_name,
                    source_interface=source_interface,
                    announce_capabilities=capabilities,
                )
            except Exception as exc:  # pragma: no cover - defensive log
                RNS.log(
                    f"Failed to persist announce metadata for {destination_hash}: {exc}",
                    getattr(RNS, "LOG_WARNING", 2),
                )
            finally:
                self._persist_queue.task_done()

    def received_announce(self, destination_hash, announced_identity, app_data):
        # RNS.log("\t+--- LXMF Announcement -----------------------------------------")
        # RNS.log(f"\t| Source hash            : {RNS.prettyhexrep(destination_hash)}")
        # RNS.log(f"\t| Announced identity     : {announced_identity}")
        # RNS.log(f"\t| App data               : {app_data}")
        # RNS.log("\t+---------------------------------------------------------------")
        label = self._decode_app_data(app_data) if self._decode_display_name_enabled else None
        capabilities = self._decode_capabilities(app_data)
        destination_key = self._normalize_hash(destination_hash)
        identity_key = self._normalize_hash(announced_identity)
        hash_keys = [key for key in (destination_key, identity_key) if key]
        if label:
            for key in hash_keys:
                self.identities[key] = label
        if capabilities:
            callback = self._capability_callback
            if callback is not None:
                for key in hash_keys:
                    callback(key, set(capabilities))
        presence_callback = self._presence_callback
        if presence_callback is not None:
            for key in hash_keys:
                presence_callback(key)
        if destination_key:
            self._persist_announce_async(
                destination_key,
                announced_identity_hash=identity_key,
                display_name=label,
                source_interface="destination",
                announce_capabilities=list(capabilities) if capabilities else None,
            )
        if identity_key and identity_key != destination_key:
            self._persist_announce_async(
                identity_key,
                announced_identity_hash=identity_key,
                display_name=label,
                source_interface="identity",
                announce_capabilities=list(capabilities) if capabilities else None,
            )

    @staticmethod
    def _normalize_hash(value) -> str | None:
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value).hex().lower()
        hash_value = getattr(value, "hash", None)
        if isinstance(hash_value, (bytes, bytearray, memoryview)):
            return bytes(hash_value).hex().lower()
        if isinstance(value, str):
            candidate = value.strip().lower()
            if candidate and all(ch in string.hexdigits for ch in candidate):
                return candidate
        return None

    @staticmethod
    def _decode_app_data(app_data) -> str | None:
        if app_data is None:
            return None

        if isinstance(app_data, (bytes, bytearray)):
            try:
                display_name = display_name_from_app_data(bytes(app_data))
            except Exception:
                display_name = None

            if display_name:
                display_name = display_name.strip()
                return display_name or None

        return None

    @staticmethod
    def _decode_capabilities(app_data) -> set[str]:
        if isinstance(app_data, str):
            return set(RemRegistryService.normalize_capabilities(app_data))
        if not isinstance(app_data, (bytes, bytearray, memoryview)):
            return set()

        raw_bytes = bytes(app_data)
        try:
            raw_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = ""
        if raw_text and any(separator in raw_text for separator in (",", ";", "|")):
            return set(RemRegistryService.normalize_capabilities(raw_text))

        try:
            decoded = msgpack.unpackb(raw_bytes, raw=False)
        except Exception:
            try:
                return set(
                    RemRegistryService.normalize_capabilities(
                        raw_bytes.decode("utf-8", errors="ignore")
                    )
                )
            except Exception:
                return set()

        if isinstance(decoded, str):
            return set(RemRegistryService.normalize_capabilities(decoded))
        if isinstance(decoded, (bytes, bytearray, memoryview)):
            return set(
                RemRegistryService.normalize_capabilities(
                    bytes(decoded).decode("utf-8", errors="ignore")
                )
            )
        if not isinstance(decoded, list) or len(decoded) < 3:
            return set()
        for slot in decoded[2:]:
            payload = decode_inbound_capability_payload(slot)
            if not isinstance(payload, dict):
                continue
            return set(RemRegistryService.normalize_capabilities(payload.get("caps")))
        return set()

    def _persist_announce_async(
        self,
        destination_hash: str,
        announced_identity_hash: str | None,
        display_name: str | None,
        *,
        source_interface: str | None = None,
        announce_capabilities: list[str] | None = None,
    ) -> None:
        """Persist announce metadata on a background thread.

        Args:
            destination_hash (str): Identity or destination hash to store.
            display_name (str | None): Optional announce display name.
            source_interface (str | None): Tag describing the announce hash type.
        """

        api = self._api
        if api is None:
            return
        self._ensure_persist_worker()

        try:
            self._persist_queue.put_nowait(
                (
                    destination_hash,
                    announced_identity_hash,
                    display_name,
                    source_interface,
                    list(announce_capabilities or []) or None,
                )
            )
        except queue.Full:
            self._dropped_persist_count += 1
            dropped_count = self._dropped_persist_count
            if dropped_count == 1 or dropped_count % self._DROP_LOG_INTERVAL == 0:
                RNS.log(
                    (
                        "Announce persistence queue is full; dropping metadata event "
                        f"#{dropped_count} for {destination_hash}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )


__all__ = [
    "AnnounceHandler",
    "_AsyncTaskRunner",
    "_build_reticulum_init_kwargs",
    "_dispatch_coroutine",
    "_resolve_interval",
    "_resolve_reticulum_config_dir",
    "_utcnow",
]


