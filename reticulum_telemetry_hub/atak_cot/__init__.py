"""ATAK COT support classes and datapack utilities.

This module provides a very small subset of the `Cursor on Target`_ (CoT)
schema used by ATAK. It is intentionally lightweight and only implements the
elements required by the accompanying tests. The objects can be created from XML
strings, converted back into dictionaries and packed into a compressed
"datapack" format for transport.

.. _Cursor on Target: https://github.com/FreeTAKTeam/FreeTAKTest
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import json
import xml.etree.ElementTree as ET
import gzip
import msgpack


def pack_data(obj: dict) -> bytes:
    """Return a gzip-compressed msgpack representation of ``obj``."""
    return gzip.compress(msgpack.packb(obj, use_bin_type=True))


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

    def to_dict(self) -> dict:
        """Return a serialisable representation."""
        return {"name": self.name, "role": self.role}

    @classmethod
    def from_dict(cls, data: dict) -> "Group":
        """Create a :class:`Group` from a dictionary."""
        return cls(name=data.get("name", ""), role=data.get("role", ""))


@dataclass
class Detail:
    """Additional information such as contact and group."""

    contact: Optional[Contact] = None
    group: Optional[Group] = None
    remarks: Optional[str] = None

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Detail":
        """Create a :class:`Detail` from a ``<detail>`` element."""
        contact_el = elem.find("contact")
        group_el = elem.find("__group")
        remarks_el = elem.find("remarks")
        return cls(
            contact=(Contact.from_xml(contact_el) if contact_el is not None else None),
            group=(Group.from_xml(group_el) if group_el is not None else None),
            remarks=remarks_el.text if remarks_el is not None else None,
        )

    def to_dict(self) -> dict:
        """Return a dictionary containing populated fields only."""
        data: dict = {}
        if self.contact:
            data["contact"] = self.contact.to_dict()
        if self.group:
            data["group"] = self.group.to_dict()
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
        remarks = data.get("remarks")
        return cls(contact=contact, group=group, remarks=remarks)


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
    def from_xml(cls, xml: str) -> "Event":
        """Parse an entire ``<event>`` XML string."""
        root = ET.fromstring(xml)
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
    "Contact",
    "pack_data",
    "unpack_data",
]
