"""Telemetry serialization, event, and reply helpers."""
# pylint: disable=no-member

from __future__ import annotations

from datetime import datetime
import json
import string
import time
from typing import Optional

import LXMF
import RNS
from msgpack import unpackb

from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.telemeter import Telemeter
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import SID_TIME
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_mapping import sid_mapping
from reticulum_telemetry_hub.reticulum_server.appearance import apply_icon_appearance
from reticulum_telemetry_hub.reticulum_server.appearance import build_telemetry_icon_appearance_value
from reticulum_telemetry_hub.reticulum_server.runtime_events import report_nonfatal_exception


class TelemetrySerializationMixin:
    """Serialize telemetry and build LXMF response fields."""

    _ingest_count: int
    _last_ingest_at: datetime | None

    def _serialize_telemeter(self, telemeter: Telemeter) -> dict:
        """Serialize the telemeter data."""
        telemeter_data = {}
        for sensor in telemeter.sensors:
            sensor_data = sensor.pack()
            telemeter_data[sensor.sid] = sensor_data

        # Ensure the timestamp sensor is always present so downstream
        # consumers (e.g. Sideband) can reconstitute the Telemeter.
        timestamp = int(telemeter.time.timestamp())
        time_payload = telemeter_data.get(SID_TIME)
        if not isinstance(time_payload, (int, float)):
            telemeter_data[SID_TIME] = timestamp
        else:
            telemeter_data[SID_TIME] = int(time_payload)

        return telemeter_data

    def _stream_appearance(self) -> list:
        """Return appearance metadata for telemetry stream entries."""

        return list(self.DEFAULT_STREAM_APPEARANCE)

    def _deserialize_telemeter(self, tel_data, peer_dest: str = "") -> Telemeter:
        """Deserialize the telemeter data.

        The method accepts either already unpacked telemetry dictionaries or
        raw msgpack-encoded bytes. The optional ``peer_dest`` parameter is
        primarily used when storing data received from the network.
        """
        if isinstance(tel_data, (bytes, bytearray)):
            tel_data = unpackb(tel_data, strict_map_key=False)

        tel = Telemeter(peer_dest)
        # Iterate in the order defined by ``sid_mapping`` so tests relying on
        # specific sensor ordering remain stable.
        for sid in sid_mapping:
            if sid in tel_data:
                if tel_data[sid] is None:
                    RNS.log(f"Sensor data for {sid} is None")
                    continue
                sensor = sid_mapping[sid]()
                sensor.unpack(tel_data[sid])
                tel.sensors.append(sensor)
        time_value = tel_data.get(SID_TIME)
        if isinstance(time_value, (int, float)):
            tel.time = datetime.fromtimestamp(int(time_value))
        return tel

    def _humanize_telemetry(self, tel_data: dict) -> dict:
        """Return a friendly dict mapping sensor names to decoded readings."""
        if isinstance(tel_data, (bytes, bytearray)):
            tel_data = unpackb(tel_data, strict_map_key=False)

        readable: dict[str, object] = {}
        for sid, payload in tel_data.items():
            name = self.SID_HUMAN_NAMES.get(sid, f"sid_{sid}")
            sensor_cls = sid_mapping.get(sid)
            if sensor_cls is None:
                readable[name] = payload
                continue
            sensor = sensor_cls()
            try:
                decoded = sensor.unpack(payload)
            except Exception as exc:  # pragma: no cover - defensive logging
                RNS.log(f"Failed decoding telemetry sensor {name}: {exc}")
                decoded = payload
            readable[name] = decoded
        return readable

    def _build_appearance_payload(
        self, telemetry_payload: dict[int, object]
    ) -> list[object]:
        """Return the appearance payload for telemetry stream entries.

        Args:
            telemetry_payload (dict[int, object]): Serialized telemetry payload.

        Returns:
            list[object]: LXMF appearance list for stream entries.
        """

        return build_telemetry_icon_appearance_value(telemetry_payload)

    def _notify_listener(
        self,
        telemetry: dict,
        peer_hash: str | bytes | None,
        timestamp: Optional[datetime],
    ) -> None:
        """Invoke each registered telemetry listener when present."""

        if not self._telemetry_listeners:
            return
        for listener in list(self._telemetry_listeners):
            try:
                listener(telemetry, peer_hash, timestamp)
            except Exception as exc:  # pragma: no cover - defensive logging
                report_nonfatal_exception(
                    self._event_log,
                    "telemetry_error",
                    f"Telemetry listener raised an exception: {exc}",
                    exc,
                    metadata={
                        "operation": "listener",
                        "peer_hash": (
                            peer_hash.hex() if isinstance(peer_hash, bytes) else peer_hash
                        ),
                    },
                    log_level=RNS.LOG_WARNING,
                )

    def _record_event(
        self,
        event_type: str,
        message: str,
        *,
        metadata: Optional[dict] = None,
    ) -> None:
        """Emit a telemetry event to the shared event log."""

        if self._event_log is None:
            return
        self._event_log.add_event(event_type, message, metadata=metadata)

    def _resolve_peer_label(self, peer_dest: str) -> tuple[str | None, str]:
        """Return display name and label for a peer destination."""

        display_name = None
        if self._api is not None and hasattr(self._api, "resolve_identity_display_name"):
            try:
                display_name = self._api.resolve_identity_display_name(peer_dest)
            except Exception:  # pragma: no cover - defensive
                display_name = None
        if display_name:
            return display_name, f"{display_name} ({peer_dest})"
        return None, peer_dest

    def _record_ingest(self, telemeter: Telemeter) -> None:
        """Update telemetry ingestion statistics."""

        self._ingest_count += 1
        if telemeter.time:
            self._last_ingest_at = telemeter.time

    @staticmethod
    def _reply(
        message: LXMF.LXMessage,
        my_lxm_dest,
        content: str,
        *,
        topic_id: str | None = None,
        status: str = "ok",
    ) -> LXMF.LXMessage:
        """Return an LXMF reply message to the sender."""

        dest = RNS.Destination(
            message.source.identity,
            RNS.Destination.OUT,
            RNS.Destination.SINGLE,
            "lxmf",
            "delivery",
        )
        return LXMF.LXMessage(
            dest,
            my_lxm_dest,
            content,
            fields=apply_icon_appearance(
                TelemetrySerializationMixin._merge_standard_fields(
                    source_fields=message.fields,
                    extra_fields={
                        LXMF.FIELD_RESULTS: TelemetrySerializationMixin._build_results_field(content),
                        LXMF.FIELD_EVENT: TelemetrySerializationMixin._build_event_field(
                            event_type="rch.telemetry.response",
                            topic_id=topic_id,
                            status=status,
                        ),
                    },
                )
            ),
            desired_method=LXMF.LXMessage.DIRECT,
        )

    @staticmethod
    def _relay_standard_fields(fields: dict | None) -> dict | None:
        """Return relay-safe standard LXMF metadata fields."""

        if not isinstance(fields, dict):
            return None
        relayed: dict = {}
        for key in (LXMF.FIELD_THREAD, LXMF.FIELD_GROUP):
            value = fields.get(key)
            if value is not None:
                relayed[key] = value
        return relayed or None

    @classmethod
    def _merge_standard_fields(
        cls,
        *,
        source_fields: dict | None,
        extra_fields: dict | None,
    ) -> dict:
        """Merge relay-safe standard fields with explicit outbound fields."""

        merged: dict = {}
        relayed = cls._relay_standard_fields(source_fields)
        if relayed:
            merged.update(relayed)
        if isinstance(extra_fields, dict):
            merged.update(extra_fields)
        return merged

    @staticmethod
    def _build_results_field(content: str):
        """Return a compact FIELD_RESULTS payload for textual telemetry replies."""

        text_value = str(content or "")
        stripped = text_value.strip()
        if stripped:
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if parsed is not None:
                return parsed
        if len(text_value.encode("utf-8", errors="ignore")) <= 1024:
            return text_value
        return {
            "truncated": True,
            "content_length_bytes": len(text_value.encode("utf-8", errors="ignore")),
            "preview": text_value[:1024],
        }

    @staticmethod
    def _build_event_field(
        *,
        event_type: str,
        topic_id: str | None,
        status: str,
    ) -> dict[str, object]:
        """Return a structured event payload for FIELD_EVENT."""

        payload: dict[str, object] = {
            "event_type": event_type,
            "status": status,
            "ts": int(time.time()),
            "source": "rch",
        }
        if topic_id:
            payload["topic_id"] = topic_id
        return payload

    @staticmethod
    def _extract_topic_id(command: dict) -> Optional[str]:
        """Return a topic id from a telemetry command payload."""

        return (
            command.get("TopicID")
            or command.get("topic_id")
            or command.get("topicId")
        )

    @staticmethod
    def _numeric_command_key(command: dict, index: int) -> int | str | None:
        """Return the numeric command key matching the provided index.

        Args:
            command (dict): Incoming command payload.
            index (int): Numeric index to locate.

        Returns:
            int | str | None: The matching key when present.
        """

        for key in command:
            try:
                if str(key).isdigit() and int(str(key)) == index:
                    return key
            except ValueError:
                continue
        return None

    def _allowed_topic_destinations(
        self, topic_id: str | None
    ) -> tuple[set[str] | None, bool]:
        """Return allowed peer destinations for ``topic_id``.

        Returns:
            tuple[set[str] | None, bool]: Allowed destinations and whether the
            topic exists.
        """

        if topic_id is None or self._api is None:
            return None, True
        try:
            subscribers = self._api.list_subscribers_for_topic(topic_id)
        except KeyError:
            return set(), False
        return {sub.destination for sub in subscribers if sub.destination}, True

    def _allowed_topic_destinations_for_sender(
        self, topic_id: str | None, message: LXMF.LXMessage
    ) -> tuple[set[str] | None, bool]:
        """Return topic destinations and whether the sender is authorized."""

        allowed, topic_exists = self._allowed_topic_destinations(topic_id)
        if topic_id is None or self._api is None or allowed is None:
            return allowed, True
        if not topic_exists:
            return allowed, True
        destination = self._identity_hex(message.source.identity)
        if destination not in allowed:
            return None, False
        return allowed, True

    @staticmethod
    def _identity_hex(identity: RNS.Identity) -> str:
        """Return the identity hash as a lowercase hex string."""

        hash_bytes = getattr(identity, "hash", b"") or b""
        return hash_bytes.hex()

    def _extract_timestamp(self, telemetry: dict) -> Optional[datetime]:
        """Return a datetime parsed from a telemetry payload when available."""

        time_payload = telemetry.get("time")
        if isinstance(time_payload, dict):
            raw_timestamp = time_payload.get("timestamp")
            if isinstance(raw_timestamp, (int, float)):
                return datetime.fromtimestamp(int(raw_timestamp))
            iso_value = time_payload.get("iso")
            if isinstance(iso_value, str):
                try:
                    return datetime.fromisoformat(iso_value)
                except ValueError:
                    return None
        if isinstance(time_payload, (int, float)):
            return datetime.fromtimestamp(int(time_payload))
        return None

    def _peer_hash_bytes(self, telemeter: Telemeter) -> Optional[bytes]:
        """Return the peer hash for ``telemeter`` as bytes or ``None`` on failure."""

        peer_dest = (telemeter.peer_dest or "").strip()
        if not peer_dest:
            RNS.log("Telemetry entry missing peer destination; skipping")
            return None

        normalized = "".join(ch for ch in peer_dest if ch in string.hexdigits)
        if not normalized:
            RNS.log(
                f"Telemetry entry peer destination missing hex characters: {peer_dest!r}"
            )
            return None
        if len(normalized) % 2 != 0:
            RNS.log(
                f"Telemetry entry peer destination has odd length after normalization: {peer_dest!r}"
            )
            return None

        try:
            return bytes.fromhex(normalized)
        except ValueError as exc:
            RNS.log(
                f"Skipping telemetry entry with invalid peer destination {peer_dest!r}: {exc}"
            )
            return None

    def _json_safe(self, value):
        """Return ``value`` converted into a JSON-safe structure."""

        if isinstance(value, dict):
            return {self._json_key(k): self._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(v) for v in value]
        if isinstance(value, (bytes, bytearray)):
            return value.hex()
        return value

    def _json_key(self, key):
        """Return a JSON-safe dict key representation."""

        if isinstance(key, (str, int, float, bool)) or key is None:
            return key
        if isinstance(key, (bytes, bytearray)):
            return key.hex()
        return str(key)
