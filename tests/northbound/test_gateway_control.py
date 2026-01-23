"""Tests for the gateway control surface."""
# pylint: disable=import-error

from datetime import datetime
from datetime import timezone
from types import SimpleNamespace
import threading

from reticulum_telemetry_hub.northbound.gateway import GatewayControl


class DummyHub:
    """Hub stub that records shutdown calls."""

    def __init__(self) -> None:
        self.shutdown_called = False

    def shutdown(self) -> None:
        """Record a shutdown request."""

        self.shutdown_called = True


def test_gateway_control_reports_running_status() -> None:
    """Report running status when the hub thread is alive."""

    stop_event = threading.Event()

    def _wait() -> None:
        stop_event.wait()

    hub_thread = threading.Thread(target=_wait)
    hub_thread.start()
    hub = DummyHub()
    control = GatewayControl(
        hub=hub,
        hub_thread=hub_thread,
        host="127.0.0.1",
        port=8000,
        started_at=datetime.now(timezone.utc),
    )

    payload = control.status()

    assert payload["status"] == "running"
    stop_event.set()
    hub_thread.join(timeout=1)


def test_gateway_control_reports_stopped_status() -> None:
    """Report stopped status when the hub thread is not running."""

    hub = DummyHub()
    hub_thread = threading.Thread(target=lambda: None)
    control = GatewayControl(
        hub=hub,
        hub_thread=hub_thread,
        host="127.0.0.1",
        port=8000,
        started_at=datetime.now(timezone.utc),
    )

    payload = control.status()

    assert payload["status"] == "stopped"


def test_gateway_control_shutdown_sets_flags() -> None:
    """Set shutdown flags and request server exit."""

    stop_event = threading.Event()
    hub_thread = threading.Thread(target=stop_event.wait)
    hub_thread.start()
    hub = DummyHub()
    server = SimpleNamespace(should_exit=False)
    control = GatewayControl(
        hub=hub,
        hub_thread=hub_thread,
        host="127.0.0.1",
        port=8000,
        started_at=datetime.now(timezone.utc),
        server=server,
    )

    control.request_shutdown()

    assert hub.shutdown_called is True
    assert server.should_exit is True
    stop_event.set()
    hub_thread.join(timeout=1)


def test_gateway_control_attach_and_start() -> None:
    """Attach a server instance and accept start requests."""

    hub = DummyHub()
    hub_thread = threading.Thread(target=lambda: None)
    control = GatewayControl(
        hub=hub,
        hub_thread=hub_thread,
        host="127.0.0.1",
        port=8000,
        started_at=datetime.now(timezone.utc),
    )
    server = SimpleNamespace(should_exit=False)

    control.attach_server(server)
    control.request_start()

    assert control.server is server
