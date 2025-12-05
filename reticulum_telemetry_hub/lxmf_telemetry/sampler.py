"""Telemetry sampling helpers."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol, Sequence

import LXMF
import RNS
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_TIME,
)
from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import TelemeterManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)


class TelemetryCollector(Protocol):
    """Protocol describing callables that return telemetry payloads."""

    def __call__(self) -> "TelemetrySample | dict | None": ...


@dataclass
class TelemetrySample:
    """Container describing telemetry payloads gathered by the sampler."""

    payload: dict
    peer_dest: str | None = None


@dataclass
class _SamplerJob:
    name: str
    interval: float
    collectors: Sequence[TelemetryCollector | Callable[[], object]]
    last_run: float = field(default_factory=time.monotonic)


class TelemetrySampler:
    """Background worker that periodically emits telemetry snapshots."""

    def __init__(
        self,
        controller: TelemetryController,
        router: LXMF.LXMRouter,
        source_destination: RNS.Destination,
        *,
        connections: dict[bytes, RNS.Destination] | None = None,
        hub_interval: float | None = None,
        service_interval: float | None = None,
        hub_collectors: (
            Sequence[TelemetryCollector | Callable[[], object]] | None
        ) = None,
        service_collectors: (
            Sequence[TelemetryCollector | Callable[[], object]] | None
        ) = None,
        telemeter_manager: TelemeterManager | None = None,
        broadcast_updates: bool = False,
    ) -> None:
        self._controller = controller
        self._router = router
        self._source_destination = source_destination
        self._connections = connections if connections is not None else {}
        self._broadcast_updates = broadcast_updates
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._jobs: list[_SamplerJob] = []
        self._local_peer_dest = (
            RNS.hexrep(source_destination.hash, False)
            if hasattr(source_destination, "hash")
            else ""
        )

        self._telemeter_manager = telemeter_manager

        if hub_interval is not None and hub_interval > 0:
            collectors = list(hub_collectors) if hub_collectors is not None else []
            if not collectors:
                collectors = [self._collect_telemeter_snapshot]
            if collectors:
                interval = float(hub_interval)
                self._jobs.append(
                    _SamplerJob(
                        "hub",
                        interval,
                        collectors,
                        time.monotonic() - interval,
                    )
                )

        if service_interval is not None and service_interval > 0:
            collectors = (
                list(service_collectors) if service_collectors is not None else []
            )
            if collectors:
                interval = float(service_interval)
                self._jobs.append(
                    _SamplerJob(
                        "service",
                        interval,
                        collectors,
                        time.monotonic() - interval,
                    )
                )

    # ------------------------------------------------------------------
    # lifecycle helpers
    # ------------------------------------------------------------------
    def start(self) -> None:
        if not self._jobs or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join()
        self._thread = None
        self._stop_event.clear()

    # ------------------------------------------------------------------
    # sampler internals
    # ------------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop_event.is_set():
            now = time.monotonic()
            next_wake = None
            for job in self._jobs:
                remaining = job.interval - (now - job.last_run)
                if remaining <= 0:
                    self._execute_job(job)
                    job.last_run = time.monotonic()
                    remaining = job.interval
                next_wake = (
                    remaining if next_wake is None else min(next_wake, remaining)
                )
            if next_wake is None:
                break
            self._stop_event.wait(next_wake)

    def _execute_job(self, job: _SamplerJob) -> None:
        for collector in job.collectors:
            sample = self._invoke_collector(collector)
            if sample is None:
                continue
            self._process_sample(sample)

    def _invoke_collector(
        self, collector: TelemetryCollector | Callable[[], object]
    ) -> TelemetrySample | None:
        try:
            result = collector()
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(f"Telemetry collector {collector!r} failed: {exc}", RNS.LOG_ERROR)
            return None

        if result is None:
            return None

        if isinstance(result, TelemetrySample):
            return result

        if isinstance(result, dict):
            return TelemetrySample(result)

        raise TypeError(
            "Telemetry collectors must return a dict or TelemetrySample; "
            f"received {type(result)!r}"
        )

    def _process_sample(self, sample: TelemetrySample) -> None:
        peer_dest = sample.peer_dest or self._local_peer_dest
        encoded = self._controller.ingest_local_payload(
            sample.payload, peer_dest=peer_dest
        )
        if not encoded:
            return

        if not self._broadcast_updates:
            return

        destinations: Sequence[RNS.Destination]
        if hasattr(self._connections, "values"):
            destinations = list(self._connections.values())
        else:
            destinations = list(self._connections)

        if not destinations:
            return

        for destination in destinations:
            try:
                message = LXMF.LXMessage(
                    destination,
                    self._source_destination,
                    fields={LXMF.FIELD_TELEMETRY: encoded},
                    desired_method=LXMF.LXMessage.DIRECT,
                )
                if hasattr(destination, "identity") and hasattr(
                    destination.identity, "hash"
                ):
                    message.destination_hash = destination.identity.hash
                self._router.handle_outbound(message)
            except Exception as exc:  # pragma: no cover - defensive logging
                RNS.log(
                    f"Failed to deliver telemetry sample to {destination}: {exc}",
                    RNS.LOG_ERROR,
                )

    # ------------------------------------------------------------------
    # built-in collectors
    # ------------------------------------------------------------------
    def _collect_time_sensor(self) -> TelemetrySample:
        payload = {SID_TIME: time.time()}
        return TelemetrySample(payload, self._local_peer_dest)

    def _collect_telemeter_snapshot(self) -> TelemetrySample:
        if self._telemeter_manager is None:
            return self._collect_time_sensor()
        payload = self._telemeter_manager.snapshot()
        if SID_TIME not in payload:
            payload[SID_TIME] = time.time()
        return TelemetrySample(payload, self._local_peer_dest)
