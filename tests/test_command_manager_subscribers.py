import LXMF
import RNS
import pytest

from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from tests.test_command_manager import make_command_manager, make_message
from tests.test_rth_api import RustTopicSubscriberApi
from tests.test_rth_api import make_config_manager


def _api_for_backend(tmp_path, backend: str):
    if backend == "rust":
        return RustTopicSubscriberApi(tmp_path)
    return ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_create_subscriber_preserves_zero_reject_tests(tmp_path, backend: str):
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    api = _api_for_backend(tmp_path, backend)
    api.create_topic(Topic(topic_name="Ops", topic_path="topic-22", topic_id="topic-22"))
    manager, server_dest = make_command_manager(api)
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

    assert api.list_subscribers()[0].reject_tests == 0
    assert "Subscriber created" in reply.content_as_string()


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_retrieve_subscriber_returns_payload(tmp_path, backend: str):
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    api = _api_for_backend(tmp_path, backend)
    api.create_topic(Topic(topic_name="Ops", topic_path="topic-01", topic_id="topic-01"))
    created = api.create_subscriber(
        Subscriber(
            destination="dest-01",
            topic_id="topic-01",
            subscriber_id="sub-123",
        )
    )
    manager, server_dest = make_command_manager(api)
    client_identity = RNS.Identity()
    client_dest = RNS.Destination(
        client_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )

    message = make_message(
        server_dest,
        client_dest,
        CommandManager.CMD_RETRIEVE_SUBSCRIBER,
        SubscriberID=created.subscriber_id,
    )
    command = message.fields[LXMF.FIELD_COMMANDS][0]

    reply = manager.handle_command(command, message)

    assert f'"SubscriberID": "{created.subscriber_id}"' in reply.content_as_string()
