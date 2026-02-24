"""Tests for AnnounceHandler metadata decoding."""

import time

import RNS.vendor.umsgpack as msgpack

from reticulum_telemetry_hub.reticulum_server.__main__ import (
    AnnounceHandler,
    ReticulumTelemetryHub,
)


def test_announce_handler_decodes_display_name_from_msgpack():
    identities: dict[str, str] = {}
    handler = AnnounceHandler(identities)
    announce_data = msgpack.packb([b"Name", 1])

    handler.received_announce(
        b"\x01\x02",
        announced_identity="peer",
        app_data=announce_data,
    )

    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    hub.identities = identities

    assert hub._lookup_identity_label(b"\x01\x02") == "Name"


def test_announce_handler_persist_queue_is_non_blocking_when_full():
    """Drop overflow announce metadata instead of blocking announce handling."""

    class SlowAPI:
        def __init__(self) -> None:
            self.persisted: list[str] = []

        def record_identity_announce(self, destination_hash: str, **_kwargs) -> None:
            time.sleep(0.02)
            self.persisted.append(destination_hash)

    api = SlowAPI()
    handler = AnnounceHandler({}, api=api, persist_queue_size=1)

    started = time.monotonic()
    for _ in range(200):
        handler._persist_announce_async("aabb", "Name", source_interface="destination")
    elapsed = time.monotonic() - started

    time.sleep(0.1)
    handler.close()

    assert elapsed < 0.2
    assert handler._dropped_persist_count > 0
    assert api.persisted


def test_announce_handler_extracts_capabilities_from_app_data() -> None:
    captured: list[tuple[str, set[str]]] = []
    handler = AnnounceHandler(
        {},
        capability_callback=lambda identity, caps: captured.append((identity, set(caps))),
    )
    capability_payload = msgpack.packb(
        {"app": "rch", "schema": 1, "caps": ["R3AKT", "telemetry_relay"]},
        use_bin_type=True,
    )
    announce_data = msgpack.packb([b"Name", 1, capability_payload], use_bin_type=True)

    handler.received_announce(
        b"\x01\x02",
        announced_identity=b"\x0a\x0b",
        app_data=announce_data,
    )

    assert captured
    flattened_caps = {cap for _, caps in captured for cap in caps}
    assert "r3akt" in flattened_caps
