from reticulum_telemetry_hub.api import ReticulumTelemetryHubAPI, Topic, Subscriber
from reticulum_telemetry_hub.api.storage import TopicRecord
from reticulum_telemetry_hub.config import HubConfigurationManager
def make_config_manager(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
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
        storage_path=storage, reticulum_config_path=reticulum_cfg, lxmf_router_config_path=lxmf_cfg
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
        Topic(topic_name="Status", topic_path="/status", topic_description="System status")
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
    assert api.retrieve_subscriber(subscriber.subscriber_id).metadata == {"level": "high"}
    api.patch_subscriber(subscriber.subscriber_id, metadata={})
    assert api.retrieve_subscriber(subscriber.subscriber_id).metadata == {}
    all_subs = api.list_subscribers()
    assert len(all_subs) == 1
    api.delete_subscriber(subscriber.subscriber_id)
    assert api.list_subscribers() == []


def test_client_join_leave(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    assert api.join("identity1")
    assert len(api.list_clients()) == 1
    assert api.leave("identity1")
    assert api.list_clients() == []


def test_get_app_info(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    info = api.get_app_info()
    assert info.storage_path.endswith("storage")
    assert info.app_version


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
