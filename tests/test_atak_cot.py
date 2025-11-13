import json
from reticulum_telemetry_hub.atak_cot import Event, pack_data, unpack_data

COT_XML = """
<event version="2.0" uid="android-001" type="b-m-f" how="m-g" time="2024-01-01T00:00:00Z" start="2024-01-01T00:00:00Z" stale="2024-01-01T01:00:00Z">
  <point lat="34.0" lon="-117.0" hae="0" ce="50" le="50" />
  <detail>
    <contact callsign="TestMarker" />
    <__group name="Blue" role="Team" />
    <remarks>Example marker</remarks>
  </detail>
</event>
"""

def test_roundtrip_datapack():
    event = Event.from_xml(COT_XML)
    packed = event.to_datapack()
    restored = Event.from_datapack(packed)
    assert restored.uid == event.uid
    assert restored.point.lat == event.point.lat
    assert restored.detail.contact.callsign == "TestMarker"


def test_json_roundtrip():
    event = Event.from_xml(COT_XML)
    json_data = json.dumps(event.to_dict())
    restored = Event.from_json(json_data)
    assert restored.uid == event.uid
    assert restored.detail.group.name == "Blue"


def test_pack_data_accepts_event_instances():
    event = Event.from_xml(COT_XML)
    packed = pack_data(event)
    decoded = unpack_data(packed)
    restored = Event.from_dict(decoded)
    assert restored.uid == event.uid
    assert restored.point.lon == event.point.lon


def test_xml_roundtrip_bytes():
    event = Event.from_xml(COT_XML)
    event.detail.remarks = "Updated"
    xml_bytes = event.to_xml_bytes()
    restored = Event.from_xml(xml_bytes)
    assert restored.detail.remarks == "Updated"
