"""ATAK Cursor on Target event container and serialization helpers."""

from __future__ import annotations

import gzip
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Union, cast

import msgpack

from reticulum_telemetry_hub.atak_cot.base import Point
from reticulum_telemetry_hub.atak_cot.detail import Detail

Packable = Union["Event", dict]


def _ensure_packable(obj: Packable) -> dict:
    """Return a dictionary representation regardless of input type."""

    if isinstance(obj, Event):
        return obj.to_dict()
    if isinstance(obj, dict):
        return obj
    raise TypeError(f"Unsupported packable type: {type(obj)!r}")


def pack_data(obj: Packable) -> bytes:
    """Return a compressed msgpack representation of ``obj`` or an Event."""

    packed = msgpack.packb(_ensure_packable(obj), use_bin_type=True)
    packed_bytes = cast(bytes, packed)
    return gzip.compress(packed_bytes)


def unpack_data(data: bytes) -> dict:
    """Inverse of :func:`pack_data` returning the original object."""

    return msgpack.unpackb(gzip.decompress(data), strict_map_key=False)


@dataclass
class Event:  # pylint: disable=too-many-instance-attributes
    """Top level CoT event object."""

    version: str
    uid: str
    type: str
    how: str
    time: str
    start: str
    stale: str
    point: Point
    access: str | None = None
    detail: Detail | None = None

    @classmethod
    def from_xml(cls, xml: Union[str, bytes]) -> "Event":
        """Parse an entire ``<event>`` XML string."""

        if isinstance(xml, bytes):
            xml = xml.decode("utf-8")
        return cls.from_element(ET.fromstring(xml))

    @classmethod
    def from_element(cls, root: ET.Element) -> "Event":
        """Construct an event from an ``<event>`` element."""

        point_el = root.find("point")
        detail_el = root.find("detail")
        point = (
            Point.from_xml(point_el) if point_el is not None else Point(0, 0, 0, 0, 0)
        )
        detail = Detail.from_xml(detail_el) if detail_el is not None else None
        return cls(
            version=root.get("version", ""),
            uid=root.get("uid", ""),
            type=root.get("type", ""),
            how=root.get("how", ""),
            time=root.get("time", ""),
            start=root.get("start", ""),
            stale=root.get("stale", ""),
            point=point,
            access=root.get("access"),
            detail=detail,
        )

    @classmethod
    def from_dict(cls, obj: dict) -> "Event":
        """Construct an :class:`Event` from a dictionary rooted at ``event``."""

        event_obj = obj.get("event") if isinstance(obj.get("event"), dict) else obj
        point = Point.from_dict(event_obj.get("point", {}))
        detail_obj = event_obj.get("detail")
        detail = Detail.from_dict(detail_obj) if detail_obj else None
        return cls(
            version=event_obj.get("version", ""),
            uid=event_obj.get("uid", ""),
            type=event_obj.get("type", ""),
            how=event_obj.get("how", ""),
            time=event_obj.get("time", ""),
            start=event_obj.get("start", ""),
            stale=event_obj.get("stale", ""),
            point=point,
            access=event_obj.get("access"),
            detail=detail,
        )

    @classmethod
    def from_json(cls, data: str) -> "Event":
        """Construct an Event from a JSON string."""

        return cls.from_dict(json.loads(data))

    def to_element(self) -> ET.Element:
        """Return an XML element representing the event."""

        attrib = {
            "version": self.version,
            "uid": self.uid,
            "type": self.type,
            "how": self.how,
            "time": self.time,
            "start": self.start,
            "stale": self.stale,
        }
        if self.access:
            attrib["access"] = self.access
        event_el = ET.Element("event", attrib)
        event_el.append(self.point.to_element())
        detail_el = self.detail.to_element() if self.detail else None
        if detail_el is not None:
            event_el.append(detail_el)
        return event_el

    def to_xml(self) -> str:
        """Return a Unicode XML string representing the event."""

        return ET.tostring(self.to_element(), encoding="unicode")

    def to_xml_bytes(self) -> bytes:
        """Return UTF-8 encoded XML bytes representing the event."""

        return ET.tostring(self.to_element())

    def to_dict(self) -> dict:
        """Return a dictionary representation of the event with an ``event`` root."""

        event_data = {
            "version": self.version,
            "uid": self.uid,
            "type": self.type,
            "how": self.how,
            "time": self.time,
            "start": self.start,
            "stale": self.stale,
            "point": self.point.to_dict(),
        }
        if self.access:
            event_data["access"] = self.access
        if self.detail:
            event_data["detail"] = self.detail.to_dict()
        return {"event": event_data}

    def to_json(self) -> str:
        """Return a JSON representation of the event."""

        return json.dumps(self.to_dict())

    def to_datapack(self) -> bytes:
        """Return a compressed datapack representation of the event."""

        return pack_data(self)

    @classmethod
    def from_datapack(cls, data: bytes) -> "Event":
        """Recreate an :class:`Event` instance from datapack bytes."""

        unpacked = unpack_data(data)
        return cls.from_dict(unpacked)
