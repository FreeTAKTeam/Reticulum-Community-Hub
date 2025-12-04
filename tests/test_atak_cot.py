import json

import pytest

from reticulum_telemetry_hub.atak_cot import Chat
from reticulum_telemetry_hub.atak_cot import ChatGroup
from reticulum_telemetry_hub.atak_cot import ChatHierarchy
from reticulum_telemetry_hub.atak_cot import ChatHierarchyContact
from reticulum_telemetry_hub.atak_cot import ChatHierarchyGroup
from reticulum_telemetry_hub.atak_cot import Detail
from reticulum_telemetry_hub.atak_cot import Event
from reticulum_telemetry_hub.atak_cot import Link
from reticulum_telemetry_hub.atak_cot import Point
from reticulum_telemetry_hub.atak_cot import Remarks
from reticulum_telemetry_hub.atak_cot import pack_data, unpack_data

COT_XML = """
<event version="2.0" uid="android-001" type="b-m-f" how="m-g"
  time="2024-01-01T00:00:00Z" start="2024-01-01T00:00:00Z"
  stale="2024-01-01T01:00:00Z">
  <point lat="34.0" lon="-117.0" hae="0" ce="50" le="50" />
  <detail>
    <contact callsign="TestMarker" />
    <__group name="Blue" role="Team" />
    <track course="90.0" speed="12.5" />
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
    assert restored.detail.track is not None
    assert restored.detail.track.speed == pytest.approx(12.5)


def test_json_roundtrip():
    event = Event.from_xml(COT_XML)
    event_dict = event.to_dict()
    assert "event" in event_dict
    json_data = json.dumps(event_dict)
    restored = Event.from_json(json_data)
    assert restored.uid == event.uid
    assert restored.detail.group.name == "Blue"
    assert restored.detail.track is not None
    assert restored.detail.track.course == pytest.approx(90.0)


def test_from_dict_accepts_legacy_payload():
    event = Event.from_xml(COT_XML)
    legacy_payload = event.to_dict()["event"]

    restored = Event.from_dict(legacy_payload)

    assert restored.uid == event.uid
    assert restored.type == event.type
    assert restored.point.lat == event.point.lat
    assert restored.detail.contact.callsign == "TestMarker"


def test_pack_data_accepts_event_instances():
    event = Event.from_xml(COT_XML)
    packed = pack_data(event)
    decoded = unpack_data(packed)
    restored = Event.from_dict(decoded)
    assert restored.uid == event.uid
    assert restored.point.lon == event.point.lon
    assert restored.detail.track is not None
    assert restored.detail.track.speed == pytest.approx(12.5)


def test_xml_roundtrip_bytes():
    event = Event.from_xml(COT_XML)
    event.detail.remarks = "Updated"
    xml_bytes = event.to_xml_bytes()
    restored = Event.from_xml(xml_bytes)
    assert restored.detail.remarks == "Updated"
    assert restored.detail.track is not None


def test_geochat_detail_roundtrip():
    detail = Detail(
        chat=Chat(
            id="ops",
            chatroom="ops",
            sender_callsign="Alpha",
            group_owner="false",
            chat_group=ChatGroup(
                chatroom="ops",
                chat_id="ops",
                uid0="0101010101010101",
                uid1="",
                uid2="user2",
            ),
            hierarchy=ChatHierarchy(
                groups=[
                    ChatHierarchyGroup(
                        uid="TeamGroups",
                        name="Teams",
                        groups=[
                            ChatHierarchyGroup(
                                uid="ops",
                                name="ops",
                                contacts=[
                                    ChatHierarchyContact(
                                        uid="0101010101010101", name="Alpha"
                                    )
                                ],
                            )
                        ],
                    )
                ]
            ),
        ),
        links=[
            Link(
                uid="0101010101010101",
                type="a-f-G-U-C-I",
                relation="p-p",
            )
        ],
        remarks=Remarks(
            text="[topic:ops] Hello team",
            source="BAO.F.Alpha.0101010101010101",
            source_id="0101010101010101",
            to="ops",
            time="2025-01-02T03:04:05Z",
        ),
    )
    event = Event(
        version="2.0",
        uid="GeoChat.0101010101010101",
        type="b-t-f",
        how="h-g-i-g-o",
        time="2025-01-02T03:04:06Z",
        start="2025-01-02T03:04:05Z",
        stale="2025-01-02T03:05:06Z",
        point=Point(lat=0.0, lon=0.0, hae=0.0, ce=0.0, le=0.0),
        detail=detail,
    )

    xml_data = event.to_xml()
    restored = Event.from_xml(xml_data)

    assert restored.detail is not None
    assert restored.detail.chat is not None
    assert restored.detail.chat.id == "ops"
    assert restored.detail.chat.chat_group is not None
    assert restored.detail.chat.chat_group.chatroom == "ops"
    assert restored.detail.chat.hierarchy is not None
    assert restored.detail.chat.hierarchy.groups[0].uid == "TeamGroups"
    assert restored.detail.links
    assert restored.detail.links[0].uid == "0101010101010101"
    assert restored.detail.links[0].type == "a-f-G-U-C-I"
    assert isinstance(restored.detail.remarks, Remarks)
    assert restored.detail.remarks.source_id == "0101010101010101"
