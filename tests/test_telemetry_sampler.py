import time

import pytest
import RNS

from reticulum_telemetry_hub.lxmf_telemetry.sampler import (
    TelemetrySample,
    TelemetrySampler,
    _SamplerJob,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_TIME,
)
from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import TelemeterManager


class DummyRouter:
    def __init__(self):
        self.messages = []

    def handle_outbound(self, message):  # pragma: no cover - interface shim
        self.messages.append(message)


class DummyConnections(dict):
    """Mutable mapping storing destinations by hash."""


def _destination() -> RNS.Destination:
    identity = RNS.Identity()
    return RNS.Destination(
        identity,
        RNS.Destination.OUT,
        RNS.Destination.SINGLE,
        "lxmf",
        "delivery",
    )


def test_sampler_publishes_snapshots(telemetry_controller):
    router = DummyRouter()
    server_dest = _destination()
    client_dest = _destination()
    connections = DummyConnections({client_dest.identity.hash: client_dest})
    manager = TelemeterManager()

    samples = []

    def collector():
        payload = {SID_TIME: int(time.time())}
        samples.append(payload)
        return payload

    sampler = TelemetrySampler(
        telemetry_controller,
        router,
        server_dest,
        connections=connections,
        hub_interval=0.01,
        hub_collectors=[collector],
        telemeter_manager=manager,
    )

    sampler.start()
    time.sleep(0.05)
    sampler.stop()

    assert samples
    assert not router.messages
    stored = telemetry_controller.get_telemetry()
    assert stored


def test_sampler_can_broadcast_when_enabled(telemetry_controller):
    router = DummyRouter()
    server_dest = _destination()
    client_dest = _destination()
    connections = DummyConnections({client_dest.identity.hash: client_dest})
    manager = TelemeterManager()

    def collector():
        payload = {SID_TIME: int(time.time())}
        return payload

    sampler = TelemetrySampler(
        telemetry_controller,
        router,
        server_dest,
        connections=connections,
        hub_interval=0.01,
        hub_collectors=[collector],
        telemeter_manager=manager,
        broadcast_updates=True,
    )

    sampler.start()
    time.sleep(0.05)
    sampler.stop()

    assert router.messages
    assert not router.messages[0].content


def test_sampler_schedules_service_collectors_independently(telemetry_controller):
    router = DummyRouter()
    server_dest = _destination()
    client_dest = _destination()
    connections = DummyConnections({client_dest.identity.hash: client_dest})

    hub_calls = []
    service_calls = []

    def hub_collector():
        hub_calls.append(time.time())
        return {SID_TIME: time.time()}

    def service_collector():
        service_calls.append(time.time())
        return TelemetrySample({SID_TIME: time.time()}, "service-node")

    sampler = TelemetrySampler(
        telemetry_controller,
        router,
        server_dest,
        connections=connections,
        hub_interval=0.01,
        service_interval=0.05,
        hub_collectors=[hub_collector],
        service_collectors=[service_collector],
        telemeter_manager=TelemeterManager(),
    )

    sampler.start()
    time.sleep(0.12)
    sampler.stop()

    assert len(hub_calls) > len(service_calls)
    assert service_calls
    assert not router.messages


def test_sampler_uses_telemeter_manager_snapshot(telemetry_controller):
    router = DummyRouter()
    server_dest = _destination()
    client_dest = _destination()
    connections = DummyConnections({client_dest.identity.hash: client_dest})
    manager = TelemeterManager()

    sampler = TelemetrySampler(
        telemetry_controller,
        router,
        server_dest,
        connections=connections,
        hub_interval=0.01,
        telemeter_manager=manager,
    )

    sampler.start()
    time.sleep(0.05)
    sampler.stop()

    assert not router.messages
    stored = telemetry_controller.get_telemetry()
    assert stored
    sensor_ids = {sensor.sid for sensor in stored[-1].sensors}
    assert SID_TIME in sensor_ids


def test_sampler_handles_no_jobs_and_safe_stop(telemetry_controller):
    router = DummyRouter()
    server_dest = _destination()
    sampler = TelemetrySampler(telemetry_controller, router, server_dest)

    sampler.start()
    sampler._run()  # run loop exits immediately when no jobs are scheduled
    sampler.stop()

    assert sampler._thread is None


def test_sampler_stop_is_idempotent(telemetry_controller):
    router = DummyRouter()
    server_dest = _destination()
    sampler = TelemetrySampler(telemetry_controller, router, server_dest)

    sampler.stop()


def test_invoke_collector_enforces_return_type(telemetry_controller):
    router = DummyRouter()
    server_dest = _destination()
    sampler = TelemetrySampler(telemetry_controller, router, server_dest)

    with pytest.raises(TypeError):
        sampler._invoke_collector(lambda: "not-a-sample")


def test_execute_job_skips_none_samples(telemetry_controller):
    router = DummyRouter()
    server_dest = _destination()
    sampler = TelemetrySampler(telemetry_controller, router, server_dest)

    job = _SamplerJob(name="noop", interval=0, collectors=[lambda: None])

    sampler._execute_job(job)


def test_process_sample_exits_on_missing_encoding():
    class NullController:
        def ingest_local_payload(self, payload, peer_dest):
            self.last_payload = payload
            self.last_peer = peer_dest
            return None

    router = DummyRouter()
    server_dest = _destination()
    controller = NullController()
    sampler = TelemetrySampler(controller, router, server_dest)

    sampler._process_sample(TelemetrySample(payload={"foo": "bar"}))

    assert not router.messages


def test_process_sample_handles_empty_destinations_with_broadcast_enabled():
    class Controller:
        def ingest_local_payload(self, payload, peer_dest):
            self.calls = getattr(self, "calls", [])
            self.calls.append((payload, peer_dest))
            return b"encoded"

    router = DummyRouter()
    server_dest = _destination()
    controller = Controller()
    sampler = TelemetrySampler(
        controller, router, server_dest, connections=[], broadcast_updates=True
    )

    sampler._process_sample(TelemetrySample(payload={"one": 1}))

    assert controller.calls
    assert not router.messages


def test_telemeter_snapshot_collectors_include_timestamp(monkeypatch, telemetry_controller):
    router = DummyRouter()
    server_dest = _destination()
    manager = type("Manager", (), {"snapshot": lambda self: {}})()
    sampler = TelemetrySampler(
        telemetry_controller,
        router,
        server_dest,
        telemeter_manager=manager,
    )
    monkeypatch.setattr("time.time", lambda: 1700000000.0)

    sample = sampler._collect_telemeter_snapshot()

    assert sample.payload[SID_TIME] == 1700000000.0
    assert sample.peer_dest == RNS.hexrep(server_dest.hash, False)
