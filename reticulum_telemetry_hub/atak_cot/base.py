"""Data classes representing ATAK Cursor-on-Target primitives."""

from __future__ import annotations

from dataclasses import dataclass
import xml.etree.ElementTree as ET


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
    endpoint: str | None = None

    @classmethod
    def from_xml(cls, elem):
        """Construct a :class:`Contact` from an XML ``<contact>`` element."""

        return cls(callsign=elem.get("callsign", ""), endpoint=elem.get("endpoint"))

    def to_element(self):
        """Return an XML element for the contact."""

        attrib = {"callsign": self.callsign}
        if self.endpoint:
            attrib["endpoint"] = self.endpoint
        return ET.Element("contact", attrib)

    def to_dict(self) -> dict:
        """Return a serialisable representation."""

        data = {"callsign": self.callsign}
        if self.endpoint:
            data["endpoint"] = self.endpoint
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Contact":
        """Create a :class:`Contact` from a dictionary."""

        return cls(callsign=data.get("callsign", ""), endpoint=data.get("endpoint"))


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

        return ET.Element("track", {"course": str(self.course), "speed": str(self.speed)})

    def to_dict(self) -> dict:
        """Return a serialisable representation."""

        return {"course": self.course, "speed": self.speed}

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        """Create a :class:`Track` from a dictionary."""

        return cls(
            course=float(data.get("course", 0)), speed=float(data.get("speed", 0))
        )


@dataclass
class Takv:
    """Describes the TAK client version and platform information."""

    version: str
    platform: str
    os: str
    device: str

    @classmethod
    def from_xml(cls, elem):
        """Create a :class:`Takv` from an XML ``<takv>`` element."""

        return cls(
            version=elem.get("version", ""),
            platform=elem.get("platform", ""),
            os=elem.get("os", ""),
            device=elem.get("device", ""),
        )

    def to_element(self):
        """Return an XML element representing this TAK client."""

        return ET.Element(
            "takv",
            {
                "version": self.version,
                "platform": self.platform,
                "os": self.os,
                "device": self.device,
            },
        )

    def to_dict(self) -> dict:
        """Return a serialisable representation."""

        return {
            "version": self.version,
            "platform": self.platform,
            "os": self.os,
            "device": self.device,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Takv":
        """Create a :class:`Takv` from a dictionary."""

        return cls(
            version=data.get("version", ""),
            platform=data.get("platform", ""),
            os=data.get("os", ""),
            device=data.get("device", ""),
        )


@dataclass
class Uid:
    """Nested UID used by ATAK to describe the Droid identifier."""

    droid: str

    @classmethod
    def from_xml(cls, elem):
        """Construct a :class:`Uid` from an XML ``<uid>`` element."""

        return cls(droid=elem.get("Droid", ""))

    def to_element(self):
        """Return an XML element representing the UID."""

        return ET.Element("uid", {"Droid": self.droid})

    def to_dict(self) -> dict:
        """Return a serialisable representation."""

        return {"Droid": self.droid}

    @classmethod
    def from_dict(cls, data: dict) -> "Uid":
        """Create a :class:`Uid` from a dictionary."""

        return cls(droid=data.get("Droid", ""))


@dataclass
class Status:
    """Represents battery status information."""

    battery: float

    @classmethod
    def from_xml(cls, elem):
        """Construct a :class:`Status` from an XML ``<status>`` element."""

        return cls(battery=float(elem.get("battery", 0)))

    def to_element(self):
        """Return an XML element representing status."""

        return ET.Element("status", {"battery": str(self.battery)})

    def to_dict(self) -> dict:
        """Return a serialisable representation."""

        return {"battery": self.battery}

    @classmethod
    def from_dict(cls, data: dict) -> "Status":
        """Create a :class:`Status` from a dictionary."""

        return cls(battery=float(data.get("battery", 0)))
