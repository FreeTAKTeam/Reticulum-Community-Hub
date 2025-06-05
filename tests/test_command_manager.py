import RNS
import LXMF
from pathlib import Path
from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND


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
