import RNS
import LXMF
from pathlib import Path
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


def test_interactive_loop_requests_telemetry_for_known_connection(monkeypatch, tmp_path):
    hub = ReticulumTelemetryHub("TestHub", str(tmp_path), tmp_path / "identity")
    sent = []
    hub.lxm_router.handle_outbound = lambda m: sent.append(m)

    dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    hub.connections = {dest.identity.hash: dest}

    inputs = iter(["telemetry", dest.identity.hash.hex(), "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    hub.interactive_loop()

    assert len(sent) == 1
    telemetry_message = sent[0]
    assert telemetry_message.destination_hash == dest.identity.hash
    assert telemetry_message.fields[LXMF.FIELD_COMMANDS][0][
        TelemetryController.TELEMETRY_REQUEST
    ] == 1000000000
