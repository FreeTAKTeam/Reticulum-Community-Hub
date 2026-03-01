from types import SimpleNamespace

from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub
from reticulum_telemetry_hub.reticulum_server.outbound_queue import OutboundPayload


def _make_payload() -> OutboundPayload:
    return OutboundPayload(
        connection=object(),
        message_text="Test outbound payload",
        destination_hash=b"\x11" * 16,
        destination_hex=(b"\x11" * 16).hex(),
        fields=None,
        chat_message_id="chat-1",
    )


def test_outbound_delivery_receipt_marks_propagated_messages_as_sent():
    events: list[dict[str, object]] = []
    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    hub.event_log = SimpleNamespace(
        add_event=lambda event_type, message, metadata=None: events.append(
            {
                "type": event_type,
                "message": message,
                "metadata": metadata,
            }
        )
    )
    hub._update_outbound_chat_state = lambda **kwargs: {
        "MessageID": "chat-1",
        "State": kwargs["state"],
        "Destination": kwargs["destination"],
    }
    hub._lookup_identity_label = lambda value: "NodeLabel"
    payload = _make_payload()
    payload.delivery_mode = "propagated"
    payload.propagation_node_hex = (b"\x22" * 16).hex()
    payload.attempts = 3

    ReticulumTelemetryHub._handle_outbound_delivery_receipt(
        hub,
        SimpleNamespace(fields=None),
        payload,
    )

    assert len(events) == 1
    assert events[0]["type"] == "message_propagated"
    metadata = events[0]["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["State"] == "sent"
    assert metadata["delivery_method"] == "propagated"
    assert metadata["propagation_node"] == payload.propagation_node_hex
    assert metadata["fallback_reason"] == "direct_delivery_failed"
    assert metadata["direct_attempts"] == 3


def test_outbound_retry_and_local_propagation_events_include_metadata():
    events: list[dict[str, object]] = []
    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    hub.event_log = SimpleNamespace(
        add_event=lambda event_type, message, metadata=None: events.append(
            {
                "type": event_type,
                "message": message,
                "metadata": metadata,
            }
        )
    )
    hub._lookup_identity_label = lambda value: "PeerLabel"
    hub._origin_rch_hex = lambda: (b"\xAA" * 16).hex()
    hub._hub_sender_label = lambda: "Hub"
    hub._extract_target_topic = lambda fields: None
    payload = _make_payload()
    payload.attempts = 1

    ReticulumTelemetryHub._handle_outbound_retry_scheduled(hub, payload)

    payload.delivery_mode = "propagated"
    payload.local_propagation_fallback = True
    payload.attempts = 3
    ReticulumTelemetryHub._handle_outbound_propagation_fallback(hub, payload)

    assert [entry["type"] for entry in events] == [
        "message_delivery_retrying",
        "message_propagation_queued",
    ]
    retry_metadata = events[0]["metadata"]
    assert isinstance(retry_metadata, dict)
    assert retry_metadata["direct_attempts"] == 1
    propagation_metadata = events[1]["metadata"]
    assert isinstance(propagation_metadata, dict)
    assert propagation_metadata["delivery_method"] == "local_propagation_store"
    assert propagation_metadata["fallback_reason"] == "direct_delivery_failed"
    assert propagation_metadata["direct_attempts"] == 3
