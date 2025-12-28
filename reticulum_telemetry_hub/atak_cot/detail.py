"""Detail payload helpers for ATAK Cursor on Target events."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional, Union

from reticulum_telemetry_hub.atak_cot.base import Contact
from reticulum_telemetry_hub.atak_cot.base import Group
from reticulum_telemetry_hub.atak_cot.base import Status
from reticulum_telemetry_hub.atak_cot.base import Takv
from reticulum_telemetry_hub.atak_cot.base import Track
from reticulum_telemetry_hub.atak_cot.base import Uid
from reticulum_telemetry_hub.atak_cot.chat import Chat
from reticulum_telemetry_hub.atak_cot.chat import ChatGroup
from reticulum_telemetry_hub.atak_cot.chat import Link
from reticulum_telemetry_hub.atak_cot.chat import Marti
from reticulum_telemetry_hub.atak_cot.chat import ServerDestination
from reticulum_telemetry_hub.atak_cot.chat import Remarks


@dataclass
class Detail:  # pylint: disable=too-many-instance-attributes
    """Additional information such as contact, group, and movement."""

    contact: Optional[Contact] = None
    group: Optional[Group] = None
    groups: list[Group] = field(default_factory=list)
    track: Optional[Track] = None
    takv: Optional[Takv] = None
    chat: Optional[Chat] = None
    chat_group: Optional[ChatGroup] = None
    uid: Optional[Uid] = None
    links: list[Link] = field(default_factory=list)
    remarks: Optional[Union[str, Remarks]] = None
    marti: Optional[Marti] = None
    status: Optional[Status] = None
    server_destination: bool = False

    @classmethod
    # pylint: disable=too-many-locals,too-many-branches
    def from_xml(cls, elem: ET.Element) -> "Detail":
        """Create a :class:`Detail` from a ``<detail>`` element."""

        contact_el = elem.find("contact")
        group_elems = elem.findall("__group")
        track_el = elem.find("track")
        takv_el = elem.find("takv")
        chat_el = elem.find("__chat")
        chatgrp_el = elem.find("chatgrp")
        uid_el = elem.find("uid")
        link_elems = elem.findall("link")
        remarks_el = elem.find("remarks")
        marti_el = elem.find("marti")
        server_destination_el = elem.find("__serverdestination")
        status_el = elem.find("status")
        groups = [Group.from_xml(item) for item in group_elems]
        primary_group = groups[0] if groups else None
        extra_groups = groups[1:] if len(groups) > 1 else []
        remarks: Optional[Union[str, Remarks]] = None
        if remarks_el is not None:
            if remarks_el.attrib:
                remarks = Remarks.from_xml(remarks_el)
            else:
                remarks = remarks_el.text
        return cls(
            contact=(Contact.from_xml(contact_el) if contact_el is not None else None),
            group=primary_group,
            groups=extra_groups,
            track=(Track.from_xml(track_el) if track_el is not None else None),
            takv=Takv.from_xml(takv_el) if takv_el is not None else None,
            chat=Chat.from_xml(chat_el) if chat_el is not None else None,
            chat_group=(
                ChatGroup.from_xml(chatgrp_el) if chatgrp_el is not None else None
            ),
            uid=Uid.from_xml(uid_el) if uid_el is not None else None,
            links=[Link.from_xml(item) for item in link_elems],
            remarks=remarks,
            marti=Marti.from_xml(marti_el) if marti_el is not None else None,
            status=Status.from_xml(status_el) if status_el is not None else None,
            server_destination=server_destination_el is not None,
        )

    def to_element(self) -> Optional[ET.Element]:  # pylint: disable=too-many-branches
        """Return an XML detail element or ``None`` if empty."""

        if not any(
            [
                self.contact,
                self.group,
                self.groups,
                self.track,
                self.takv,
                self.chat,
                self.chat_group,
                self.uid,
                self.links,
                self.remarks,
                self.marti,
                self.status,
                self.server_destination,
            ]
        ):
            return None
        detail_el = ET.Element("detail")
        if self.takv:
            detail_el.append(self.takv.to_element())
        if self.contact:
            detail_el.append(self.contact.to_element())
        if self.group:
            detail_el.append(self.group.to_element())
        for group in self.groups:
            detail_el.append(group.to_element())
        if self.track:
            detail_el.append(self.track.to_element())
        if self.chat:
            detail_el.append(self.chat.to_element())
        if self.chat_group:
            detail_el.append(self.chat_group.to_element())
        if self.uid:
            detail_el.append(self.uid.to_element())
        for link in self.links:
            detail_el.append(link.to_element())
        if self.remarks:
            if isinstance(self.remarks, Remarks):
                detail_el.append(self.remarks.to_element())
            else:
                remarks_el = ET.SubElement(detail_el, "remarks")
                remarks_el.text = self.remarks
        if self.marti:
            marti_element = self.marti.to_element()
            if marti_element is not None:
                detail_el.append(marti_element)
        if self.server_destination:
            detail_el.append(ServerDestination.to_element())
        if self.status:
            detail_el.append(self.status.to_element())
        return detail_el

    def to_dict(self) -> dict:  # pylint: disable=too-many-branches
        """Return a dictionary containing populated fields only."""

        data: dict = {}
        if self.contact:
            data["contact"] = self.contact.to_dict()
        if self.group:
            data["group"] = self.group.to_dict()
        if self.groups:
            data["groups"] = [group.to_dict() for group in self.groups]
        if self.track:
            data["track"] = self.track.to_dict()
        if self.takv:
            data["takv"] = self.takv.to_dict()
        if self.chat:
            data["chat"] = self.chat.to_dict()
        if self.chat_group:
            data["chat_group"] = self.chat_group.to_dict()
        if self.uid:
            data["uid"] = self.uid.to_dict()
        if self.links:
            data["links"] = [link.to_dict() for link in self.links]
        if self.remarks:
            data["remarks"] = (
                self.remarks.to_dict()
                if isinstance(self.remarks, Remarks)
                else self.remarks
            )
        if self.marti:
            marti_dict = self.marti.to_dict()
            if marti_dict:
                data["marti"] = marti_dict
        if self.status:
            data["status"] = self.status.to_dict()
        if self.server_destination:
            data["server_destination"] = True
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Detail":  # pylint: disable=too-many-locals
        """Create a :class:`Detail` from a dictionary."""

        contact = None
        if "contact" in data:
            contact = Contact.from_dict(data["contact"])
        group = None
        if "group" in data:
            group = Group.from_dict(data["group"])
        groups_data = data.get("groups", [])
        groups = [Group.from_dict(item) for item in groups_data]
        track = None
        if "track" in data:
            track = Track.from_dict(data["track"])
        takv = None
        if "takv" in data:
            takv = Takv.from_dict(data["takv"])
        chat = None
        if "chat" in data:
            chat = Chat.from_dict(data["chat"])
        chat_group = None
        if "chat_group" in data:
            chat_group = ChatGroup.from_dict(data["chat_group"])
        uid = None
        if "uid" in data:
            uid = Uid.from_dict(data["uid"])
        links_data = data.get("links", [])
        links = [Link.from_dict(item) for item in links_data]
        remarks_data = data.get("remarks")
        remarks = None
        if isinstance(remarks_data, dict):
            remarks = Remarks.from_dict(remarks_data)
        elif remarks_data is not None:
            remarks = str(remarks_data)
        marti = None
        if "marti" in data:
            marti = Marti.from_dict(data.get("marti", {}))
        status = None
        if "status" in data:
            status = Status.from_dict(data.get("status", {}))
        server_destination = data.get("server_destination", False) is True
        return cls(
            contact=contact,
            group=group,
            groups=groups,
            track=track,
            takv=takv,
            chat=chat,
            chat_group=chat_group,
            uid=uid,
            links=links,
            remarks=remarks,
            marti=marti,
            status=status,
            server_destination=server_destination,
        )
