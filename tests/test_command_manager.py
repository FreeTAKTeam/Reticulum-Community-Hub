import LXMF
import RNS

from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)


def make_message(dest, source, command):
    msg = LXMF.LXMessage(
        dest,
        source,
        fields={LXMF.FIELD_COMMANDS: [{PLUGIN_COMMAND: command}]},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    msg.pack()
    msg.signature_validated = True
    return msg


def test_join_and_list_clients(tmp_path):
    hub = ReticulumTelemetryHub("TestHub", str(tmp_path), tmp_path / "identity")
    sent = []
    hub.lxm_router.handle_outbound = lambda m: sent.append(m)

    client_id = RNS.Identity()
    client_dest = RNS.Destination(
        client_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    join_msg = make_message(hub.my_lxmf_dest, client_dest, CommandManager.CMD_JOIN)
    hub.delivery_callback(join_msg)

    assert client_dest.identity.hash in hub.connections

    list_msg = make_message(
        hub.my_lxmf_dest, client_dest, CommandManager.CMD_LIST_CLIENTS
    )
    hub.delivery_callback(list_msg)

    assert sent
    reply = sent[-1]
    assert reply.content_as_string() == RNS.prettyhexrep(client_dest.identity.hash)


def test_send_message_uses_connection_values(tmp_path):
    hub = ReticulumTelemetryHub("TestHub", str(tmp_path), tmp_path / "identity")
    sent = []
    hub.lxm_router.handle_outbound = lambda m: sent.append(m)

    dest_one = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dest_two = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    hub.connections = {
        dest_one.identity.hash: dest_one,
        dest_two.identity.hash: dest_two,
    }

    hub.send_message("Hello")

    assert len(sent) == 2
    destinations = {msg.destination_hash for msg in sent}
    assert destinations == {dest_one.identity.hash, dest_two.identity.hash}
    assert all(msg.content_as_string() == "Hello" for msg in sent)


def test_delivery_callback_handles_commands_and_broadcasts():
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    router_messages = []

    class DummyRouter:
        def handle_outbound(self, message):
            router_messages.append(message)

    hub.lxm_router = DummyRouter()
    hub.my_lxmf_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    dest_one = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    dest_two = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    hub.connections = {
        dest_one.identity.hash: dest_one,
        dest_two.identity.hash: dest_two,
    }
    hub.identities = {dest_one.hash.hex(): "node-a"}

    telemetry_calls = []
    hub.tel_controller = type(
        "DummyController",
        (),
        {"handle_message": lambda self, message: telemetry_calls.append(message) or True},
    )()

    command_reply = LXMF.LXMessage(dest_one, hub.my_lxmf_dest, "cmd-reply")
    hub.command_manager = type(
        "DummyCommands",
        (),
        {
            "handle_commands": lambda self, commands, message: [command_reply],
        },
    )()

    hub.send_message = ReticulumTelemetryHub.send_message.__get__(
        hub, ReticulumTelemetryHub
    )

    incoming = LXMF.LXMessage(
        hub.my_lxmf_dest,
        dest_one,
        "broadcast",
        fields={LXMF.FIELD_COMMANDS: [{PLUGIN_COMMAND: CommandManager.CMD_JOIN}]},
    )
    incoming.signature_validated = True

    hub.delivery_callback(incoming)

    assert command_reply in router_messages
    command_responses = [msg for msg in router_messages if msg is command_reply]
    assert len(command_responses) == 1

    broadcast_payloads = [msg.content_as_string() for msg in router_messages]
    assert any("node-a > broadcast" in payload for payload in broadcast_payloads)
    assert len(router_messages) == 1 + len(hub.connections)
    assert telemetry_calls == [incoming]
