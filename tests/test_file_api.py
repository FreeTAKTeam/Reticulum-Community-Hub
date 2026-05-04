from pathlib import Path

import pytest

from reticulum_telemetry_hub.api import ReticulumTelemetryHubAPI
from tests.test_rth_api import RustTopicSubscriberApi
from tests.test_rth_api import make_config_manager


def _api_for_backend(
    tmp_path: Path, backend: str
) -> ReticulumTelemetryHubAPI | RustTopicSubscriberApi:
    if backend == "rust":
        return RustTopicSubscriberApi(tmp_path)
    return ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))


def _attachment_path(
    api: ReticulumTelemetryHubAPI | RustTopicSubscriberApi,
    category: str,
    filename: str,
) -> Path:
    if isinstance(api, ReticulumTelemetryHubAPI):
        if category == "image":
            return api._config_manager.config.image_storage_path / filename  # pylint: disable=protected-access
        return api._config_manager.config.file_storage_path / filename  # pylint: disable=protected-access
    base_path = api._storage_path / ("images" if category == "image" else "files")  # pylint: disable=protected-access
    base_path.mkdir(parents=True, exist_ok=True)
    return base_path / filename


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_store_and_list_files(tmp_path: Path, backend: str):
    api = _api_for_backend(tmp_path, backend)
    file_path = _attachment_path(api, "file", "note.txt")
    file_path.write_text("hello file")

    file_record = api.store_file(file_path, media_type="text/plain")
    image_path = _attachment_path(api, "image", "photo.jpg")
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


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_store_file_validates_path(tmp_path: Path, backend: str):
    api = _api_for_backend(tmp_path, backend)

    with pytest.raises(ValueError):
        api.store_file(tmp_path / "missing.bin")


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_store_file_rejects_outside_base_path(tmp_path: Path, backend: str):
    api = _api_for_backend(tmp_path, backend)
    outside_path = tmp_path / "outside.bin"
    outside_path.write_text("outside")

    with pytest.raises(ValueError):
        api.store_file(outside_path)


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_retrieve_image_rejects_file_category(tmp_path: Path, backend: str):
    api = _api_for_backend(tmp_path, backend)
    file_path = _attachment_path(api, "file", "not-image.txt")
    file_path.write_text("content")
    file_record = api.store_file(file_path)

    with pytest.raises(KeyError):
        api.retrieve_image(file_record.file_id)


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_delete_file_and_image_removes_db_and_disk(tmp_path: Path, backend: str):
    api = _api_for_backend(tmp_path, backend)
    file_path = _attachment_path(api, "file", "delete-note.txt")
    file_path.write_text("hello")
    file_record = api.store_file(file_path, media_type="text/plain")
    image_path = _attachment_path(api, "image", "delete-photo.jpg")
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


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_delete_file_missing_raises_key_error(tmp_path: Path, backend: str):
    api = _api_for_backend(tmp_path, backend)

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
