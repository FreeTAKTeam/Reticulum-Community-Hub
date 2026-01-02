"""GeoChat-specific data structures for ATAK Cursor on Target payloads."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChatHierarchyContact:
    """Represents a contact entry inside a chat hierarchy."""

    uid: str
    name: str

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "ChatHierarchyContact":
        """Create a :class:`ChatHierarchyContact` from a ``<contact>`` element."""

        return cls(uid=elem.get("uid", ""), name=elem.get("name", ""))

    def to_element(self) -> ET.Element:
        """Return an XML element representing the hierarchy contact."""

        return ET.Element("contact", {"uid": self.uid, "name": self.name})

    def to_dict(self) -> dict:
        """Return a serialisable representation of the hierarchy contact."""

        return {"uid": self.uid, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> "ChatHierarchyContact":
        """Create a :class:`ChatHierarchyContact` from a dictionary."""

        return cls(uid=data.get("uid", ""), name=data.get("name", ""))


@dataclass
class ChatHierarchyGroup:
    """Represents nested groups under the chat hierarchy."""

    uid: str
    name: str
    contacts: list[ChatHierarchyContact] = field(default_factory=list)
    groups: list["ChatHierarchyGroup"] = field(default_factory=list)

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "ChatHierarchyGroup":
        """Create a :class:`ChatHierarchyGroup` from a ``<group>`` element."""

        contacts = [
            ChatHierarchyContact.from_xml(item) for item in elem.findall("contact")
        ]
        child_groups = [
            ChatHierarchyGroup.from_xml(item) for item in elem.findall("group")
        ]
        return cls(
            uid=elem.get("uid", ""),
            name=elem.get("name", ""),
            contacts=contacts,
            groups=child_groups,
        )

    def to_element(self) -> ET.Element:
        """Return an XML element representing the hierarchy group."""

        element = ET.Element("group", {"uid": self.uid, "name": self.name})
        for contact in self.contacts:
            element.append(contact.to_element())
        for group in self.groups:
            element.append(group.to_element())
        return element

    def to_dict(self) -> dict:
        """Return a serialisable representation of the hierarchy group."""

        data: dict = {"uid": self.uid, "name": self.name}
        if self.contacts:
            data["contacts"] = [contact.to_dict() for contact in self.contacts]
        if self.groups:
            data["groups"] = [group.to_dict() for group in self.groups]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ChatHierarchyGroup":
        """Create a :class:`ChatHierarchyGroup` from a dictionary."""

        contacts_data = data.get("contacts", [])
        groups_data = data.get("groups", [])
        contacts = [ChatHierarchyContact.from_dict(item) for item in contacts_data]
        groups = [ChatHierarchyGroup.from_dict(item) for item in groups_data]
        return cls(
            uid=data.get("uid", ""),
            name=data.get("name", ""),
            contacts=contacts,
            groups=groups,
        )


@dataclass
class ChatHierarchy:
    """Root chat hierarchy container."""

    groups: list[ChatHierarchyGroup] = field(default_factory=list)

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "ChatHierarchy":
        """Create a :class:`ChatHierarchy` from a ``<hierarchy>`` element."""

        groups = [ChatHierarchyGroup.from_xml(item) for item in elem.findall("group")]
        return cls(groups=groups)

    def to_element(self) -> ET.Element:
        """Return an XML hierarchy element."""

        element = ET.Element("hierarchy")
        for group in self.groups:
            element.append(group.to_element())
        return element

    def to_dict(self) -> dict:
        """Return a serialisable representation of the hierarchy."""

        return {"groups": [group.to_dict() for group in self.groups]}

    @classmethod
    def from_dict(cls, data: dict) -> "ChatHierarchy":
        """Create a :class:`ChatHierarchy` from a dictionary."""

        groups_data = data.get("groups", [])
        return cls(groups=[ChatHierarchyGroup.from_dict(item) for item in groups_data])


@dataclass
class ChatGroup:
    """Participants and identifiers for a GeoChat room."""

    chat_id: str
    uid0: str
    chatroom: Optional[str] = None
    uid1: str = ""
    uid2: str = ""

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "ChatGroup":
        """Create a :class:`ChatGroup` from a ``<chatgrp>`` element."""

        return cls(
            chatroom=elem.get("chatroom"),
            chat_id=elem.get("id", ""),
            uid0=elem.get("uid0", ""),
            uid1=elem.get("uid1", ""),
            uid2=elem.get("uid2", ""),
        )

    def to_element(self) -> ET.Element:
        """Return an XML element describing the chat group."""

        attrib = {
            "id": self.chat_id,
            "uid0": self.uid0,
            "uid1": self.uid1,
        }
        if self.chatroom:
            attrib["chatroom"] = self.chatroom
        if self.uid2:
            attrib["uid2"] = self.uid2
        return ET.Element("chatgrp", attrib)

    def to_dict(self) -> dict:
        """Return a serialisable representation of the chat group."""

        data = {
            "chat_id": self.chat_id,
            "uid0": self.uid0,
            "uid1": self.uid1,
        }
        if self.chatroom:
            data["chatroom"] = self.chatroom
        if self.uid2:
            data["uid2"] = self.uid2
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ChatGroup":
        """Create a :class:`ChatGroup` from a dictionary."""

        return cls(
            chatroom=data.get("chatroom"),
            chat_id=data.get("chat_id", ""),
            uid0=data.get("uid0", ""),
            uid1=data.get("uid1", ""),
            uid2=data.get("uid2", ""),
        )


@dataclass
class Remarks:
    """Represents annotated remarks content."""

    text: str
    source: Optional[str] = None
    source_id: Optional[str] = None
    to: Optional[str] = None
    time: Optional[str] = None

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Remarks":
        """Create a :class:`Remarks` from a ``<remarks>`` element."""

        return cls(
            text=elem.text or "",
            source=elem.get("source"),
            source_id=elem.get("sourceID"),
            to=elem.get("to"),
            time=elem.get("time"),
        )

    def to_element(self) -> ET.Element:
        """Return an XML element with optional metadata."""

        attrib: dict[str, str] = {}
        if self.source is not None:
            attrib["source"] = self.source
        if self.source_id is not None:
            attrib["sourceID"] = self.source_id
        if self.to is not None:
            attrib["to"] = self.to
        if self.time is not None:
            attrib["time"] = self.time
        element = ET.Element("remarks", attrib)
        element.text = self.text
        return element

    def to_dict(self) -> dict:
        """Return a serialisable representation of the remarks."""

        data: dict = {"text": self.text}
        if self.source is not None:
            data["source"] = self.source
        if self.source_id is not None:
            data["source_id"] = self.source_id
        if self.to is not None:
            data["to"] = self.to
        if self.time is not None:
            data["time"] = self.time
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Remarks":
        """Create a :class:`Remarks` from a dictionary."""

        return cls(
            text=data.get("text", ""),
            source=data.get("source"),
            source_id=data.get("source_id"),
            to=data.get("to"),
            time=data.get("time"),
        )


@dataclass
class MartiDest:
    """Represents a MARTI destination element."""

    callsign: Optional[str] = None

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "MartiDest":
        """Create a :class:`MartiDest` from a ``<dest>`` element."""

        return cls(callsign=elem.get("callsign", ""))

    def to_element(self) -> ET.Element:
        """Return an XML element representing the destination."""

        attrib: dict[str, str] = {}
        if self.callsign:
            attrib["callsign"] = self.callsign
        return ET.Element("dest", attrib)

    def to_dict(self) -> dict:
        """Return a serialisable representation of the destination."""

        return {"callsign": self.callsign}

    @classmethod
    def from_dict(cls, data: dict) -> "MartiDest":
        """Create a :class:`MartiDest` from a dictionary."""

        return cls(callsign=data.get("callsign"))


@dataclass
class Marti:
    """Represents MARTI routing details."""

    dest: Optional[MartiDest] = None

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Marti":
        """Create a :class:`Marti` from a ``<marti>`` element."""

        dest_el = elem.find("dest")
        return cls(dest=MartiDest.from_xml(dest_el) if dest_el is not None else None)

    def to_element(self) -> Optional[ET.Element]:
        """Return a MARTI element when routing information exists."""

        if self.dest is None:
            return None
        element = ET.Element("marti")
        element.append(self.dest.to_element())
        return element

    def to_dict(self) -> dict:
        """Return a serialisable representation of the MARTI details."""

        if self.dest is None:
            return {}
        return {"dest": self.dest.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "Marti":
        """Create a :class:`Marti` from a dictionary."""

        dest_data = data.get("dest")
        dest = MartiDest.from_dict(dest_data) if isinstance(dest_data, dict) else None
        return cls(dest=dest)


@dataclass
class ServerDestination:
    """Represents an empty ``__serverdestination`` marker element."""

    @staticmethod
    def to_element() -> ET.Element:
        """Return an empty ``__serverdestination`` element."""

        return ET.Element("__serverdestination")

    @staticmethod
    def to_dict() -> dict:
        """Return an empty mapping representing the marker."""

        return {}


@dataclass
class Chat:  # pylint: disable=too-many-instance-attributes
    """Metadata describing the GeoChat parent and room."""

    parent: Optional[str] = None
    id: Optional[str] = None
    chatroom: Optional[str] = None
    sender_callsign: Optional[str] = None
    group_owner: Optional[str] = None
    message_id: Optional[str] = None
    chat_group: Optional[ChatGroup] = None
    hierarchy: Optional[ChatHierarchy] = None

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Chat":
        """Create a :class:`Chat` from an XML ``<__chat>`` element."""

        chat_group_el = elem.find("chatgrp")
        hierarchy_el = elem.find("hierarchy")
        return cls(
            parent=elem.get("parent"),
            id=elem.get("id"),
            chatroom=elem.get("chatroom"),
            sender_callsign=elem.get("senderCallsign"),
            group_owner=elem.get("groupOwner"),
            message_id=elem.get("messageId"),
            chat_group=(
                ChatGroup.from_xml(chat_group_el) if chat_group_el is not None else None
            ),
            hierarchy=(
                ChatHierarchy.from_xml(hierarchy_el)
                if hierarchy_el is not None
                else None
            ),
        )

    def to_element(self) -> ET.Element:
        """Return an XML element representing the chat metadata."""

        attrib = {}
        if self.parent is not None:
            attrib["parent"] = self.parent
        if self.id is not None:
            attrib["id"] = self.id
        if self.chatroom is not None:
            attrib["chatroom"] = self.chatroom
        if self.sender_callsign is not None:
            attrib["senderCallsign"] = self.sender_callsign
        if self.group_owner is not None:
            attrib["groupOwner"] = self.group_owner
        if self.message_id is not None:
            attrib["messageId"] = self.message_id
        element = ET.Element("__chat", attrib)
        if self.chat_group:
            element.append(self.chat_group.to_element())
        if self.hierarchy:
            element.append(self.hierarchy.to_element())
        return element

    def to_dict(self) -> dict:
        """Return a serialisable representation of the chat details."""

        data: dict = {}
        if self.parent is not None:
            data["parent"] = self.parent
        if self.id is not None:
            data["id"] = self.id
        if self.chatroom is not None:
            data["chatroom"] = self.chatroom
        if self.sender_callsign is not None:
            data["sender_callsign"] = self.sender_callsign
        if self.group_owner is not None:
            data["group_owner"] = self.group_owner
        if self.message_id is not None:
            data["message_id"] = self.message_id
        if self.chat_group:
            data["chat_group"] = self.chat_group.to_dict()
        if self.hierarchy:
            data["hierarchy"] = self.hierarchy.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Chat":
        """Create a :class:`Chat` from a dictionary."""

        chat_group = None
        if "chat_group" in data:
            chat_group = ChatGroup.from_dict(data["chat_group"])
        hierarchy = None
        if "hierarchy" in data:
            hierarchy = ChatHierarchy.from_dict(data["hierarchy"])
        return cls(
            parent=data.get("parent"),
            id=data.get("id"),
            chatroom=data.get("chatroom"),
            sender_callsign=data.get("sender_callsign"),
            group_owner=data.get("group_owner"),
            message_id=data.get("message_id"),
            chat_group=chat_group,
            hierarchy=hierarchy,
        )


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
