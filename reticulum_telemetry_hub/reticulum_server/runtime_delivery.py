"""Delivery callbacks and receipt handling."""
# ruff: noqa: F403,F405

from __future__ import annotations

import time

import LXMF
import RNS

from reticulum_telemetry_hub.api.models import FileAttachment
import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.internal_adapter import LxmfInbound
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_events import report_nonfatal_exception
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeDeliveryMixin:
    """Delivery callbacks and receipt handling."""

    def delivery_callback(self, message: LXMF.LXMessage):
        """Callback function to handle incoming messages.

        Args:
            message (LXMF.LXMessage): LXMF message object
        """
        try:
            # Format the timestamp of the message
            time_string = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(message.timestamp)
            )
            signature_string = "Signature is invalid, reason undetermined"

            # Determine the signature validation status
            if message.signature_validated:
                signature_string = "Validated"
            elif message.unverified_reason == LXMF.LXMessage.SIGNATURE_INVALID:
                signature_string = "Invalid signature"
                return
            elif message.unverified_reason == LXMF.LXMessage.SOURCE_UNKNOWN:
                signature_string = "Cannot verify, source is unknown"
                return

            # Log the delivery details
            self.log_delivery_details(message, time_string, signature_string)
            self._mark_presence_evidence(self._message_source_hex(message))
            self._handle_lxmf_on_inbound(message)
            envelope_error = self._validate_inbound_delivery_contract(message)
            if envelope_error is not None:
                error_reply = self._reply_message(message, envelope_error)
                if error_reply is not None:
                    try:
                        self.lxm_router.handle_outbound(error_reply)
                    except Exception:
                        pass
                return

            command_payload_present = False
            adapter_commands: list[dict] = []
            sender_joined = False
            attachment_replies: list[LXMF.LXMessage] = []
            stored_attachments: list[FileAttachment] = []
            # Handle the commands
            command_replies: list[LXMF.LXMessage] = []
            if message.signature_validated:
                commands: list[dict] | None = None
                escape_error: str | None = None
                if LXMF.FIELD_COMMANDS in message.fields:
                    command_payload_present = True
                    commands = message.fields[LXMF.FIELD_COMMANDS]
                else:
                    escape_commands, escape_detected, escape_error = (
                        self._parse_escape_prefixed_commands(message)
                    )
                    if escape_detected:
                        command_payload_present = True
                    if escape_commands:
                        commands = escape_commands

                topic_id = self._extract_attachment_topic_id(commands)
                (
                    attachment_replies,
                    stored_attachments,
                ) = self._persist_attachments_from_fields(message, topic_id=topic_id)
                if escape_error:
                    error_reply = self._reply_message(
                        message, f"Command error: {escape_error}"
                    )
                    if error_reply is not None:
                        attachment_replies.append(error_reply)

                if commands:
                    if self._should_ignore_passive_command_payload(commands, message):
                        RNS.log(
                            "Ignored passive background command payload with unknown numeric command key.",
                            getattr(RNS, "LOG_DEBUG", 6),
                        )
                    else:
                        command_replies = self.command_handler(commands, message) or []
                        adapter_commands = list(commands)

            responses = attachment_replies + command_replies
            text_only_replies: list[LXMF.LXMessage] = []
            for response in command_replies:
                response_fields = getattr(response, "fields", None) or {}
                if isinstance(response_fields, dict) and any(
                    key in response_fields
                    for key in (LXMF.FIELD_FILE_ATTACHMENTS, LXMF.FIELD_IMAGE)
                ):
                    text_only = self._reply_message(
                        message, response.content_as_string(), fields={}
                    )
                    if text_only is not None:
                        text_only_replies.append(text_only)

            responses.extend(text_only_replies)
            for response in responses:
                try:
                    self.lxm_router.handle_outbound(response)
                except Exception as exc:  # pragma: no cover - defensive log
                    has_attachment = False
                    response_fields = getattr(response, "fields", None) or {}
                    if isinstance(response_fields, dict):
                        has_attachment = any(
                            key in response_fields
                            for key in (LXMF.FIELD_FILE_ATTACHMENTS, LXMF.FIELD_IMAGE)
                        )
                    report_nonfatal_exception(
                        getattr(self, "event_log", None),
                        "lxmf_runtime_error",
                        f"Failed to send response: {exc}",
                        exc,
                        metadata={
                            "operation": "send_response",
                            "has_attachment": has_attachment,
                        },
                        log_level=getattr(RNS, "LOG_WARNING", 2),
                    )
                    if has_attachment:
                        fallback = self._reply_message(
                            message,
                            "Failed to send attachment response; the file may be too large.",
                        )
                        if fallback is None:
                            continue
                        try:
                            self.lxm_router.handle_outbound(fallback)
                        except Exception as retry_exc:  # pragma: no cover - defensive log
                            report_nonfatal_exception(
                                getattr(self, "event_log", None),
                                "lxmf_runtime_error",
                                f"Failed to send fallback response: {retry_exc}",
                                retry_exc,
                                metadata={
                                    "operation": "send_fallback_response",
                                    "has_attachment": has_attachment,
                                },
                                log_level=getattr(RNS, "LOG_WARNING", 2),
                            )
            if responses:
                command_payload_present = True

            sender_joined = self._sender_is_joined(message)
            telemetry_handled = self.tel_controller.handle_message(message)
            if telemetry_handled:
                RNS.log("Telemetry data saved")

            # Reason: some clients emit background telemetry/control packets
            # without user intent. Those should not trigger the unjoined help flow.
            if (message.content is None or message.content == b"") and not stored_attachments:
                return

            if self._is_telemetry_only(message, telemetry_handled):
                return

            if not sender_joined:
                if command_payload_present:
                    return
                self._reply_with_help(message)
                return

            adapter = getattr(self, "internal_adapter", None)
            if adapter is not None and message.signature_validated:
                try:
                    inbound = LxmfInbound(
                        message_id=self._message_id_hex(message),
                        source_id=self._message_source_hex(message),
                        topic_id=self._extract_target_topic(message.fields),
                        text=self._message_text(message),
                        fields=message.fields or {},
                        commands=adapter_commands,
                    )
                    adapter.handle_inbound(inbound)
                except Exception as exc:  # pragma: no cover - defensive logging
                    RNS.log(
                        f"Internal adapter failed to process inbound message: {exc}",
                        getattr(RNS, "LOG_WARNING", 2),
                    )

            if command_payload_present:
                return

            source = message.get_source()
            source_hash = getattr(source, "hash", None) or message.source_hash
            source_label = self._lookup_identity_label(source_hash)
            topic_id = self._extract_target_topic(message.fields)
            content_text = self._message_text(message)
            try:
                message_time = datetime.fromtimestamp(
                    getattr(message, "timestamp", time.time()),
                    tz=timezone.utc,
                ).replace(tzinfo=None)
            except Exception:
                message_time = _utcnow()

            self._record_message_event(
                content=content_text,
                source_label=source_label,
                source_hash=self._message_source_hex(message),
                topic_id=topic_id,
                timestamp=message_time,
                direction="inbound",
                state="delivered",
                destination=None,
                attachments=stored_attachments,
                message_id=self._message_id_hex(message),
            )

            tak_connector = getattr(self, "tak_connector", None)
            if tak_connector is not None and content_text:
                try:
                    coroutine = tak_connector.send_chat_event(
                        content=content_text,
                        sender_label=source_label,
                        topic_id=topic_id,
                        source_hash=source_hash,
                        timestamp=message_time,
                    )
                    runner = getattr(self, "_tak_async_runner", None)
                    if runner is not None:
                        runner.submit(coroutine)
                    else:
                        _dispatch_coroutine(coroutine)
                except Exception as exc:  # pragma: no cover - defensive log
                    RNS.log(
                        f"Failed to send CoT chat event: {exc}",
                        getattr(RNS, "LOG_WARNING", 2),
                    )

            # Broadcast the message to all connected clients.
            msg = self._format_chat_broadcast_text(
                source_label=source_label,
                content_text=content_text,
                topic_id=topic_id,
            )
            source_hex = self._message_source_hex(message)
            exclude = {source_hex} if source_hex else None
            relay_fields = self._merge_standard_fields(
                source_fields=message.fields,
                extra_fields={
                    LXMF.FIELD_EVENT: self._build_event_field(
                        event_type="rch.message.relay",
                        direction="inbound",
                        topic_id=topic_id,
                        source_hash=source_hex,
                    )
                },
            )
            self.send_message(msg, topic=topic_id, exclude=exclude, fields=relay_fields)
        except Exception as e:
            RNS.log(f"Error: {e}")

