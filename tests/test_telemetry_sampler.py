import time

import LXMF
import RNS
from msgpack import unpackb

from reticulum_telemetry_hub.lxmf_telemetry.sampler import (
    TelemetrySample,
    TelemetrySampler,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_TIME,
)


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
    )

    sampler.start()
    time.sleep(0.05)
    sampler.stop()

    assert samples
    assert router.messages

    message = router.messages[-1]
    assert LXMF.FIELD_TELEMETRY in message.fields
    decoded = unpackb(message.fields[LXMF.FIELD_TELEMETRY], strict_map_key=False)
    assert SID_TIME in decoded

    stored = telemetry_controller.get_telemetry()
    assert stored


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
    )

    sampler.start()
    time.sleep(0.12)
    sampler.stop()

    assert len(hub_calls) > len(service_calls)
    assert service_calls
    assert router.messages
