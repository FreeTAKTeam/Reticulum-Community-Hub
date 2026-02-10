import LXMF
import json
import RNS
import pytest
from msgpack import packb
from types import MethodType

from reticulum_telemetry_hub.atak_cot.tak_connector import TakConnector
from reticulum_telemetry_hub.atak_cot import Remarks
from reticulum_telemetry_hub.api import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.models import Subscriber, Topic

from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from tests.test_rth_api import make_config_manager


def make_message(dest, source, command, *, use_str_command=False, **command_fields):
    payload = {"Command": command} if use_str_command else {PLUGIN_COMMAND: command}
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


COMMAND_HANDLER_MAP = [
    (CommandManager.CMD_HELP, "_handle_help"),
    (CommandManager.CMD_EXAMPLES, "_handle_examples"),
    (CommandManager.CMD_JOIN, "_handle_join"),
    (CommandManager.CMD_LEAVE, "_handle_leave"),
    (CommandManager.CMD_LIST_CLIENTS, "_handle_list_clients"),
    (CommandManager.CMD_GET_APP_INFO, "_handle_get_app_info"),
    (CommandManager.CMD_LIST_FILES, "_handle_list_files"),
    (CommandManager.CMD_LIST_IMAGES, "_handle_list_images"),
    (CommandManager.CMD_LIST_TOPIC, "_handle_list_topics"),
    (CommandManager.CMD_CREATE_TOPIC, "_handle_create_topic"),
    (CommandManager.CMD_RETRIEVE_TOPIC, "_handle_retrieve_topic"),
    (CommandManager.CMD_DELETE_TOPIC, "_handle_delete_topic"),
    (CommandManager.CMD_PATCH_TOPIC, "_handle_patch_topic"),
    (CommandManager.CMD_SUBSCRIBE_TOPIC, "_handle_subscribe_topic"),
    (CommandManager.CMD_LIST_SUBSCRIBER, "_handle_list_subscribers"),
    (CommandManager.CMD_CREATE_SUBSCRIBER, "_handle_create_subscriber"),
    (CommandManager.CMD_ADD_SUBSCRIBER, "_handle_create_subscriber"),
    (CommandManager.CMD_RETRIEVE_SUBSCRIBER, "_handle_retrieve_subscriber"),
    (CommandManager.CMD_DELETE_SUBSCRIBER, "_handle_delete_subscriber"),
    (CommandManager.CMD_REMOVE_SUBSCRIBER, "_handle_delete_subscriber"),
    (CommandManager.CMD_PATCH_SUBSCRIBER, "_handle_patch_subscriber"),
    (CommandManager.CMD_RETRIEVE_FILE, "_handle_retrieve_file"),
    (CommandManager.CMD_RETRIEVE_IMAGE, "_handle_retrieve_image"),
]


def test_handle_commands_parses_string_entries():
    class DummyAPI:
        def __init__(self) -> None:
            self.created_topics: list[Topic] = []

        def create_topic(self, topic: Topic) -> Topic:
            topic.topic_id = "topic-from-string"
            self.created_topics.append(topic)
            return topic

        def list_topics(self):
            return []

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    payload = {
        "Command": CommandManager.CMD_CREATE_TOPIC,
        "TopicName": "Alpha",
        "TopicPath": "alpha/path",
    }
    command_blob = json.dumps(payload)
    message = LXMF.LXMessage(
        server_dest,
        client_dest,
        fields={LXMF.FIELD_COMMANDS: [command_blob]},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.pack()
    message.signature_validated = True

    responses = manager.handle_commands(message.fields[LXMF.FIELD_COMMANDS], message)

    assert responses
    reply_text = responses[0].content_as_string()
    assert "Topic created" in reply_text
    assert manager.api.created_topics
    created_topic = manager.api.created_topics[0]
    assert created_topic.topic_name == "Alpha"
    assert created_topic.topic_path == "alpha/path"


def test_handle_commands_parses_sideband_string_entries():
    class DummyAPI:
        def __init__(self) -> None:
            self.created_topics: list[Topic] = []

        def create_topic(self, topic: Topic) -> Topic:
            topic.topic_id = "topic-from-sideband-str"
            self.created_topics.append(topic)
            return topic

        def list_topics(self):
            return []

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    payload = {
        "Command": CommandManager.CMD_CREATE_TOPIC,
        "TopicName": "Alpha",
        "TopicPath": "alpha/path",
    }
    message = LXMF.LXMessage(
        server_dest,
        client_dest,
        fields={LXMF.FIELD_COMMANDS: [{0: json.dumps(payload)}]},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.pack()
    message.signature_validated = True

    responses = manager.handle_commands(message.fields[LXMF.FIELD_COMMANDS], message)

    assert responses
    reply_text = responses[0].content_as_string()
    assert "Topic created" in reply_text
    assert manager.api.created_topics
    created_topic = manager.api.created_topics[0]
    assert created_topic.topic_name == "Alpha"
    assert created_topic.topic_path == "alpha/path"


def test_handle_commands_parses_sideband_dict_entries():
    class DummyAPI:
        def __init__(self) -> None:
            self.created_topics: list[Topic] = []

        def create_topic(self, topic: Topic) -> Topic:
            topic.topic_id = "topic-from-sideband-dict"
            self.created_topics.append(topic)
            return topic

        def list_topics(self):
            return []

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    payload = {
        "Command": CommandManager.CMD_CREATE_TOPIC,
        "TopicName": "Beta",
        "TopicPath": "beta/path",
    }
    message = LXMF.LXMessage(
        server_dest,
        client_dest,
        fields={LXMF.FIELD_COMMANDS: [{0: payload}]},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.pack()
    message.signature_validated = True

    responses = manager.handle_commands(message.fields[LXMF.FIELD_COMMANDS], message)

    assert responses
    reply_text = responses[0].content_as_string()
    assert "Topic created" in reply_text
    assert manager.api.created_topics
    created_topic = manager.api.created_topics[0]
    assert created_topic.topic_name == "Beta"
    assert created_topic.topic_path == "beta/path"


def test_handle_commands_parses_sideband_wrapped_string_commands():
    class DummyAPI:
        def __init__(self) -> None:
            self.created_topics: list[Topic] = []

        def create_topic(self, topic: Topic) -> Topic:
            topic.topic_id = "topic-from-sideband-wrapped-str"
            self.created_topics.append(topic)
            return topic

        def list_topics(self):
            return []

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    payload = {
        "Command": CommandManager.CMD_CREATE_TOPIC,
        "TopicName": "Gamma",
        "TopicPath": "gamma/path",
    }
    wrapped_command = json.dumps({0: json.dumps(payload)})
    message = LXMF.LXMessage(
        server_dest,
        client_dest,
        fields={LXMF.FIELD_COMMANDS: [wrapped_command]},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.pack()
    message.signature_validated = True

    responses = manager.handle_commands(message.fields[LXMF.FIELD_COMMANDS], message)

    assert responses
    reply_text = responses[0].content_as_string()
    assert "Topic created" in reply_text
    assert manager.api.created_topics
    created_topic = manager.api.created_topics[0]
    assert created_topic.topic_name == "Gamma"
    assert created_topic.topic_path == "gamma/path"


def test_handle_commands_parses_sideband_wrapped_object_commands():
    class DummyAPI:
        def __init__(self) -> None:
            self.created_topics: list[Topic] = []

        def create_topic(self, topic: Topic) -> Topic:
            topic.topic_id = "topic-from-sideband-wrapped-obj"
            self.created_topics.append(topic)
            return topic

        def list_topics(self):
            return []

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    payload = {
        "Command": CommandManager.CMD_CREATE_TOPIC,
        "TopicName": "Delta",
        "TopicPath": "delta/path",
    }
    wrapped_command = json.dumps({0: payload})
    message = LXMF.LXMessage(
        server_dest,
        client_dest,
        fields={LXMF.FIELD_COMMANDS: [wrapped_command]},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.pack()
    message.signature_validated = True

    responses = manager.handle_commands(message.fields[LXMF.FIELD_COMMANDS], message)

    assert responses
    reply_text = responses[0].content_as_string()
    assert "Topic created" in reply_text
    assert manager.api.created_topics
    created_topic = manager.api.created_topics[0]
    assert created_topic.topic_name == "Delta"
    assert created_topic.topic_path == "delta/path"


def test_handle_commands_accepts_positional_numeric_payload():
    class DummyAPI:
        def __init__(self) -> None:
            self.created_topics: list[Topic] = []

        def create_topic(self, topic: Topic) -> Topic:
            topic.topic_id = "topic-from-positional"
            self.created_topics.append(topic)
            return topic

        def list_topics(self):
            return []

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    payload = {
        0: CommandManager.CMD_CREATE_TOPIC,
        1: "Weather",
        2: "environment/weather",
    }
    message = LXMF.LXMessage(
        server_dest,
        client_dest,
        fields={LXMF.FIELD_COMMANDS: [payload]},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.pack()
    message.signature_validated = True

    responses = manager.handle_commands(message.fields[LXMF.FIELD_COMMANDS], message)

    assert responses
    reply_text = responses[0].content_as_string()
    assert "Topic created" in reply_text
    created_topic = manager.api.created_topics[0]
    assert created_topic.topic_name == "Weather"
    assert created_topic.topic_path == "environment/weather"


def test_create_topic_interactive_prompt_flow():
    class DummyAPI:
        def __init__(self) -> None:
            self.created: list[Topic] = []

        def create_topic(self, topic: Topic) -> Topic:
            topic.topic_id = "topic-after-prompt"
            self.created.append(topic)
            return topic

        def list_topics(self):
            return []

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    initial_message = make_message(
        server_dest,
        client_dest,
        CommandManager.CMD_CREATE_TOPIC,
        TopicName="Weather",
    )
    prompt_responses = manager.handle_commands(
        initial_message.fields[LXMF.FIELD_COMMANDS], initial_message
    )

    assert prompt_responses
    prompt_text = prompt_responses[0].content_as_string()
    assert "TopicPath" in prompt_text
    assert manager.pending_field_requests

    followup_message = make_message(
        server_dest,
        client_dest,
        CommandManager.CMD_CREATE_TOPIC,
        TopicPath="environment/weather",
    )
    creation_responses = manager.handle_commands(
        followup_message.fields[LXMF.FIELD_COMMANDS], followup_message
    )

    assert creation_responses
    creation_text = creation_responses[0].content_as_string()
    assert "Topic created" in creation_text
    assert manager.api.created
    created_topic = manager.api.created[0]
    assert created_topic.topic_name == "Weather"
    assert created_topic.topic_path == "environment/weather"
    assert manager.pending_field_requests == {}


def test_unknown_command_logs_error(monkeypatch):
    class DummyAPI:
        def list_topics(self):
            return []

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    logs: list[tuple[str, int | None]] = []

    def fake_log(message, level=None):
        logs.append((message, level))

    monkeypatch.setattr(RNS, "log", fake_log)

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = make_message(server_dest, client_dest, "NotACommand")

    responses = manager.handle_commands(message.fields[LXMF.FIELD_COMMANDS], message)

    assert responses
    reply_text = responses[0].content_as_string()
    assert "Unknown command" in reply_text
    assert logs
    relevant = [entry for entry in logs if "NotACommand" in entry[0]]
    assert relevant
    logged_message, logged_level = relevant[-1]
    assert "NotACommand" in logged_message
    assert logged_level == getattr(RNS, "LOG_ERROR", 1)


def test_handle_command_routes_telemetry_request_name():
    class DummyAPI:
        pass

    class DummyTelemetryController:
        def __init__(self) -> None:
            self.calls: list[tuple[dict, LXMF.LXMessage, RNS.Destination]] = []

        def handle_command(self, command, message, dest):
            self.calls.append((command, message, dest))
            return LXMF.LXMessage(
                dest,
                dest,
                "telemetry",
                desired_method=LXMF.LXMessage.DIRECT,
            )

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    server_dest = RNS.Destination(
        RNS.Identity(),
        RNS.Destination.IN,
        RNS.Destination.SINGLE,
        "lxmf",
        "delivery",
    )
    telemetry_controller = DummyTelemetryController()
    manager = CommandManager({}, telemetry_controller, server_dest, DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = make_message(
        server_dest,
        client_dest,
        "TelemetryRequest",
        use_str_command=True,
        **{"1": 1_700_000_000},
    )
    command = message.fields[LXMF.FIELD_COMMANDS][0]

    reply = manager.handle_command(command, message)

    assert reply is not None
    assert reply.content_as_string() == "telemetry"
    assert telemetry_controller.calls


def test_handle_command_routes_telemetry_request_name_with_leading_zero():
    class DummyAPI:
        pass

    class DummyTelemetryController:
        def __init__(self) -> None:
            self.calls: list[tuple[dict, LXMF.LXMessage, RNS.Destination]] = []

        def handle_command(self, command, message, dest):
            self.calls.append((command, message, dest))
            return LXMF.LXMessage(
                dest,
                dest,
                "telemetry",
                desired_method=LXMF.LXMessage.DIRECT,
            )

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    server_dest = RNS.Destination(
        RNS.Identity(),
        RNS.Destination.IN,
        RNS.Destination.SINGLE,
        "lxmf",
        "delivery",
    )
    telemetry_controller = DummyTelemetryController()
    manager = CommandManager({}, telemetry_controller, server_dest, DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = make_message(
        server_dest,
        client_dest,
        "TelemetryRequest",
        use_str_command=True,
        **{"01": 1_700_000_000},
    )
    command = message.fields[LXMF.FIELD_COMMANDS][0]

    reply = manager.handle_command(command, message)

    assert reply is not None
    assert reply.content_as_string() == "telemetry"
    assert telemetry_controller.calls


def test_create_topic_accepts_snake_case_fields():
    class DummyAPI:
        def __init__(self) -> None:
            self.created: list[Topic] = []

        def create_topic(self, topic: Topic) -> Topic:
            topic.topic_id = "topic-snake"
            self.created.append(topic)
            return topic

        def list_topics(self):
            return []

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    message = make_message(
        server_dest,
        client_dest,
        CommandManager.CMD_CREATE_TOPIC,
        topic_name="Alpha",
        topic_path="alpha/path",
    )
    responses = manager.handle_commands(message.fields[LXMF.FIELD_COMMANDS], message)

    assert responses
    reply_text = responses[0].content_as_string()
    assert "Topic created" in reply_text
    created_topic = manager.api.created[0]
    assert created_topic.topic_name == "Alpha"
    assert created_topic.topic_path == "alpha/path"


def test_list_files_and_images_commands(tmp_path):
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    config_manager = make_config_manager(tmp_path)
    api = ReticulumTelemetryHubAPI(config_manager=config_manager)
    file_path = config_manager.config.file_storage_path / "note.txt"
    file_path.write_text("hello attachment")
    file_record = api.store_file(
        file_path, media_type="text/plain", topic_id="topic-file-123"
    )
    image_path = config_manager.config.image_storage_path / "photo.jpg"
    image_bytes = b"img-bytes"
    image_path.write_bytes(image_bytes)
    image_record = api.store_image(
        image_path, media_type="image/jpeg", topic_id="topic-image-456"
    )

    manager, server_dest = make_command_manager(api)
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    list_files_msg = make_message(
        server_dest, client_dest, "listfiles", use_str_command=True
    )
    files_response = manager.handle_command(
        list_files_msg.fields[LXMF.FIELD_COMMANDS][0], list_files_msg
    )
    assert files_response is not None
    assert str(file_record.file_id) in files_response.content_as_string()
    assert "note.txt" in files_response.content_as_string()
    assert "TopicID=topic-file-123" in files_response.content_as_string()

    list_images_msg = make_message(
        server_dest, client_dest, "ListImages", use_str_command=True
    )
    images_response = manager.handle_command(
        list_images_msg.fields[LXMF.FIELD_COMMANDS][0], list_images_msg
    )
    assert images_response is not None
    assert str(image_record.file_id) in images_response.content_as_string()
    assert "photo.jpg" in images_response.content_as_string()
    assert "TopicID=topic-image-456" in images_response.content_as_string()


def test_retrieve_file_includes_attachment_field(tmp_path):
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    config_manager = make_config_manager(tmp_path)
    api = ReticulumTelemetryHubAPI(config_manager=config_manager)
    file_bytes = b"binary-data"
    file_path = config_manager.config.file_storage_path / "sample.bin"
    file_path.write_bytes(file_bytes)
    file_record = api.store_file(file_path, media_type="application/octet-stream")

    manager, server_dest = make_command_manager(api)
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    retrieve_msg = make_message(
        server_dest, client_dest, "retrievefile", FileID=file_record.file_id
    )
    response = manager.handle_command(
        retrieve_msg.fields[LXMF.FIELD_COMMANDS][0], retrieve_msg
    )

    assert response is not None
    assert LXMF.FIELD_FILE_ATTACHMENTS in response.fields
    attachment_payload = response.fields[LXMF.FIELD_FILE_ATTACHMENTS][0]
    if isinstance(attachment_payload, dict):
        assert attachment_payload["data"] == file_bytes
    else:
        assert attachment_payload[1] == file_bytes
    assert str(file_record.file_id) in response.content_as_string()


def test_retrieve_image_includes_image_field(tmp_path):
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    config_manager = make_config_manager(tmp_path)
    api = ReticulumTelemetryHubAPI(config_manager=config_manager)
    image_bytes = b"image-bytes"
    image_path = config_manager.config.image_storage_path / "snapshot.jpg"
    image_path.write_bytes(image_bytes)
    image_record = api.store_image(image_path, media_type="image/jpeg")

    manager, server_dest = make_command_manager(api)
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    retrieve_msg = make_message(
        server_dest,
        client_dest,
        CommandManager.CMD_RETRIEVE_IMAGE,
        FileID=image_record.file_id,
    )
    response = manager.handle_command(
        retrieve_msg.fields[LXMF.FIELD_COMMANDS][0], retrieve_msg
    )

    assert response is not None
    assert LXMF.FIELD_IMAGE in response.fields
    image_field = response.fields[LXMF.FIELD_IMAGE]
    if isinstance(image_field, dict):
        assert image_field["data"] == image_bytes
    elif isinstance(image_field, (list, tuple)):
        assert image_field[1] == image_bytes
    else:
        assert image_field == image_bytes
    assert LXMF.FIELD_FILE_ATTACHMENTS in response.fields
    attachment_payload = response.fields[LXMF.FIELD_FILE_ATTACHMENTS][0]
    if isinstance(attachment_payload, dict):
        assert attachment_payload["data"] == image_bytes
    else:
        assert attachment_payload[1] == image_bytes


def test_retrieve_file_rejects_non_integer_id(tmp_path):
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    manager, server_dest = make_command_manager(api)
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    retrieve_msg = make_message(
        server_dest, client_dest, CommandManager.CMD_RETRIEVE_FILE, FileID="abc"
    )
    response = manager.handle_command(
        retrieve_msg.fields[LXMF.FIELD_COMMANDS][0], retrieve_msg
    )

    assert response is not None
    assert "FileID must be an integer" in response.content_as_string()


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
    hub.wait_for_outbound_flush()

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
    hub.wait_for_outbound_flush()

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
    hub.wait_for_outbound_flush()

    assert len(sent) == 1
    assert sent[0].destination_hash == dest_two.identity.hash


def test_dispatch_northbound_message_prefixes_topic_payload():
    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    sent: dict[str, object] = {}

    class DummyAPI:
        def retrieve_topic(self, topic_id: str) -> Topic:
            return Topic(topic_name="Ops", topic_path="/ops/live", topic_id=topic_id)

        def record_chat_message(self, message):
            message.message_id = "queued-1"
            return message

        def update_chat_message_state(self, message_id: str, state: str):
            assert message_id == "queued-1"
            assert state == "sent"
            return None

    hub.api = DummyAPI()
    hub.display_name = "HubNode"
    hub.event_log = None
    hub.send_message = (
        lambda message, **kwargs: sent.update({"message": message, **kwargs}) or True
    )

    queued = hub.dispatch_northbound_message("status ping", topic_id="topic-live")

    assert queued is not None
    assert queued.content == "/ops/live: HubNode > status ping"
    assert sent["message"] == "/ops/live: HubNode > status ping"
    assert sent["topic"] == "topic-live"


def test_dispatch_northbound_message_keeps_existing_sender_prefix():
    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    sent: dict[str, object] = {}

    class DummyAPI:
        def retrieve_topic(self, topic_id: str) -> Topic:
            return Topic(topic_name="Venezuela", topic_path="var.venezuela", topic_id=topic_id)

        def record_chat_message(self, message):
            message.message_id = "queued-2"
            return message

        def update_chat_message_state(self, message_id: str, state: str):
            assert message_id == "queued-2"
            assert state == "sent"
            return None

    hub.api = DummyAPI()
    hub.display_name = "RTH"
    hub.event_log = None
    hub.send_message = (
        lambda message, **kwargs: sent.update({"message": message, **kwargs}) or True
    )

    queued = hub.dispatch_northbound_message(
        "RCH - win test > this is about Venezuela",
        topic_id="topic-venezuela",
    )

    assert queued is not None
    assert queued.content == "var.venezuela: RCH - win test > this is about Venezuela"
    assert sent["message"] == "var.venezuela: RCH - win test > this is about Venezuela"
    assert sent["topic"] == "topic-venezuela"


def test_help_command_lists_examples(tmp_path):
    class DummyAPI:
        pass

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    manager, server_dest = make_command_manager(DummyAPI())
    client_id = RNS.Identity()
    client_dest = RNS.Destination(
        client_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    help_command = {PLUGIN_COMMAND: CommandManager.CMD_HELP}
    help_msg = make_message(server_dest, client_dest, CommandManager.CMD_HELP)
    reply = manager.handle_command(help_command, help_msg)
    assert reply is not None
    text = reply.content_as_string()
    assert "# Command list" in text
    assert "- `Help`" in text
    assert "- `TelemetryRequest` (`1`)" in text


def test_examples_command_returns_help_payload(tmp_path):
    class DummyAPI:
        pass

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    manager, server_dest = make_command_manager(DummyAPI())
    client_id = RNS.Identity()
    client_dest = RNS.Destination(
        client_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    examples_command = {PLUGIN_COMMAND: CommandManager.CMD_EXAMPLES}
    examples_msg = make_message(server_dest, client_dest, CommandManager.CMD_EXAMPLES)
    reply = manager.handle_command(examples_command, examples_msg)
    assert reply is not None
    text = reply.content_as_string()
    assert "# Command examples" in text
    assert "Description" in text
    assert CommandManager.CMD_CREATE_TOPIC in text
    assert "TelemetryRequest" in text


@pytest.mark.parametrize("command_name, handler_attr", COMMAND_HANDLER_MAP)
@pytest.mark.parametrize("use_string_key", [False, True])
def test_handle_command_dispatches_to_handler(
    command_name, handler_attr, use_string_key
):
    class DummyAPI:
        pass

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    sentinel = object()
    called: list[bool] = []

    def stub(*args, **kwargs):
        called.append(True)
        return sentinel

    setattr(manager, handler_attr, MethodType(stub, manager))
    message = make_message(
        server_dest,
        client_dest,
        command_name,
        use_str_command=use_string_key,
    )
    command = message.fields[LXMF.FIELD_COMMANDS][0]

    response = manager.handle_command(command, message)

    assert response is sentinel
    assert called


def test_handle_command_accepts_retrieve_subscriber_alias():
    class DummyAPI:
        pass

    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    sentinel = object()
    called: list[bool] = []

    def stub(*args, **kwargs):
        called.append(True)
        return sentinel

    manager._handle_retrieve_subscriber = MethodType(stub, manager)
    message = make_message(
        server_dest,
        client_dest,
        "RetrieveSubscriber",
        use_str_command=True,
    )
    command = message.fields[LXMF.FIELD_COMMANDS][0]

    response = manager.handle_command(command, message)

    assert response is sentinel
    assert called
    assert command["Command"] == CommandManager.CMD_RETRIEVE_SUBSCRIBER


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

    hub.send_message = MethodType(ReticulumTelemetryHub.send_message, hub)

    incoming = LXMF.LXMessage(
        hub.my_lxmf_dest,
        dest_one,
        "broadcast",
        fields={LXMF.FIELD_COMMANDS: [{PLUGIN_COMMAND: CommandManager.CMD_JOIN}]},
    )
    incoming.signature_validated = True

    hub.delivery_callback(incoming)
    hub.wait_for_outbound_flush()

    assert command_reply in router_messages
    command_responses = [msg for msg in router_messages if msg is command_reply]
    assert len(command_responses) == 1

    broadcast_payloads = [msg.content_as_string() for msg in router_messages]
    assert all("broadcast" not in payload for payload in broadcast_payloads)
    assert len(router_messages) == 1
    assert telemetry_calls == [incoming]


class DummyPytakClient:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def create_and_send_message(self, message, config=None, parse_inbound=True):
        self.sent.append((message, config, parse_inbound))


def test_delivery_callback_emits_cot_chat_for_valid_message():
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    hub.lxm_router = type(
        "DummyRouter", (), {"handle_outbound": lambda self, msg: None}
    )()
    hub.my_lxmf_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    sender_hash = sender.identity.hash.hex()
    hub.connections = {}
    hub.identities = {sender_hash: "peer-one"}
    hub.topic_subscribers = {}
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
    hub.send_message = MethodType(ReticulumTelemetryHub.send_message, hub)
    client = DummyPytakClient()
    hub.tak_connector = TakConnector(pytak_client=client)

    incoming = LXMF.LXMessage(
        hub.my_lxmf_dest, sender, "Hello world", fields={"TopicID": "chat"}
    )
    incoming.signature_validated = True

    hub.delivery_callback(incoming)
    hub.wait_for_outbound_flush()

    assert client.sent
    event, config, parse_flag = client.sent[0]
    assert event.detail is not None
    assert event.detail.chat is not None
    assert event.detail.chat.chatroom == "chat"
    assert isinstance(event.detail.remarks, Remarks)
    assert "Hello world" in event.detail.remarks.text
    assert config["fts"]["CALLSIGN"] == hub.tak_connector.config.callsign
    assert parse_flag is False


def test_command_handler_handles_missing_command_manager(monkeypatch):
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    logged: list[str] = []
    monkeypatch.setattr(
        RNS,
        "log",
        lambda message, *args, **kwargs: logged.append(str(message)),
    )

    server_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    source_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = LXMF.LXMessage(
        server_dest,
        source_dest,
        fields={LXMF.FIELD_COMMANDS: [{PLUGIN_COMMAND: CommandManager.CMD_HELP}]},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.pack()
    message.signature_validated = True

    responses = ReticulumTelemetryHub.command_handler(
        hub, message.fields[LXMF.FIELD_COMMANDS], message
    )

    assert responses == []
    assert any("Command manager unavailable" in entry for entry in logged)


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
    hub._lookup_identity_label = lambda _source_hash: "user-beta"
    hub.topic_subscribers = {"topic-beta": {dest_one.identity.hash.hex().lower()}}

    class DummyAPI:
        def list_subscribers(self):
            return []

        def retrieve_topic(self, topic_id: str):
            assert topic_id == "topic-beta"
            return Topic(topic_name="Beta", topic_path="/ops/beta", topic_id=topic_id)

    hub.api = DummyAPI()

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
    hub.send_message = MethodType(ReticulumTelemetryHub.send_message, hub)

    incoming = LXMF.LXMessage(
        hub.my_lxmf_dest,
        dest_two,
        "topic-message",
        fields={"TopicID": "topic-beta"},
    )
    incoming.signature_validated = True

    hub.delivery_callback(incoming)
    hub.wait_for_outbound_flush()
    hub.wait_for_outbound_flush()

    assert len(router_messages) == 1
    assert router_messages[0].destination_hash == dest_one.identity.hash
    assert (
        router_messages[0].content_as_string()
        == "/ops/beta: user-beta > topic-message"
    )


def test_delivery_callback_skips_sender_echo():
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
    hub.topic_subscribers = {}
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
    hub.send_message = MethodType(ReticulumTelemetryHub.send_message, hub)

    incoming = LXMF.LXMessage(
        hub.my_lxmf_dest,
        dest_one,
        "hello world",
    )
    incoming.signature_validated = True

    hub.delivery_callback(incoming)
    hub.wait_for_outbound_flush()

    assert len(router_messages) == 1
    assert router_messages[0].destination_hash == dest_two.identity.hash


def test_delivery_callback_skips_telemetry_only_messages():
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    router_messages: list[LXMF.LXMessage] = []

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
    hub.topic_subscribers = {}
    hub.api = type("DummyAPI", (), {"list_subscribers": lambda self: []})()

    hub.tel_controller = type(
        "DummyController",
        (),
        {"handle_message": lambda self, message: True},
    )()
    hub.command_manager = type(
        "DummyCommands",
        (),
        {"handle_commands": lambda self, commands, message: []},
    )()
    hub.send_message = MethodType(ReticulumTelemetryHub.send_message, hub)

    fields = {LXMF.FIELD_TELEMETRY: packb({"sensor": 1}, use_bin_type=True)}
    incoming = LXMF.LXMessage(
        hub.my_lxmf_dest,
        dest_one,
        "Telemetry update",
        fields=fields,
    )
    incoming.signature_validated = True

    hub.delivery_callback(incoming)
    hub.wait_for_outbound_flush()

    assert not router_messages


def test_delivery_callback_replies_help_and_skips_broadcast_when_not_joined():
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    router_messages: list[LXMF.LXMessage] = []

    class DummyRouter:
        def handle_outbound(self, message):
            router_messages.append(message)

    hub.lxm_router = DummyRouter()
    hub.my_lxmf_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    joined_peer = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    hub.connections = {
        joined_peer.identity.hash: joined_peer,
    }
    hub.identities = {}
    hub.topic_subscribers = {}
    hub.api = type(
        "DummyAPI",
        (),
        {
            "list_subscribers": lambda self: [],
            "has_client": lambda self, identity: False,
        },
    )()
    hub.tel_controller = type(
        "DummyController",
        (),
        {"handle_message": lambda self, message: False},
    )()

    def build_help(message):
        return LXMF.LXMessage(sender, hub.my_lxmf_dest, "help-text")

    hub.command_manager = type(
        "DummyCommands",
        (),
        {
            "handle_commands": lambda self, commands, message: [],
            "_handle_help": lambda self, message: build_help(message),
        },
    )()
    hub.send_message = MethodType(ReticulumTelemetryHub.send_message, hub)

    incoming = LXMF.LXMessage(hub.my_lxmf_dest, sender, "hello app")
    incoming.signature_validated = True

    hub.delivery_callback(incoming)
    hub.wait_for_outbound_flush()
    hub.wait_for_outbound_flush()

    assert len(router_messages) == 1
    assert router_messages[0].content_as_string() == "help-text"


def test_delivery_callback_skips_cot_chat_for_telemetry():
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    hub = ReticulumTelemetryHub.__new__(ReticulumTelemetryHub)
    hub.lxm_router = type(
        "DummyRouter", (), {"handle_outbound": lambda self, msg: None}
    )()
    hub.my_lxmf_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    sender = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    hub.connections = {}
    hub.identities = {}
    hub.topic_subscribers = {}
    hub.api = type("DummyAPI", (), {"list_subscribers": lambda self: []})()
    hub.tel_controller = type(
        "DummyController",
        (),
        {"handle_message": lambda self, message: True},
    )()
    hub.command_manager = type(
        "DummyCommands",
        (),
        {"handle_commands": lambda self, commands, message: []},
    )()
    hub.send_message = MethodType(ReticulumTelemetryHub.send_message, hub)
    client = DummyPytakClient()
    hub.tak_connector = TakConnector(pytak_client=client)

    telemetry_fields = {LXMF.FIELD_TELEMETRY: packb({"sensor": 1}, use_bin_type=True)}
    incoming = LXMF.LXMessage(
        hub.my_lxmf_dest, sender, "Telemetry data", fields=telemetry_fields
    )
    incoming.signature_validated = True

    hub.delivery_callback(incoming)
    hub.wait_for_outbound_flush()

    assert not client.sent


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


def test_unknown_command_returns_help_text():
    class DummyAPI:
        pass

    manager, server_dest = make_command_manager(DummyAPI())
    client_dest = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = make_message(server_dest, client_dest, "NotReal")
    command = message.fields[LXMF.FIELD_COMMANDS][0]

    reply = manager.handle_command(command, message)
    text = reply.content_as_string()
    assert text.startswith("Unknown command")
    assert "# Command list" in text
