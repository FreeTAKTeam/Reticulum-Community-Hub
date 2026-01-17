from reticulum_telemetry_hub.api import ChatMessage
from reticulum_telemetry_hub.api import ReticulumTelemetryHubAPI
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


def test_chat_message_persistence(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    message = ChatMessage(
        direction="inbound",
        scope="dm",
        state="delivered",
        content="Hello from LXMF",
        source="deadbeef",
    )
    stored = api.record_chat_message(message)
    assert stored.message_id

    messages = api.list_chat_messages(limit=5)
    assert any(entry.message_id == stored.message_id for entry in messages)

    updated = api.update_chat_message_state(stored.message_id or "", "sent")
    assert updated is not None
    assert updated.state == "sent"

    stats = api.chat_message_stats()
    assert stats.get("sent", 0) >= 1


def test_store_uploaded_attachment(tmp_path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    attachment = api.store_uploaded_attachment(
        content=b"payload",
        filename="report.txt",
        media_type="text/plain",
        category="file",
        topic_id="topic-1",
    )

    assert attachment.file_id is not None
    assert attachment.name == "report.txt"
    assert attachment.topic_id == "topic-1"
