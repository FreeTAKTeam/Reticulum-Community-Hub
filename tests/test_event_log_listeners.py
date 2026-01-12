"""Tests for event log listeners."""

from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


def test_event_log_listener_receives_events() -> None:
    """Ensure event listeners receive new events."""

    log = EventLog()
    received = []

    def _listener(entry: dict) -> None:
        """Capture event entries.

        Args:
            entry (dict): Event entry payload.
        """

        received.append(entry)

    log.add_listener(_listener)
    log.add_event("type", "message")

    assert len(received) == 1
    assert received[0]["type"] == "type"
