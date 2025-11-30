from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Point:
    """A geographic point element."""

    lat: float
    lon: float
    hae: float
    ce: float
    le: float

    @classmethod
    def from_xml(cls, elem):
        """Create a :class:`Point` from an XML ``<point>`` element."""

        return cls(
            lat=float(elem.get("lat", 0)),
            lon=float(elem.get("lon", 0)),
            hae=float(elem.get("hae", 0)),
            ce=float(elem.get("ce", 0)),
            le=float(elem.get("le", 0)),
        )

    def to_element(self):
        """Return an XML element representing this point."""

        from xml.etree import ElementTree as ET

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
    def from_xml(cls, elem):
        """Construct a :class:`Contact` from an XML ``<contact>`` element."""

        return cls(callsign=elem.get("callsign", ""))

    def to_element(self):
        """Return an XML element for the contact."""

        from xml.etree import ElementTree as ET

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
    """Specifies group affiliation for the sender."""

    name: str
    role: str

    @classmethod
    def from_xml(cls, elem):
        """Create a :class:`Group` from an XML ``<__group>`` element."""

        return cls(name=elem.get("name", ""), role=elem.get("role", ""))

    def to_element(self):
        """Return an XML element for the group affiliation."""

        from xml.etree import ElementTree as ET

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
    def from_xml(cls, elem):
        """Parse an XML ``<track>`` element into a :class:`Track`."""

        return cls(
            course=float(elem.get("course", 0)), speed=float(elem.get("speed", 0))
        )

    def to_element(self):
        """Return an XML element for the movement details."""

        from xml.etree import ElementTree as ET

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
            course=float(data.get("course", 0)), speed=float(data.get("speed", 0))
        )
