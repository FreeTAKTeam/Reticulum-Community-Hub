import LXMF
import RNS

from reticulum_telemetry_hub.api.models import Subscriber, Topic

from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)


def make_message(dest, source, command, **command_fields):
    payload = {PLUGIN_COMMAND: command}
    payload.update(command_fields)
    msg = LXMF.LXMessage(
        dest,
        source,
        fields={LXMF.FIELD_COMMANDS: [payload]},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    msg.pack()
    msg.signature_validated = True
    return msg


def make_command_manager(api):
    class DummyTelemetryController:
        def handle_command(self, command, message, dest):
            return None

    server_dest = RNS.Destination(
        RNS.Identity(),
        RNS.Destination.IN,
        RNS.Destination.SINGLE,
        "lxmf",
        "delivery",
    )
    manager = CommandManager({}, DummyTelemetryController(), server_dest, api)
    return manager, server_dest


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
    expected_identity = RNS.prettyhexrep(client_dest.identity.hash)
    assert reply.content_as_string() == f"{expected_identity}|{{}}"


def test_list_clients_persisted_across_sessions(tmp_path):
    original_router = ReticulumTelemetryHub._shared_lxm_router
    ReticulumTelemetryHub._shared_lxm_router = None
    try:
        hub = ReticulumTelemetryHub("TestHub", str(tmp_path), tmp_path / "identity")
        hub.lxm_router.handle_outbound = lambda m: None

        client_id = RNS.Identity()
        client_dest = RNS.Destination(
            client_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
        )

        join_msg = make_message(hub.my_lxmf_dest, client_dest, CommandManager.CMD_JOIN)
        hub.delivery_callback(join_msg)

        # Recreate the hub to simulate a restart; the API-backed list should persist.
        ReticulumTelemetryHub._shared_lxm_router = None
        existing_destinations = list(getattr(RNS.Transport, "destinations", []))
        RNS.Transport.destinations = []
        try:
            restarted = ReticulumTelemetryHub(
                "TestHub", str(tmp_path), tmp_path / "identity"
            )
            sent = []
            restarted.lxm_router.handle_outbound = lambda m: sent.append(m)

            list_msg = make_message(
                restarted.my_lxmf_dest, client_dest, CommandManager.CMD_LIST_CLIENTS
            )
            restarted.delivery_callback(list_msg)

            assert sent
            reply = sent[-1]
            expected_identity = RNS.prettyhexrep(client_dest.identity.hash)
            assert expected_identity in reply.content_as_string()
        finally:
            RNS.Transport.destinations = existing_destinations
    finally:
        ReticulumTelemetryHub._shared_lxm_router = original_router


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


def test_send_message_filters_by_topic(tmp_path):
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
    topic_id = "topic-alpha"
    hub.topic_subscribers = {topic_id: {dest_one.identity.hash.hex().lower()}}

    hub.send_message("Hello", topic=topic_id)

    assert len(sent) == 1
    assert sent[0].destination_hash == dest_one.identity.hash


def test_send_message_refreshes_topic_registry(tmp_path):
    hub = ReticulumTelemetryHub("TestHub", str(tmp_path), tmp_path / "identity")
    sent: list[LXMF.LXMessage] = []
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
    topic_id = "topic-refresh"

    class DummyAPI:
        def __init__(self) -> None:
            self.calls = 0

        def list_subscribers(self):
            self.calls += 1
            return [
                Subscriber(
                    destination=dest_two.identity.hash.hex(),
                    topic_id=topic_id,
                    metadata={"tag": "beta"},
                )
            ]

    dummy_api = DummyAPI()
    hub.api = dummy_api
    hub.topic_subscribers = {}

    hub.send_message("Hello", topic=topic_id)

    assert len(sent) == 1
    assert sent[0].destination_hash == dest_two.identity.hash
    assert hub.topic_subscribers[topic_id] == {dest_two.identity.hash.hex().lower()}
    assert dummy_api.calls == 1


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
        {
            "handle_message": lambda self, message: telemetry_calls.append(message)
            or True
        },
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


def test_delivery_callback_honors_topic_field():
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
    hub.identities = {}
    hub.topic_subscribers = {"topic-beta": {dest_one.identity.hash.hex().lower()}}
    hub.api = type("DummyAPI", (), {"list_subscribers": lambda self: []})()

    hub.tel_controller = type(
        "DummyController",
        (),
        {"handle_message": lambda self, message: False},
    )()
    hub.command_manager = type(
        "DummyCommands",
        (),
        {"handle_commands": lambda self, commands, message: []},
    )()
    hub.send_message = ReticulumTelemetryHub.send_message.__get__(
        hub, ReticulumTelemetryHub
    )

    incoming = LXMF.LXMessage(
        hub.my_lxmf_dest,
        dest_two,
        "topic-message",
        fields={"TopicID": "topic-beta"},
    )
    incoming.signature_validated = True

    hub.delivery_callback(incoming)

    assert len(router_messages) == 1
    assert router_messages[0].destination_hash == dest_one.identity.hash


def test_list_topics_includes_hint():
    topics = [
        Topic(
            topic_name="Alerts",
            topic_path="/alerts",
            topic_description="Status",
            topic_id="abc",
        ),
        Topic(topic_name="Updates", topic_path="/updates", topic_id="def"),
    ]

    class DummyAPI:
        def list_topics(self):
            return topics

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = make_message(server_dest, client_dest, CommandManager.CMD_LIST_TOPIC)
    command = message.fields[LXMF.FIELD_COMMANDS][0]

    reply = manager.handle_command(command, message)
    payload = reply.content_as_string()
    assert "1. Alerts" in payload
    assert CommandManager.CMD_SUBSCRIBE_TOPIC in payload
    assert "TopicID" in payload


def test_create_topic_uses_api_payload():
    captured = {}

    class DummyAPI:
        def create_topic(self, topic):
            captured["topic"] = topic
            topic.topic_id = "topic-1"
            return topic

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = make_message(
        server_dest,
        client_dest,
        CommandManager.CMD_CREATE_TOPIC,
        TopicName="News",
        TopicPath="/news",
        TopicDescription="Latest",
    )
    command = message.fields[LXMF.FIELD_COMMANDS][0]

    reply = manager.handle_command(command, message)
    assert captured["topic"].topic_name == "News"
    assert captured["topic"].topic_path == "/news"
    payload = reply.content_as_string()
    assert "Topic created" in payload
    assert "topic-1" in payload


def test_subscribe_topic_uses_source_identity():
    captured = {}

    class DummyAPI:
        def subscribe_topic(
            self, topic_id, destination, reject_tests=None, metadata=None
        ):
            captured["topic_id"] = topic_id
            captured["destination"] = destination
            captured["reject_tests"] = reject_tests
            captured["metadata"] = metadata
            return Subscriber(
                destination=destination,
                topic_id=topic_id,
                subscriber_id="sub-1",
                metadata=metadata or {},
            )

    manager, server_dest = make_command_manager(DummyAPI())
    client_identity = RNS.Identity()
    client_dest = RNS.Destination(
        client_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = make_message(
        server_dest,
        client_dest,
        CommandManager.CMD_SUBSCRIBE_TOPIC,
        TopicID="topic-9",
        RejectTests=5,
        Metadata={"app": "demo"},
    )
    command = message.fields[LXMF.FIELD_COMMANDS][0]

    reply = manager.handle_command(command, message)
    expected_destination = CommandManager._identity_hex(client_identity)
    assert captured["topic_id"] == "topic-9"
    assert captured["destination"] == expected_destination
    assert captured["reject_tests"] == 5
    assert captured["metadata"] == {"app": "demo"}
    assert "Subscribed" in reply.content_as_string()


def test_subscribe_topic_allows_zero_reject_tests():
    class DummyAPI:
        def __init__(self) -> None:
            self.latest_reject = None

        def subscribe_topic(
            self,
            topic_id,
            destination,
            reject_tests=None,
            metadata=None,
        ):
            self.latest_reject = reject_tests
            return Subscriber(
                destination=destination,
                topic_id=topic_id,
                subscriber_id="sub-2",
                reject_tests=reject_tests,
                metadata=metadata or {},
            )

    manager, server_dest = make_command_manager(DummyAPI())
    client_identity = RNS.Identity()
    client_dest = RNS.Destination(
        client_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = make_message(
        server_dest,
        client_dest,
        CommandManager.CMD_SUBSCRIBE_TOPIC,
        TopicID="topic-10",
        RejectTests=0,
    )
    command = message.fields[LXMF.FIELD_COMMANDS][0]

    reply = manager.handle_command(command, message)

    assert manager.api.latest_reject == 0
    assert "Subscribed" in reply.content_as_string()
