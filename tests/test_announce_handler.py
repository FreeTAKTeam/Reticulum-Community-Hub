"""Tests for AnnounceHandler metadata decoding."""

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
