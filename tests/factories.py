"""Test helpers for constructing representative telemetry sensors and payloads."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Dict
from typing import Optional

from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_CONNECTION_MAP,
    SID_LXMF_PROPAGATION,
    SID_RNS_TRANSPORT,
    SID_TIME,
)

from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.connection_map import (
    ConnectionMap,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.lxmf_propagation import (
    LXMFPropagation,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.rns_transport import (
    RNSTransport,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.location import (
    Location,
)


PEER_HASH_A = b"\xaa" * 16
PEER_HASH_B = b"\xbb" * 16


def create_rns_transport_sensor() -> RNSTransport:
    """Return an ``RNSTransport`` populated with nested Sideband payload data."""

    sensor = RNSTransport()
    sensor.unpack(
        {
            "transport_enabled": True,
            "transport_identity": b"\x01" * 16,
            "transport_uptime": 4242,
            "traffic_rxb": 10_000,
            "traffic_txb": 20_000,
            "speed_rx": 128.5,
            "speed_tx": 256.75,
            "speed_rx_inst": 130.0,
            "speed_tx_inst": 260.0,
            "memory_used": 12_345_678,
            "interface_count": 2,
            "link_count": 7,
            "interfaces": [
                {"name": "if0", "state": "up"},
                {"name": "if1", "state": "down"},
            ],
            "path_table": [
                {
                    "interface": "if0",
                    "via": b"\xaa" * 8,
                    "hash": b"\xbb" * 16,
                    "hops": 1,
                }
            ],
            "ifstats": {
                "rxb": 10_000,
                "txb": 20_000,
                "rxs": 500.0,
                "txs": 600.0,
                "interfaces": [
                    {"name": "if0", "paths": 2},
                    {"name": "if1", "paths": 0},
                ],
            },
            "custom_metric": 99.9,
        }
    )
    return sensor


def create_lxmf_propagation_sensor() -> LXMFPropagation:
    """Return an ``LXMFPropagation`` sensor with multiple peers and aggregates."""

    sensor = LXMFPropagation()
    sensor.unpack(
        {
            "destination_hash": b"\x10" * 16,
            "identity_hash": b"\x20" * 16,
            "uptime": 12_345,
            "delivery_limit": 42.5,
            "propagation_limit": 256.0,
            "autopeer_maxdepth": 3,
            "from_static_only": True,
            "messagestore": {"count": 5, "bytes": 4096, "limit": 8192},
            "clients": {
                "client_propagation_messages_received": 7,
                "client_propagation_messages_served": 9,
            },
            "unpeered_propagation_incoming": 2,
            "unpeered_propagation_rx_bytes": 1_024,
            "static_peers": 1,
            "max_peers": 10,
            "peers": {
                PEER_HASH_A: {
                    "type": "propagator",
                    "state": "active",
                    "alive": True,
                    "last_heard": 1_234.5,
                    "next_sync_attempt": 2_345.6,
                    "last_sync_attempt": 1_111.0,
                    "sync_backoff": 10.0,
                    "peering_timebase": 42.0,
                    "ler": 0.75,
                    "str": 0.5,
                    "transfer_limit": 512,
                    "network_distance": 2,
                    "rx_bytes": 2_048,
                    "tx_bytes": 4_096,
                    "messages": {
                        "offered": 3,
                        "outgoing": 2,
                        "incoming": 1,
                        "unhandled": 0,
                    },
                },
                PEER_HASH_B: {
                    "type": "propagator",
                    "state": "down",
                    "alive": False,
                    "last_heard": 3_210.1,
                    "next_sync_attempt": None,
                    "last_sync_attempt": 2_222.0,
                    "sync_backoff": 20.0,
                    "peering_timebase": 84.0,
                    "ler": 0.55,
                    "str": 0.25,
                    "transfer_limit": 256,
                    "network_distance": 4,
                    "rx_bytes": 512,
                    "tx_bytes": 256,
                    "messages": {
                        "offered": 1,
                        "outgoing": 0,
                        "incoming": 0,
                        "unhandled": 1,
                    },
                },
            },
        }
    )
    sensor.unpeered_incoming = 2
    sensor.unpeered_rx_bytes = 1_024
    sensor.static_peers = 1
    sensor.max_peers = 10
    return sensor


def create_connection_map_sensor() -> ConnectionMap:
    """Return a ``ConnectionMap`` with multiple maps and signal updates."""

    sensor = ConnectionMap()
    sensor.ensure_map("main", "Main Map")
    sensor.add_point(
        "main",
        "deadbeef",
        latitude=44.0,
        longitude=-63.0,
        altitude=10.0,
        point_type="peer",
        name="Gateway",
        signal_strength=-42,
        snr=12.5,
    )
    sensor.add_point("main", "deadbeef", signal_strength=-40)

    sensor.ensure_map("backup", "Backup Map")
    sensor.add_point(
        "backup",
        "feedface",
        latitude=45.0,
        longitude=-62.0,
        altitude=12.0,
        point_type="peer",
        name="Repeater",
        signal_strength=-55,
        snr=10.0,
    )
    return sensor


def create_location_sensor(timestamp: Optional[int] = None) -> Location:
    """Return a ``Location`` sensor with deterministic values."""

    sensor = Location()
    sensor.latitude = 44.0
    sensor.longitude = -63.0
    sensor.altitude = 10.0
    sensor.speed = 0.0
    sensor.bearing = 0.0
    sensor.accuracy = 5.0
    sensor.last_update = datetime.fromtimestamp(
        timestamp or 1_700_000_000, timezone.utc
    )
    return sensor


def build_location_payload(timestamp: Optional[int] = None) -> list | None:
    sensor = create_location_sensor(timestamp)
    return sensor.pack()


def build_complex_telemeter_payload(
    *, timestamp: int | None = None
) -> Dict[int, object]:
    """Return a telemetry payload covering complex/nested sensors."""

    sensors = [
        create_location_sensor(timestamp),
        create_rns_transport_sensor(),
        create_lxmf_propagation_sensor(),
        create_connection_map_sensor(),
    ]
    payload: Dict[int, dict] = {}
    for sensor in sensors:
        packed = sensor.pack()
        if packed is not None:
            payload[sensor.sid] = packed
    if timestamp is not None:
        payload[SID_TIME] = int(timestamp)
    return payload


def build_rns_transport_payload() -> dict:
    return create_rns_transport_sensor().pack() or {}


def build_lxmf_propagation_payload() -> dict:
    return create_lxmf_propagation_sensor().pack() or {}


def build_connection_map_payload() -> dict:
    return create_connection_map_sensor().pack() or {}


def complex_sensor_sids() -> tuple[int, int, int]:
    return SID_RNS_TRANSPORT, SID_LXMF_PROPAGATION, SID_CONNECTION_MAP
