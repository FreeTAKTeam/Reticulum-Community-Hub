from pathlib import Path

import pytest

from reticulum_telemetry_hub.api import ReticulumTelemetryHubAPI
from tests.test_rth_api import make_config_manager


def test_store_and_list_files(tmp_path: Path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    file_path = api._config_manager.config.file_storage_path / "note.txt"  # pylint: disable=protected-access
    file_path.write_text("hello file")

    file_record = api.store_file(file_path, media_type="text/plain")
    image_path = api._config_manager.config.image_storage_path / "photo.jpg"  # pylint: disable=protected-access
    image_path.write_bytes(b"binary-data")
    image_record = api.store_image(image_path, media_type="image/jpeg")

    files = api.list_files()
    images = api.list_images()

    assert file_record.file_id is not None
    assert image_record.file_id is not None
    assert file_record.size == len("hello file")
    assert all(record.category == "file" for record in files)
    assert all(record.category == "image" for record in images)
    assert any(record.file_id == file_record.file_id for record in files)
    assert api.retrieve_file(file_record.file_id).path == str(file_path)
    assert api.retrieve_image(image_record.file_id).path == str(image_path)


def test_store_file_validates_path(tmp_path: Path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))

    with pytest.raises(ValueError):
        api.store_file(tmp_path / "missing.bin")


def test_store_file_rejects_outside_base_path(tmp_path: Path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    outside_path = tmp_path / "outside.bin"
    outside_path.write_text("outside")

    with pytest.raises(ValueError):
        api.store_file(outside_path)


def test_retrieve_image_rejects_file_category(tmp_path: Path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    file_path = api._config_manager.config.file_storage_path / "not-image.txt"  # pylint: disable=protected-access
    file_path.write_text("content")
    file_record = api.store_file(file_path)

    with pytest.raises(KeyError):
        api.retrieve_image(file_record.file_id)


def test_delete_file_and_image_removes_db_and_disk(tmp_path: Path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    file_path = api._config_manager.config.file_storage_path / "delete-note.txt"  # pylint: disable=protected-access
    file_path.write_text("hello")
    file_record = api.store_file(file_path, media_type="text/plain")
    image_path = api._config_manager.config.image_storage_path / "delete-photo.jpg"  # pylint: disable=protected-access
    image_path.write_bytes(b"image-data")
    image_record = api.store_image(image_path, media_type="image/jpeg")

    deleted_file = api.delete_file(file_record.file_id)
    deleted_image = api.delete_image(image_record.file_id)

    assert deleted_file.file_id == file_record.file_id
    assert deleted_image.file_id == image_record.file_id
    assert not Path(deleted_file.path).exists()
    assert not Path(deleted_image.path).exists()

    with pytest.raises(KeyError):
        api.retrieve_file(file_record.file_id)
    with pytest.raises(KeyError):
        api.retrieve_image(image_record.file_id)


def test_delete_file_missing_raises_key_error(tmp_path: Path):
    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))

    with pytest.raises(KeyError):
        api.delete_file(999)


def test_delete_image_tolerates_path_validation_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Delete the metadata record even when path inspection raises ValueError."""

    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    image_path = api._config_manager.config.image_storage_path / "linux-photo.jpg"  # pylint: disable=protected-access
    image_path.write_bytes(b"image-data")
    image_record = api.store_image(image_path, media_type="image/jpeg")

    def raise_path_error(path: Path) -> bool:
        raise ValueError(f"invalid path: {path}")

    monkeypatch.setattr(api._filesystem, "is_file", raise_path_error)  # pylint: disable=protected-access

    deleted_image = api.delete_image(image_record.file_id)

    assert deleted_image.file_id == image_record.file_id
    with pytest.raises(KeyError):
        api.retrieve_image(image_record.file_id)
