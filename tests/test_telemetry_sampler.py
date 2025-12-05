import time

import RNS

from reticulum_telemetry_hub.lxmf_telemetry.sampler import (
    TelemetrySample,
    TelemetrySampler,
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
