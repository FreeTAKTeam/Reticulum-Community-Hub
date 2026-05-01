"""CoT chat event helpers for the TAK connector."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
import json
import uuid

import RNS

from reticulum_telemetry_hub.atak_cot import Chat
from reticulum_telemetry_hub.atak_cot import ChatGroup
from reticulum_telemetry_hub.atak_cot import Detail
from reticulum_telemetry_hub.atak_cot import Event
from reticulum_telemetry_hub.atak_cot import Link
from reticulum_telemetry_hub.atak_cot import Marti
from reticulum_telemetry_hub.atak_cot import MartiDest
from reticulum_telemetry_hub.atak_cot import Remarks
from reticulum_telemetry_hub.atak_cot.tak_connector_models import utc_iso_millis
from reticulum_telemetry_hub.atak_cot.tak_connector_models import utcnow


class TakChatMixin:
    """Build and send CoT chat events."""

    def build_chat_event(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        *,
        content: str,
        sender_label: str,
        topic_id: str | None = None,
        source_hash: str | None = None,
        timestamp: datetime | None = None,
        message_uuid: str | None = None,
    ) -> Event:
        """Construct a CoT chat :class:`Event` for LXMF message content."""

        if not content:
            raise ValueError("Chat content is required to build a CoT event.")

        event_time = timestamp or utcnow()
        stale = event_time + timedelta(hours=24)
        chatroom = str(topic_id) if topic_id else "All Chat Rooms"
        sender_uid = self._normalize_hash(source_hash) or self._config.callsign
        message_id = message_uuid or str(uuid.uuid4())
        event_uid = f"GeoChat.{sender_uid}.{chatroom}.{message_id}"

        chat_group = ChatGroup(
            chatroom=None,
            chat_id=chatroom,
            uid0=sender_uid,
            uid1=chatroom,
        )
        chat = Chat(
            id=chatroom,
            chatroom=chatroom,
            sender_callsign=sender_label,
            group_owner="false",
            message_id=message_id,
            chat_group=chat_group,
        )
        link = Link(
            uid=sender_uid,
            type=self.CHAT_LINK_TYPE,
            relation="p-p",
        )
        remarks_source = f"LXMF.CLIENT.{sender_uid}" if sender_uid else "LXMF.CLIENT"
        remarks = Remarks(
            text=content.strip(),
            source=remarks_source,
            source_id=sender_uid,
            to=chatroom,
            time=utc_iso_millis(event_time),
        )
        detail = Detail(
            chat=chat,
            links=[link],
            remarks=remarks,
            marti=Marti(dest=MartiDest(callsign=None)),
            server_destination=True,
        )

        event_dict = {
            "version": "2.0",
            "uid": event_uid,
            "type": self.CHAT_EVENT_TYPE,
            "how": self.CHAT_EVENT_HOW,
            "access": "Undefined",
            "time": utc_iso_millis(event_time),
            "start": utc_iso_millis(event_time),
            "stale": utc_iso_millis(stale),
            "point": {
                "lat": 0.0,
                "lon": 0.0,
                "hae": 9999999.0,
                "ce": 9999999.0,
                "le": 9999999.0,
            },
            "detail": detail.to_dict(),
        }
        return Event.from_dict(event_dict)

    async def send_chat_event(  # pylint: disable=too-many-arguments
        self,
        *,
        content: str,
        sender_label: str,
        topic_id: str | None = None,
        source_hash: str | None = None,
        timestamp: datetime | None = None,
        message_uuid: str | None = None,
    ) -> bool:
        """Send a CoT chat event derived from LXMF payloads."""

        event = self.build_chat_event(
            content=content,
            sender_label=sender_label,
            topic_id=topic_id,
            source_hash=source_hash,
            timestamp=timestamp,
            message_uuid=message_uuid,
        )
        event_size = len(json.dumps(event.to_dict()))
        RNS.log(
            f"TAK connector sending event type {event.type} ({event_size} bytes)",
            RNS.LOG_INFO,
        )
        await self._pytak_client.create_and_send_message(
            event, config=self._config_parser, parse_inbound=False
        )
        return True
