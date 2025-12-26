from reticulum_telemetry_hub.api.models import Client
from reticulum_telemetry_hub.api.models import ReticulumInfo
from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.api.models import Topic


def test_topic_from_dict_uses_defaults():
    topic = Topic.from_dict({})

    assert topic.topic_name == ""
    assert topic.topic_path == ""
    assert topic.topic_description == ""


def test_subscriber_from_dict_prefers_reject_tests_key():
    subscriber = Subscriber.from_dict(
        {
            "SubscriberID": "sub-1",
            "Destination": "dest",
            "RejectTests": 0,
            "Metadata": None,
        }
    )

    assert subscriber.reject_tests == 0
    assert subscriber.metadata == {}
    assert subscriber.subscriber_id == "sub-1"


def test_client_touch_updates_last_seen():
    client = Client(identity="abc")
    initial = client.last_seen

    client.touch()

    assert client.last_seen > initial


def test_reticulum_info_to_dict_returns_all_fields():
    info = ReticulumInfo(
        is_transport_enabled=True,
        is_connected_to_shared_instance=False,
        reticulum_config_path="/tmp/r.cfg",
        database_path="/tmp/db",
        storage_path="/tmp/storage",
        app_name="RTH",
        rns_version="1.0",
        lxmf_version="0.9",
        app_version="0.0.0",
        app_description="Reticulum Telemetry Hub instance",
    )

    result = info.to_dict()

    assert result["rns_version"] == "1.0"
    assert result["app_version"] == "0.0.0"
    assert result["storage_path"] == "/tmp/storage"
    assert result["app_name"] == "RTH"
    assert result["app_description"] == "Reticulum Telemetry Hub instance"
