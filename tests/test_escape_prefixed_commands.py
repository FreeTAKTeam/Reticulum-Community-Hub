import json

import LXMF
import RNS

from reticulum_telemetry_hub.reticulum_server.__main__ import (
    ESCAPED_COMMAND_PREFIX,
    ReticulumTelemetryHub,
)
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager


def _make_stub_hub():
    """Build a minimal hub instance for delivery callback tests."""
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    hub.lxm_router = type(
        "DummyRouter", (), {"handle_outbound": lambda self, msg: None}
    )()
    hub.my_lxmf_dest = RNS.Destination(
        RNS.Identity(),
        RNS.Destination.IN,
        RNS.Destination.SINGLE,
        "lxmf",
        "delivery",
    )
    hub.connections = {}
    hub.identities = {}
    hub.topic_subscribers = {}
    hub.api = type("DummyAPI", (), {"list_subscribers": lambda self: []})()
    hub.tel_controller = type(
        "DummyTelemetryController", (), {"handle_message": lambda self, message: False}
    )()
    hub._refresh_topic_registry = lambda: None
    hub.send_message = lambda *args, **kwargs: None
    return hub


def test_delivery_callback_parses_plaintext_escape():
    """Ensure plaintext escape bodies become wrapped command payloads."""
    hub = _make_stub_hub()
    received = []

    def record(commands, message):
        received.append(commands)

    hub.command_handler = record

    dest_one = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    payload = f"{ESCAPED_COMMAND_PREFIX}{CommandManager.CMD_JOIN}"
    incoming = LXMF.LXMessage(hub.my_lxmf_dest, dest_one, payload, fields={})
    incoming.signature_validated = True

    hub.delivery_callback(incoming)

    assert received == [[{"Command": CommandManager.CMD_JOIN}]]


def test_delivery_callback_parses_json_escape():
    """Ensure JSON escape bodies are parsed into a command list."""
    hub = _make_stub_hub()
    received = []

    def record(commands, message):
        received.append(commands)

    hub.command_handler = record

    dest_one = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    command_payload = json.dumps({"Command": CommandManager.CMD_LIST_CLIENTS})
    payload = f"{ESCAPED_COMMAND_PREFIX}{command_payload}"
    incoming = LXMF.LXMessage(hub.my_lxmf_dest, dest_one, payload, fields={})
    incoming.signature_validated = True

    hub.delivery_callback(incoming)

    assert received == [[{"Command": CommandManager.CMD_LIST_CLIENTS}]]


def test_delivery_callback_ignores_non_prefixed_bodies():
    """Ensure normal message bodies do not trigger command parsing."""
    hub = _make_stub_hub()
    received = []

    def record(commands, message):
        received.append(commands)

    hub.command_handler = record

    dest_one = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    incoming = LXMF.LXMessage(
        hub.my_lxmf_dest, dest_one, CommandManager.CMD_JOIN, fields={}
    )
    incoming.signature_validated = True

    hub.delivery_callback(incoming)

    assert not received


def test_delivery_callback_suppresses_broadcast_for_escape_commands():
    """Ensure escape-prefixed command bodies are not echoed to clients."""
    hub = _make_stub_hub()
    received = []
    broadcasts: list[tuple] = []

    def record(commands, message):
        received.append(commands)

    def record_broadcast(*args, **kwargs):
        broadcasts.append((args, kwargs))

    hub.command_handler = record
    hub.send_message = record_broadcast

    dest_one = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    payload = f"{ESCAPED_COMMAND_PREFIX}{CommandManager.CMD_JOIN}"
    incoming = LXMF.LXMessage(hub.my_lxmf_dest, dest_one, payload, fields={})
    incoming.signature_validated = True

    hub.delivery_callback(incoming)

    assert received == [[{"Command": CommandManager.CMD_JOIN}]]
    assert broadcasts == []


def test_delivery_callback_suppresses_broadcast_for_lxmf_commands():
    """Ensure LXMF command fields do not broadcast message bodies."""
    hub = _make_stub_hub()
    received = []
    broadcasts: list[tuple] = []

    def record(commands, message):
        received.append(commands)

    def record_broadcast(*args, **kwargs):
        broadcasts.append((args, kwargs))

    hub.command_handler = record
    hub.send_message = record_broadcast

    dest_one = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    command_fields = [{"Command": CommandManager.CMD_LIST_CLIENTS}]
    incoming = LXMF.LXMessage(
        hub.my_lxmf_dest, dest_one, CommandManager.CMD_LIST_CLIENTS, fields={}
    )
    incoming.fields[LXMF.FIELD_COMMANDS] = command_fields
    incoming.signature_validated = True

    hub.delivery_callback(incoming)

    assert received == [command_fields]
    assert broadcasts == []
