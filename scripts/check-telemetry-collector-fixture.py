#!/usr/bin/env python3
"""Independently check the issue #260 wire fixture with Python MessagePack.

This verifies the client-facing list/binary/numeric-sensor structure, not a live
Columba or Sideband session. Requires the already installed msgpack package.
"""
import base64
import json
from pathlib import Path
import struct

import msgpack

fixture_path = Path(__file__).resolve().parents[1] / "crates/r3akt-transport-rns/tests/fixtures/collector_stream.json"
fixture = json.loads(fixture_path.read_text())
for key, topic, unavailable in [
    ("global_fields_b64", None, 0),
    ("topic_fields_b64", "ops", 0),
    ("unavailable_fields_b64", None, 1),
]:
    fields = msgpack.unpackb(base64.b64decode(fixture[key]), strict_map_key=False)
    stream = fields[3]
    assert isinstance(stream, list), "field 3 must be a plain list, not packed again"
    event = fields[13]
    assert event["entry_count"] == len(stream)
    assert event["topic_id"] == topic
    assert event["unavailable_records"] == unavailable
    if unavailable:
        assert stream == []
        continue
    assert len(stream) == 1
    peer, timestamp, packed, appearance = stream[0]
    assert isinstance(peer, bytes) and len(peer) == 16
    assert peer.hex() == fixture["peer"]
    assert timestamp == fixture["timestamp"]
    assert isinstance(packed, bytes)
    assert packed == base64.b64decode(fixture["packed_telemeter_b64"])
    assert appearance is None
    telemeter = msgpack.unpackb(packed, strict_map_key=False)
    assert telemeter[1] == timestamp
    location = telemeter[2]
    assert struct.unpack(">i", location[0])[0] / 1_000_000 == 44.0
    assert struct.unpack(">i", location[1])[0] / 1_000_000 == -63.0
print("Collector fixtures: plain streams, binary entries and packed sensor maps verified")
