import LXMF
import RNS

from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from tests.test_command_manager import make_command_manager, make_message


def test_create_subscriber_preserves_zero_reject_tests():
    captured = {}

    class DummyAPI:
        def create_subscriber(self, subscriber):
            captured["subscriber"] = subscriber
            subscriber.subscriber_id = "sub-zero"
            return subscriber

    manager, server_dest = make_command_manager(DummyAPI())
    client_identity = RNS.Identity()
    client_dest = RNS.Destination(
        client_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    message = make_message(
        server_dest,
        client_dest,
        CommandManager.CMD_CREATE_SUBSCRIBER,
        TopicID="topic-22",
        RejectTests=0,
    )
    command = message.fields[LXMF.FIELD_COMMANDS][0]

    reply = manager.handle_command(command, message)

    assert captured["subscriber"].reject_tests == 0
    assert "Subscriber created" in reply.content_as_string()
