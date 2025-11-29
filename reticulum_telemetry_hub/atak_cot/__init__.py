"""ATAK COT support classes and datapack utilities.

This module provides a very small subset of the `Cursor on Target`_ (CoT)
schema used by ATAK. It is intentionally lightweight and only implements
the elements required by the accompanying tests. The objects can be
created from XML strings, converted back into dictionaries and packed into
a compressed "datapack" format for transport.

.. _Cursor on Target: https://github.com/FreeTAKTeam/FreeTAKTest
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union, cast
import json
import xml.etree.ElementTree as ET
import gzip
import msgpack


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
class Point:
    """A geographic point element."""

    lat: float
    lon: float
    hae: float
    ce: float
    le: float

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Point":
        """Create a :class:`Point` from an XML ``<point>`` element."""
        return cls(
            lat=float(elem.get("lat", 0)),
            lon=float(elem.get("lon", 0)),
            hae=float(elem.get("hae", 0)),
            ce=float(elem.get("ce", 0)),
            le=float(elem.get("le", 0)),
        )

    def to_element(self) -> ET.Element:
        """Return an XML element representing this point."""
        attrib = {
            "lat": str(self.lat),
            "lon": str(self.lon),
            "hae": str(self.hae),
            "ce": str(self.ce),
            "le": str(self.le),
        }
        return ET.Element("point", attrib)

    def to_dict(self) -> dict:
        """Return a serialisable dictionary representation."""
        return {
            "lat": self.lat,
            "lon": self.lon,
            "hae": self.hae,
            "ce": self.ce,
            "le": self.le,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Point":
        """Create a :class:`Point` from a dictionary."""
        return cls(
            lat=float(data.get("lat", 0)),
            lon=float(data.get("lon", 0)),
            hae=float(data.get("hae", 0)),
            ce=float(data.get("ce", 0)),
            le=float(data.get("le", 0)),
        )


@dataclass
class Contact:
    """Identifies the sender of the COT message."""

    callsign: str

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Contact":
        """Construct a :class:`Contact` from an XML ``<contact>`` element."""
        return cls(callsign=elem.get("callsign", ""))

    def to_element(self) -> ET.Element:
        """Return an XML element for the contact."""
        return ET.Element("contact", {"callsign": self.callsign})

    def to_dict(self) -> dict:
        """Return a serialisable representation."""
        return {"callsign": self.callsign}

    @classmethod
    def from_dict(cls, data: dict) -> "Contact":
        """Create a :class:`Contact` from a dictionary."""
        return cls(callsign=data.get("callsign", ""))


@dataclass
class Group:
    """Represents a group affiliation."""

    name: str
    role: str

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Group":
        """Parse an XML ``<__group>`` element into a :class:`Group`."""
        return cls(name=elem.get("name", ""), role=elem.get("role", ""))

    def to_element(self) -> ET.Element:
        """Return an XML element for the group affiliation."""
        return ET.Element("__group", {"name": self.name, "role": self.role})

    def to_dict(self) -> dict:
        """Return a serialisable representation."""
        return {"name": self.name, "role": self.role}

    @classmethod
    def from_dict(cls, data: dict) -> "Group":
        """Create a :class:`Group` from a dictionary."""
        return cls(name=data.get("name", ""), role=data.get("role", ""))


@dataclass
class Track:
    """Represents movement information such as speed and bearing."""

    course: float
    speed: float

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Track":
        """Parse an XML ``<track>`` element into a :class:`Track`."""

        return cls(
            course=float(elem.get("course", 0)),
            speed=float(elem.get("speed", 0)),
        )

    def to_element(self) -> ET.Element:
        """Return an XML element for the movement details."""

        return ET.Element(
            "track", {"course": str(self.course), "speed": str(self.speed)}
        )

    def to_dict(self) -> dict:
        """Return a serialisable representation."""

        return {"course": self.course, "speed": self.speed}

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        """Create a :class:`Track` from a dictionary."""

        return cls(
            course=float(data.get("course", 0)),
            speed=float(data.get("speed", 0)),
        )


@dataclass
class Detail:
    """Additional information such as contact, group, and movement."""

    contact: Optional[Contact] = None
    group: Optional[Group] = None
    track: Optional[Track] = None
    remarks: Optional[str] = None

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Detail":
        """Create a :class:`Detail` from a ``<detail>`` element."""
        contact_el = elem.find("contact")
        group_el = elem.find("__group")
        track_el = elem.find("track")
        remarks_el = elem.find("remarks")
        return cls(
            contact=(
                Contact.from_xml(contact_el)
                if contact_el is not None
                else None
            ),
            group=(Group.from_xml(group_el) if group_el is not None else None),
            track=(Track.from_xml(track_el) if track_el is not None else None),
            remarks=remarks_el.text if remarks_el is not None else None,
        )

    def to_element(self) -> Optional[ET.Element]:
        """Return an XML detail element or ``None`` if empty."""
        if not any([self.contact, self.group, self.track, self.remarks]):
            return None
        detail_el = ET.Element("detail")
        if self.contact:
            detail_el.append(self.contact.to_element())
        if self.group:
            detail_el.append(self.group.to_element())
        if self.track:
            detail_el.append(self.track.to_element())
        if self.remarks:
            remarks_el = ET.SubElement(detail_el, "remarks")
            remarks_el.text = self.remarks
        return detail_el

    def to_dict(self) -> dict:
        """Return a dictionary containing populated fields only."""
        data: dict = {}
        if self.contact:
            data["contact"] = self.contact.to_dict()
        if self.group:
            data["group"] = self.group.to_dict()
        if self.track:
            data["track"] = self.track.to_dict()
        if self.remarks:
            data["remarks"] = self.remarks
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Detail":
        """Create a :class:`Detail` from a dictionary."""
        contact = None
        if "contact" in data:
            contact = Contact.from_dict(data["contact"])
        group = None
        if "group" in data:
            group = Group.from_dict(data["group"])
        track = None
        if "track" in data:
            track = Track.from_dict(data["track"])
        remarks = data.get("remarks")
        return cls(contact=contact, group=group, track=track, remarks=remarks)


@dataclass
class Event:
    """Top level CoT event object."""

    version: str
    uid: str
    type: str
    how: str
    time: str
    start: str
    stale: str
    point: Point
    detail: Optional[Detail] = None

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
            Point.from_xml(point_el)
            if point_el is not None
            else Point(0, 0, 0, 0, 0)
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
            detail=detail,
        )

    @classmethod
    def from_dict(cls, obj: dict) -> "Event":
        """Construct an :class:`Event` from a dictionary."""
        point = Point.from_dict(obj.get("point", {}))
        detail_obj = obj.get("detail")
        detail = Detail.from_dict(detail_obj) if detail_obj else None
        return cls(
            version=obj.get("version", ""),
            uid=obj.get("uid", ""),
            type=obj.get("type", ""),
            how=obj.get("how", ""),
            time=obj.get("time", ""),
            start=obj.get("start", ""),
            stale=obj.get("stale", ""),
            point=point,
            detail=detail,
        )

    @classmethod
    def from_json(cls, data: str) -> "Event":
        """Create an :class:`Event` from a JSON string."""
        return cls.from_dict(json.loads(data))

    def to_dict(self) -> dict:
        """Return a serialisable representation of the event."""
        data = {
            "version": self.version,
            "uid": self.uid,
            "type": self.type,
            "how": self.how,
            "time": self.time,
            "start": self.start,
            "stale": self.stale,
            "point": self.point.to_dict(),
        }
        if self.detail:
            data["detail"] = self.detail.to_dict()
        return data

    def to_element(self) -> ET.Element:
        """Return an XML ``<event>`` element."""
        event_attrs = {
            "version": self.version,
            "uid": self.uid,
            "type": self.type,
            "how": self.how,
            "time": self.time,
            "start": self.start,
            "stale": self.stale,
        }
        root = ET.Element("event", event_attrs)
        root.append(self.point.to_element())
        if self.detail:
            detail_el = self.detail.to_element()
            if detail_el is not None:
                root.append(detail_el)
        return root

    def to_xml(self, encoding: str = "unicode") -> Union[str, bytes]:
        """Return an XML string (or encoded bytes) for the event."""
        return ET.tostring(self.to_element(), encoding=encoding)

    def to_xml_bytes(self, encoding: str = "utf-8") -> bytes:
        """Convenience helper returning encoded XML bytes."""
        xml_data = self.to_xml(encoding=encoding)
        # ET.tostring may return bytes, but handle other bytes-like objects
        # (bytearray, memoryview) safely by converting to bytes first.
        if isinstance(xml_data, (bytes, bytearray, memoryview)):
            return bytes(xml_data)
        return xml_data.encode(encoding)

    def to_datapack(self) -> bytes:
        """Return a compressed datapack for network transport."""
        return pack_data(self.to_dict())

    @classmethod
    def from_datapack(cls, data: bytes) -> "Event":
        """Recreate an :class:`Event` packed with :meth:`to_datapack`."""
        obj = unpack_data(data)
        return cls.from_dict(obj)


__all__ = [
    "Event",
    "Detail",
    "Point",
    "Group",
    "Track",
    "Contact",
    "pack_data",
    "unpack_data",
]
