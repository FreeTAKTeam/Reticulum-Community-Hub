"""Telemetry command handling helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import LXMF
import RNS
from msgpack import packb

from reticulum_telemetry_hub.reticulum_server.appearance import apply_icon_appearance


class TelemetryCommandMixin:
    """Handle inbound telemetry request commands."""

    def handle_command(
        self, command: dict, message: LXMF.LXMessage, my_lxm_dest
    ) -> Optional[LXMF.LXMessage]:
        """Handle the incoming command."""
        request_key = self._numeric_command_key(
            command, self.TELEMETRY_REQUEST
        )
        if request_key is not None:
            request_value = command[request_key]
            topic_id = self._extract_topic_id(command)

            # Sideband (and compatible clients) send telemetry requests either as a
            # standalone timestamp or as ``[timestamp, collector_flag]``.  The
            # hub currently ignores the optional collector flag, but we still
            # need to unpack the timestamp so ``datetime.fromtimestamp`` doesn't
            # receive a list and raise ``TypeError``.
            if isinstance(request_value, (list, tuple)):
                if not request_value:
                    return None
                timebase_raw = request_value[0]
            else:
                timebase_raw = request_value

            if not isinstance(timebase_raw, (int, float)):
                raise TypeError(
                    "Telemetry request timestamp must be numeric; "
                    f"received {type(timebase_raw)!r}"
                )

            timebase = int(timebase_raw)
            human_readable_entries: list[dict[str, object]] = []
            with self._session_scope() as ses:
                timebase_dt = datetime.fromtimestamp(timebase)
                allowed_destinations, allowed_for_sender = (
                    self._allowed_topic_destinations_for_sender(topic_id, message)
                )
                if not allowed_for_sender:
                    return self._reply(
                        message,
                        my_lxm_dest,
                        "Telemetry request denied: sender is not subscribed to the topic.",
                        topic_id=topic_id,
                        status="denied",
                    )
                teles = self._load_latest_telemetry(
                    ses,
                    start_time=timebase_dt,
                    peer_destinations=allowed_destinations,
                )
                packed_tels = []
                incoming_fields = message.fields if isinstance(message.fields, dict) else {}
                dest = RNS.Destination(
                    message.source.identity,
                    RNS.Destination.OUT,
                    RNS.Destination.SINGLE,
                    "lxmf",
                    "delivery",
                )
                for tel in teles:
                    peer_hash = self._peer_hash_bytes(tel)
                    if peer_hash is None:
                        continue
                    tel_data = self._serialize_telemeter(tel)
                    human_readable_entries.append(
                        {
                            "peer_destination": tel.peer_dest,
                            "timestamp": round(tel.time.timestamp()),
                            "telemetry": self._humanize_telemetry(tel_data),
                        }
                    )
                    packed_tels.append(
                        [
                            peer_hash,
                            round(tel.time.timestamp()),
                            packb(tel_data, use_bin_type=True),
                            self._build_appearance_payload(tel_data),
                        ]
                    )
                message = LXMF.LXMessage(
                    dest,
                    my_lxm_dest,
                    desired_method=LXMF.LXMessage.DIRECT,
                )
            # Sideband expects telemetry streams as plain lists; avoid
            # double-encoding the field so clients can iterate entries directly.
            message.fields = self._merge_standard_fields(
                source_fields=incoming_fields,
                extra_fields={
                    LXMF.FIELD_TELEMETRY_STREAM: packed_tels,
                    LXMF.FIELD_EVENT: self._build_event_field(
                        event_type="rch.telemetry.response",
                        topic_id=topic_id,
                        status="ok",
                    ),
                },
            )
            message.fields = apply_icon_appearance(message.fields)
            RNS.log(
                f"Sending telemetry snapshot for {len(human_readable_entries)} clients",
                getattr(RNS, "LOG_INFO", 4),
            )
            self._record_event(
                "telemetry_request",
                f"Telemetry request served ({len(human_readable_entries)} entries)",
                metadata={
                    "topic_id": topic_id,
                    "timebase": timebase,
                    "entry_count": len(human_readable_entries),
                },
            )
            return message
        else:
            return None

