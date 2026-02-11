"""Tests for file/image routes in the northbound API."""
# pylint: disable=import-error

from pathlib import Path
from typing import Tuple

from fastapi.testclient import TestClient

from reticulum_telemetry_hub.api import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.models import FileAttachment
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.app import create_app
from tests.test_rth_api import make_config_manager


def _build_client(tmp_path: Path) -> Tuple[TestClient, ReticulumTelemetryHubAPI]:
    """Create a TestClient with a configured API instance.

    Args:
        tmp_path (Path): Temporary directory for test storage.

    Returns:
        Tuple[TestClient, ReticulumTelemetryHubAPI]: Client and API instance.
    """

    api = ReticulumTelemetryHubAPI(config_manager=make_config_manager(tmp_path))
    app = create_app(
        api=api,
        telemetry_controller=TelemetryController(db_path=tmp_path / "telemetry.db", api=api),
    )
    return TestClient(app), api


def test_file_routes_return_empty_lists(tmp_path: Path) -> None:
    """Ensure empty file and image lists return empty payloads."""

    client, _ = _build_client(tmp_path)

    file_response = client.get("/File")
    image_response = client.get("/Image")

    assert file_response.status_code == 200
    assert image_response.status_code == 200
    assert file_response.json() == []
    assert image_response.json() == []


def test_file_routes_return_metadata(tmp_path: Path) -> None:
    """Verify file and image metadata routes return stored attachments."""

    client, api = _build_client(tmp_path)
    file_path = api._config_manager.config.file_storage_path / "note.txt"  # pylint: disable=protected-access
    file_path.write_text("hello")
    file_record = api.store_file(file_path, media_type="text/plain")
    image_path = api._config_manager.config.image_storage_path / "photo.jpg"  # pylint: disable=protected-access
    image_path.write_bytes(b"img")
    image_record = api.store_image(image_path, media_type="image/jpeg")

    file_response = client.get(f"/File/{file_record.file_id}")
    image_response = client.get(f"/Image/{image_record.file_id}")

    assert file_response.status_code == 200
    assert image_response.status_code == 200
    assert file_response.json()["FileID"] == file_record.file_id
    assert file_response.json()["MediaType"] == "text/plain"
    assert image_response.json()["FileID"] == image_record.file_id
    assert image_response.json()["MediaType"] == "image/jpeg"


def test_file_routes_return_raw_bytes(tmp_path: Path) -> None:
    """Ensure raw routes return file bytes and media types."""

    client, api = _build_client(tmp_path)
    file_path = api._config_manager.config.file_storage_path / "note.txt"  # pylint: disable=protected-access
    file_path.write_bytes(b"payload")
    file_record = api.store_file(file_path, media_type="text/plain")
    image_path = api._config_manager.config.image_storage_path / "photo.jpg"  # pylint: disable=protected-access
    image_path.write_bytes(b"binary")
    image_record = api.store_image(image_path, media_type="image/jpeg")

    file_response = client.get(f"/File/{file_record.file_id}/raw")
    image_response = client.get(f"/Image/{image_record.file_id}/raw")

    assert file_response.status_code == 200
    assert image_response.status_code == 200
    assert file_response.content == b"payload"
    assert image_response.content == b"binary"
    assert "text/plain" in file_response.headers["content-type"]
    assert "image/jpeg" in image_response.headers["content-type"]


def test_file_routes_missing_entries_return_404(tmp_path: Path) -> None:
    """Validate missing file and image lookups return 404 errors."""

    client, _ = _build_client(tmp_path)

    file_response = client.get("/File/999")
    image_response = client.get("/Image/999")
    file_raw_response = client.get("/File/999/raw")
    image_raw_response = client.get("/Image/999/raw")

    assert file_response.status_code == 404
    assert image_response.status_code == 404
    assert file_raw_response.status_code == 404
    assert image_raw_response.status_code == 404


def test_file_routes_delete_entries(tmp_path: Path) -> None:
    """Ensure delete routes remove files/images from metadata and disk."""

    client, api = _build_client(tmp_path)
    file_path = api._config_manager.config.file_storage_path / "delete.txt"  # pylint: disable=protected-access
    file_path.write_bytes(b"payload")
    file_record = api.store_file(file_path, media_type="text/plain")
    image_path = api._config_manager.config.image_storage_path / "delete.jpg"  # pylint: disable=protected-access
    image_path.write_bytes(b"image")
    image_record = api.store_image(image_path, media_type="image/jpeg")

    file_response = client.delete(f"/File/{file_record.file_id}")
    image_response = client.delete(f"/Image/{image_record.file_id}")

    assert file_response.status_code == 200
    assert image_response.status_code == 200
    assert file_response.json()["FileID"] == file_record.file_id
    assert image_response.json()["FileID"] == image_record.file_id
    assert not file_path.exists()
    assert not image_path.exists()

    assert client.get(f"/File/{file_record.file_id}").status_code == 404
    assert client.get(f"/Image/{image_record.file_id}").status_code == 404


def test_file_routes_delete_missing_entries_return_404(tmp_path: Path) -> None:
    """Ensure delete routes return 404 when records are missing."""

    client, _ = _build_client(tmp_path)

    assert client.delete("/File/999").status_code == 404
    assert client.delete("/Image/999").status_code == 404


def test_file_routes_delete_rejects_outside_storage_paths(tmp_path: Path) -> None:
    """Ensure delete routes return 400 for files outside configured storage."""

    client, api = _build_client(tmp_path)
    rogue_file = tmp_path / "outside-file.bin"
    rogue_file.write_bytes(b"payload")
    rogue_image = tmp_path / "outside-image.bin"
    rogue_image.write_bytes(b"payload")

    file_record = api._storage.create_file_record(  # pylint: disable=protected-access
        FileAttachment(
            name="outside-file.bin",
            path=str(rogue_file),
            category="file",
            size=rogue_file.stat().st_size,
            media_type="application/octet-stream",
        )
    )
    image_record = api._storage.create_file_record(  # pylint: disable=protected-access
        FileAttachment(
            name="outside-image.bin",
            path=str(rogue_image),
            category="image",
            size=rogue_image.stat().st_size,
            media_type="image/png",
        )
    )

    file_response = client.delete(f"/File/{file_record.file_id}")
    image_response = client.delete(f"/Image/{image_record.file_id}")

    assert file_response.status_code == 400
    assert image_response.status_code == 400
