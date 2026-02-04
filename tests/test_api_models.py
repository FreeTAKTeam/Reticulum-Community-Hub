from datetime import datetime, timedelta, timezone
from pathlib import Path

from reticulum_telemetry_hub.api.models import Client
from reticulum_telemetry_hub.api.models import FileAttachment
from reticulum_telemetry_hub.api.models import IdentityStatus
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


def test_subscriber_from_dict_accepts_snake_case_keys():
    subscriber = Subscriber.from_dict(
        {
            "destination": "dest-2",
            "topic_id": "topic-123",
            "reject_tests": 1,
            "metadata": {"role": "watcher"},
        }
    )

    assert subscriber.destination == "dest-2"
    assert subscriber.topic_id == "topic-123"
    assert subscriber.reject_tests == 1
    assert subscriber.metadata == {"role": "watcher"}


def test_topic_from_dict_accepts_snake_case_and_sets_id():
    topic = Topic.from_dict(
        {
            "topic_name": "alerts",
            "topic_path": "/alerts",
            "topic_description": "Alert channel",
            "topic_id": "topic-1",
        }
    )

    assert topic.topic_id == "topic-1"
    assert topic.topic_name == "alerts"
    assert topic.topic_path == "/alerts"
    assert topic.topic_description == "Alert channel"


def test_client_touch_updates_last_seen():
    client = Client(identity="abc")
    initial = client.last_seen

    client.touch()

    assert client.last_seen > initial


def test_client_touch_increments_when_clock_does_not_advance(monkeypatch):
    frozen_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    client = Client(identity="abc", last_seen=frozen_time)
    monkeypatch.setattr(
        "reticulum_telemetry_hub.api.models._now", lambda: frozen_time
    )

    client.touch()

    assert client.last_seen == frozen_time + timedelta(microseconds=1)


def test_reticulum_info_to_dict_returns_all_fields():
    info = ReticulumInfo(
        is_transport_enabled=True,
        is_connected_to_shared_instance=False,
        reticulum_config_path="/tmp/r.cfg",
        database_path="/tmp/db",
        storage_path="/tmp/storage",
        file_storage_path="/tmp/storage/files",
        image_storage_path="/tmp/storage/images",
        app_name="RTH",
        rns_version="1.0",
        lxmf_version="0.9",
        app_version="0.0.0",
        app_description="Reticulum Telemetry Hub instance",
        reticulum_destination="deadbeef",
    )

    result = info.to_dict()

    assert result["rns_version"] == "1.0"
    assert result["app_version"] == "0.0.0"
    assert result["storage_path"] == "/tmp/storage"
    assert result["file_storage_path"] == "/tmp/storage/files"
    assert result["image_storage_path"] == "/tmp/storage/images"
    assert result["app_name"] == "RTH"
    assert result["app_description"] == "Reticulum Telemetry Hub instance"
    assert result["reticulum_destination"] == "deadbeef"


def test_file_attachment_to_dict_serializes_fields():
    attachment = FileAttachment(
        name="note.txt",
        path="/tmp/note.txt",
        category="file",
        size=10,
        media_type="text/plain",
    )

    serialized = attachment.to_dict()

    assert serialized["Name"] == "note.txt"
    assert serialized["Path"] == "/tmp/note.txt"
    assert serialized["Category"] == "file"
    assert serialized["Size"] == 10
    assert serialized["MediaType"] == "text/plain"


def test_subscriber_to_dict_sanitizes_metadata():
    subscriber = Subscriber(
        destination="dest",
        topic_id="topic-1",
        metadata={"raw": b"\x01\x02"},
        subscriber_id="sub-1",
    )

    payload = subscriber.to_dict()

    assert payload["Metadata"] == {"raw": "0102"}


def test_client_to_dict_sanitizes_metadata():
    client = Client(
        identity="client-1",
        metadata={"path": Path("C:/tmp/config.ini")},
    )

    payload = client.to_dict()

    assert Path(payload["metadata"]["path"]).as_posix().endswith("tmp/config.ini")


def test_identity_status_to_dict_sanitizes_metadata():
    status = IdentityStatus(
        identity="client-2",
        status="active",
        metadata={"raw": b"\xff"},
    )

    payload = status.to_dict()

    assert payload["Metadata"] == {"raw": "ff"}
