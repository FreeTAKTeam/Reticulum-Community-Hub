"""GeoChat participant link model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import xml.etree.ElementTree as ET


@dataclass
class Link:
    """Relationship metadata for GeoChat participants."""

    uid: str
    type: str
    relation: str
    production_time: Optional[str] = None
    parent_callsign: Optional[str] = None

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Link":
        """Create a :class:`Link` from a ``<link>`` element."""

        return cls(
            uid=elem.get("uid", ""),
            type=elem.get("type", ""),
            relation=elem.get("relation", ""),
            production_time=elem.get("production_time"),
            parent_callsign=elem.get("parent_callsign"),
        )

    def to_element(self) -> ET.Element:
        """Return an XML element for the participant link."""

        attrib = {"uid": self.uid, "type": self.type, "relation": self.relation}
        if self.production_time is not None:
            attrib["production_time"] = self.production_time
        if self.parent_callsign is not None:
            attrib["parent_callsign"] = self.parent_callsign
        return ET.Element("link", attrib)

    def to_dict(self) -> dict:
        """Return a serialisable representation of the link."""

        data = {"uid": self.uid, "type": self.type, "relation": self.relation}
        if self.production_time is not None:
            data["production_time"] = self.production_time
        if self.parent_callsign is not None:
            data["parent_callsign"] = self.parent_callsign
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Link":
        """Create a :class:`Link` from a dictionary."""

        return cls(
            uid=data.get("uid", ""),
            type=data.get("type", ""),
            relation=data.get("relation", ""),
            production_time=data.get("production_time"),
            parent_callsign=data.get("parent_callsign"),
        )
