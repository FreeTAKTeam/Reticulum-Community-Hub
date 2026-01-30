import LXMF
import RNS

from reticulum_telemetry_hub.api import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from tests.test_rth_api import make_config_manager


def ensure_reticulum() -> None:
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()


def build_manager(api: ReticulumTelemetryHubAPI) -> tuple[CommandManager, RNS.Destination]:
    class DummyTelemetryController:
        def handle_command(self, command, message, dest):  # noqa: ANN001
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


def make_message(
    server_dest: RNS.Destination, client_dest: RNS.Destination, payload: dict
) -> LXMF.LXMessage:
    message = LXMF.LXMessage(
        server_dest,
        client_dest,
        fields={LXMF.FIELD_COMMANDS: [payload]},
        desired_method=LXMF.LXMessage.DIRECT,
    )
    message.pack()
    message.signature_validated = True
    return message


def make_client_destination() -> RNS.Destination:
    return RNS.Destination(
        RNS.Identity(),
        RNS.Destination.OUT,
        RNS.Destination.SINGLE,
        "lxmf",
        "delivery",
    )


def test_list_files_and_images_when_empty(tmp_path):
    ensure_reticulum()
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))

    manager, server_dest = build_manager(api)
    client_dest = make_client_destination()

    list_files_msg = make_message(
        server_dest, client_dest, {PLUGIN_COMMAND: CommandManager.CMD_LIST_FILES}
    )
    files_response = manager.handle_command(
        list_files_msg.fields[LXMF.FIELD_COMMANDS][0], list_files_msg
    )

    list_images_msg = make_message(
        server_dest, client_dest, {PLUGIN_COMMAND: CommandManager.CMD_LIST_IMAGES}
    )
    images_response = manager.handle_command(
        list_images_msg.fields[LXMF.FIELD_COMMANDS][0], list_images_msg
    )

    assert files_response is not None
    assert files_response.content_as_string() == "No files stored yet."
    assert images_response is not None
    assert images_response.content_as_string() == "No images stored yet."


def test_retrieve_file_prompts_for_missing_id(tmp_path):
    ensure_reticulum()
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    manager, server_dest = build_manager(api)
    client_dest = make_client_destination()

    retrieve_msg = make_message(
        server_dest,
        client_dest,
        {PLUGIN_COMMAND: CommandManager.CMD_RETRIEVE_FILE},
    )
    response = manager.handle_command(
        retrieve_msg.fields[LXMF.FIELD_COMMANDS][0], retrieve_msg
    )

    assert response is not None
    content = response.content_as_string()
    assert "missing required fields" in content
    assert "FileID" in content


def test_retrieve_file_supports_camel_case_id(tmp_path):
    ensure_reticulum()
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    file_path = api._config_manager.config.file_storage_path / "camel.bin"  # pylint: disable=protected-access
    file_bytes = b"camel"
    file_path.write_bytes(file_bytes)
    file_record = api.store_file(file_path)

    manager, server_dest = build_manager(api)
    client_dest = make_client_destination()
    retrieve_msg = make_message(
        server_dest,
        client_dest,
        {PLUGIN_COMMAND: CommandManager.CMD_RETRIEVE_FILE, "fileId": file_record.file_id},
    )

    response = manager.handle_command(
        retrieve_msg.fields[LXMF.FIELD_COMMANDS][0], retrieve_msg
    )

    assert response is not None
    attachment_payload = response.fields[LXMF.FIELD_FILE_ATTACHMENTS][0]
    if isinstance(attachment_payload, dict):
        assert attachment_payload["data"] == file_bytes
    else:
        assert attachment_payload[1] == file_bytes
    assert str(file_record.file_id) in response.content_as_string()


def test_retrieve_image_supports_camel_case_id(tmp_path):
    ensure_reticulum()
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    image_path = api._config_manager.config.image_storage_path / "camel.jpg"  # pylint: disable=protected-access
    image_bytes = b"camel-img"
    image_path.write_bytes(image_bytes)
    image_record = api.store_image(image_path)

    manager, server_dest = build_manager(api)
    client_dest = make_client_destination()
    retrieve_msg = make_message(
        server_dest,
        client_dest,
        {PLUGIN_COMMAND: CommandManager.CMD_RETRIEVE_IMAGE, "imageId": image_record.file_id},
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
    attachment_payload = response.fields[LXMF.FIELD_FILE_ATTACHMENTS][0]
    if isinstance(attachment_payload, dict):
        assert attachment_payload["data"] == image_bytes
    else:
        assert attachment_payload[1] == image_bytes


def test_retrieve_file_missing_record_returns_error(tmp_path):
    ensure_reticulum()
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    manager, server_dest = build_manager(api)
    client_dest = make_client_destination()

    retrieve_msg = make_message(
        server_dest,
        client_dest,
        {PLUGIN_COMMAND: CommandManager.CMD_RETRIEVE_FILE, "FileID": 999},
    )
    response = manager.handle_command(
        retrieve_msg.fields[LXMF.FIELD_COMMANDS][0], retrieve_msg
    )

    assert response is not None
    assert "File '999' not found" in response.content_as_string()
    assert set(response.fields.keys()) == {LXMF.FIELD_ICON_APPEARANCE}


def test_retrieve_file_missing_from_disk_returns_helpful_message(tmp_path):
    ensure_reticulum()
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    file_path = api._config_manager.config.file_storage_path / "ghost.bin"  # pylint: disable=protected-access
    file_path.write_text("ghost")
    file_record = api.store_file(file_path)
    file_path.unlink()

    manager, server_dest = build_manager(api)
    client_dest = make_client_destination()
    retrieve_msg = make_message(
        server_dest,
        client_dest,
        {PLUGIN_COMMAND: CommandManager.CMD_RETRIEVE_FILE, "FileID": file_record.file_id},
    )
    response = manager.handle_command(
        retrieve_msg.fields[LXMF.FIELD_COMMANDS][0], retrieve_msg
    )

    assert response is not None
    assert "not found on disk" in response.content_as_string()
    assert LXMF.FIELD_FILE_ATTACHMENTS not in response.fields


def test_retrieve_image_missing_from_disk_returns_helpful_message(tmp_path):
    ensure_reticulum()
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    image_path = api._config_manager.config.image_storage_path / "ghost.jpg"  # pylint: disable=protected-access
    image_path.write_text("ghost-image")
    image_record = api.store_image(image_path)
    image_path.unlink()

    manager, server_dest = build_manager(api)
    client_dest = make_client_destination()
    retrieve_msg = make_message(
        server_dest,
        client_dest,
        {PLUGIN_COMMAND: CommandManager.CMD_RETRIEVE_IMAGE, "FileID": image_record.file_id},
    )
    response = manager.handle_command(
        retrieve_msg.fields[LXMF.FIELD_COMMANDS][0], retrieve_msg
    )

    assert response is not None
    assert "not found on disk" in response.content_as_string()
    assert LXMF.FIELD_IMAGE not in response.fields
    assert LXMF.FIELD_FILE_ATTACHMENTS not in response.fields


def test_retrieve_file_exception_returns_error_message(tmp_path):
    ensure_reticulum()

    class FailingAPI:
        def retrieve_file(self, record_id: int):  # noqa: ANN001
            raise RuntimeError("boom")

        def retrieve_image(self, record_id: int):  # noqa: ANN001
            raise RuntimeError("boom")

    manager, server_dest = build_manager(FailingAPI())
    client_dest = make_client_destination()
    retrieve_msg = make_message(
        server_dest,
        client_dest,
        {PLUGIN_COMMAND: CommandManager.CMD_RETRIEVE_FILE, "FileID": 1},
    )
    responses = manager.handle_commands(
        retrieve_msg.fields[LXMF.FIELD_COMMANDS], retrieve_msg
    )

    assert responses
    assert any("Command failed" in response.content_as_string() for response in responses)
