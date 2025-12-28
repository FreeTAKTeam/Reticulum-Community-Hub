import threading

import pytest
from sqlalchemy.exc import OperationalError

from reticulum_telemetry_hub.api import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api import Subscriber
from reticulum_telemetry_hub.api import Topic
from reticulum_telemetry_hub.api.storage import TopicRecord
from reticulum_telemetry_hub.config import HubConfigurationManager


def make_config_manager(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "config.ini").write_text(
        "[app]\n"
        "name = TestHub\n"
        "version = 9.9.9\n"
        "description = Test hub instance\n"
    )
    reticulum_cfg = tmp_path / "reticulum.ini"
    reticulum_cfg.write_text(
        "[reticulum]\n"
        "enable_transport = true\n"
        "share_instance = yes\n"
        "[interfaces]\n"
        "listen_ip = 127.0.0.1\n"
        "listen_port = 9999\n"
    )
    lxmf_cfg = tmp_path / "lxmf.ini"
    lxmf_cfg.write_text(
        "[propagation]\n"
        "enable_node = yes\n"
        "announce_interval = 5\n"
        "[lxmf]\n"
        "display_name = TestRouter\n"
    )
    return HubConfigurationManager(
        storage_path=storage,
        reticulum_config_path=reticulum_cfg,
        lxmf_router_config_path=lxmf_cfg,
    )


def test_topic_crud(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Status", topic_path="/status"))
    assert topic.topic_id
    assert api.retrieve_topic(topic.topic_id).topic_name == "Status"
    updated = api.patch_topic(topic.topic_id, topic_description="System status")
    assert updated.topic_description == "System status"
    topics = api.list_topics()
    assert len(topics) == 1
    deleted = api.delete_topic(topic.topic_id)
    assert deleted.topic_id == topic.topic_id


def test_patch_topic_allows_clearing_description(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(
        Topic(
            topic_name="Status", topic_path="/status", topic_description="System status"
        )
    )

    api.patch_topic(topic.topic_id, topic_description="")
    updated = api.retrieve_topic(topic.topic_id)

    assert updated.topic_description == ""


def test_subscriber_management(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Alerts", topic_path="/alerts"))
    subscriber = api.subscribe_topic(topic.topic_id, destination="abc123")
    assert subscriber.subscriber_id
    retrieved = api.retrieve_subscriber(subscriber.subscriber_id)
    assert retrieved.destination == "abc123"
    api.patch_subscriber(subscriber.subscriber_id, metadata={"level": "high"})
    assert api.retrieve_subscriber(subscriber.subscriber_id).metadata == {
        "level": "high"
    }
    api.patch_subscriber(subscriber.subscriber_id, metadata={})
    assert api.retrieve_subscriber(subscriber.subscriber_id).metadata == {}
    all_subs = api.list_subscribers()
    assert len(all_subs) == 1
    api.delete_subscriber(subscriber.subscriber_id)
    assert api.list_subscribers() == []


def test_patch_subscriber_allows_zero_reject_tests(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Zero", topic_path="/zero"))
    subscriber = api.subscribe_topic(
        topic.topic_id, destination="abc123", reject_tests=3
    )

    api.patch_subscriber(subscriber.subscriber_id, reject_tests=0)
    updated = api.retrieve_subscriber(subscriber.subscriber_id)

    assert updated.reject_tests == 0


def test_client_join_leave(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    assert api.join("identity1")
    assert len(api.list_clients()) == 1
    assert api.leave("identity1")
    assert api.list_clients() == []


def test_concurrent_client_join_and_leave(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))

    worker_count = 20
    iterations = 4
    barrier = threading.Barrier(worker_count)
    errors: list[Exception] = []

    def worker(idx: int):
        identity = f"identity-{idx}"
        try:
            barrier.wait()
            for _ in range(iterations):
                api.join(identity)
            if idx % 2 == 0:
                api.leave(identity)
        except Exception as exc:  # pragma: no cover - defensive capture
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(worker_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    expected_clients = worker_count // 2
    assert len(api.list_clients()) == expected_clients


def test_storage_session_retries_close_failed_sessions(tmp_path, monkeypatch):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    storage = api._storage
    storage._SESSION_RETRIES = 2
    storage._SESSION_BACKOFF = 0

    closed_sessions: list[bool] = []

    class FailingSession:
        def execute(self, _):
            raise OperationalError("SELECT 1", {}, Exception("locked"))

        def close(self):
            closed_sessions.append(True)

    monkeypatch.setattr(storage, "_Session", lambda: FailingSession())

    with pytest.raises(OperationalError):
        storage._acquire_session_with_retry()

    assert len(closed_sessions) == storage._SESSION_RETRIES


def test_get_app_info(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    info = api.get_app_info()
    assert info.storage_path.endswith("storage")
    assert info.file_storage_path.endswith("files")
    assert info.image_storage_path.endswith("images")
    assert info.app_name == "TestHub"
    assert info.app_version == "9.9.9"
    assert info.app_description == "Test hub instance"


def test_persistence_between_instances(tmp_path):
    cfg = make_config_manager(tmp_path)
    api1 = ReticulumTelemetryHubAPI(config_manager=cfg)
    topic = api1.create_topic(Topic(topic_name="Ops", topic_path="/ops"))
    api1.join("identity42")

    # Recreate API with same configuration/DB path
    api2 = ReticulumTelemetryHubAPI(config_manager=cfg)
    assert api2.retrieve_topic(topic.topic_id).topic_name == "Ops"
    clients = api2.list_clients()
    assert any(c.identity == "identity42" for c in clients)


def test_patch_topic_preserves_created_at(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Status", topic_path="/status"))

    with api._storage._Session() as session:
        original_record = session.get(TopicRecord, topic.topic_id)
        original_created_at = original_record.created_at

    api.patch_topic(topic.topic_id, topic_description="Updated status")

    with api._storage._Session() as session:
        updated_record = session.get(TopicRecord, topic.topic_id)
        assert updated_record.description == "Updated status"
        assert updated_record.created_at == original_created_at


def test_join_and_leave_require_identity(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))

    with pytest.raises(ValueError):
        api.join("")

    with pytest.raises(ValueError):
        api.leave("")


def test_create_topic_requires_fields(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))

    with pytest.raises(ValueError):
        api.create_topic(Topic(topic_name="", topic_path=""))


def test_topic_operations_raise_when_missing(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))

    with pytest.raises(KeyError):
        api.retrieve_topic("missing")

    with pytest.raises(KeyError):
        api.delete_topic("missing")


def test_patch_topic_without_updates_returns_original(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Status", topic_path="/status"))

    returned = api.patch_topic(topic.topic_id)

    assert returned.topic_id == topic.topic_id


def test_patch_topic_raises_when_storage_returns_none(tmp_path, monkeypatch):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Status", topic_path="/status"))

    monkeypatch.setattr(api._storage, "update_topic", lambda *_args, **_kwargs: None)

    with pytest.raises(KeyError):
        api.patch_topic(topic.topic_id, topic_name="New Name")


def test_create_subscriber_requires_destination(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))

    with pytest.raises(ValueError):
        api.create_subscriber(Subscriber(destination=""))


def test_subscriber_operations_raise_when_missing(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))

    with pytest.raises(KeyError):
        api.retrieve_subscriber("unknown")

    with pytest.raises(KeyError):
        api.delete_subscriber("unknown")


def test_patch_subscriber_accepts_metadata_with_title_case(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    topic = api.create_topic(Topic(topic_name="Alerts", topic_path="/alerts"))
    subscriber = api.subscribe_topic(topic.topic_id, destination="dest")

    api.patch_subscriber(subscriber.subscriber_id, Metadata={"priority": "high"})
    updated = api.retrieve_subscriber(subscriber.subscriber_id)

    assert updated.metadata == {"priority": "high"}
