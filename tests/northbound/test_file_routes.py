"""Tests for file/image routes in the northbound API."""
# pylint: disable=import-error

from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Tuple

from fastapi.testclient import TestClient

from reticulum_telemetry_hub.api.models import FileAttachment
from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
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
        auth=ApiAuth(api_key="secret"),
    )
    return TestClient(app), api


def test_file_routes_return_empty_lists(tmp_path: Path) -> None:
    """Ensure empty file and image lists return empty payloads."""

    client, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    file_response = client.get("/File", headers=headers)
    image_response = client.get("/Image", headers=headers)

    assert file_response.status_code == 200
    assert image_response.status_code == 200
    assert file_response.json() == []
    assert image_response.json() == []


def test_file_routes_return_metadata(tmp_path: Path) -> None:
    """Verify file and image metadata routes return stored attachments."""

    client, api = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    file_path = api._config_manager.config.file_storage_path / "note.txt"  # pylint: disable=protected-access
    file_path.write_text("hello")
    file_record = api.store_file(file_path, media_type="text/plain")
    image_path = api._config_manager.config.image_storage_path / "photo.jpg"  # pylint: disable=protected-access
    image_path.write_bytes(b"img")
    image_record = api.store_image(image_path, media_type="image/jpeg")

    file_response = client.get(f"/File/{file_record.file_id}", headers=headers)
    image_response = client.get(f"/Image/{image_record.file_id}", headers=headers)

    assert file_response.status_code == 200
    assert image_response.status_code == 200
    assert file_response.json()["FileID"] == file_record.file_id
    assert file_response.json()["MediaType"] == "text/plain"
    assert image_response.json()["FileID"] == image_record.file_id
    assert image_response.json()["MediaType"] == "image/jpeg"


def test_file_and_image_routes_paginate_metadata(tmp_path: Path) -> None:
    """Verify file and image list routes return paginated envelopes when requested."""

    client, api = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    for index in range(3):
        file_path = api._config_manager.config.file_storage_path / f"note-{index}.txt"  # pylint: disable=protected-access
        file_path.write_text(f"hello {index}")
        api.store_file(file_path, media_type="text/plain")
    for index in range(2):
        image_path = api._config_manager.config.image_storage_path / f"photo-{index}.jpg"  # pylint: disable=protected-access
        image_path.write_bytes(b"img")
        api.store_image(image_path, media_type="image/jpeg")

    file_response = client.get(
        "/File",
        params={"page": 2, "per_page": 2},
        headers=headers,
    )
    image_response = client.get(
        "/Image",
        params={"page": 1, "per_page": 1},
        headers=headers,
    )

    assert file_response.status_code == 200
    assert image_response.status_code == 200
    file_payload = file_response.json()
    image_payload = image_response.json()
    assert len(file_payload["items"]) == 1
    assert file_payload["total"] == 3
    assert file_payload["has_previous"] is True
    assert len(image_payload["items"]) == 1
    assert image_payload["total"] == 2
    assert image_payload["has_next"] is True


def test_file_routes_patch_topic_association(tmp_path: Path) -> None:
    """Verify file and image routes update attachment topic links."""

    client, api = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    topic = api.create_topic(Topic(topic_name="alerts", topic_path="alerts"))
    file_path = api._config_manager.config.file_storage_path / "topic.txt"  # pylint: disable=protected-access
    file_path.write_text("hello")
    image_path = api._config_manager.config.image_storage_path / "topic.jpg"  # pylint: disable=protected-access
    image_path.write_bytes(b"img")
    file_record = api.store_file(file_path, media_type="text/plain")
    image_record = api.store_image(image_path, media_type="image/jpeg")

    file_response = client.patch(
        f"/File/{file_record.file_id}",
        json={"TopicID": topic.topic_id},
        headers=headers,
    )
    image_response = client.patch(
        f"/Image/{image_record.file_id}",
        json={"TopicID": topic.topic_id},
        headers=headers,
    )

    assert file_response.status_code == 200
    assert image_response.status_code == 200
    assert file_response.json()["TopicID"] == topic.topic_id
    assert image_response.json()["TopicID"] == topic.topic_id


def test_file_routes_patch_missing_entries_return_404(tmp_path: Path) -> None:
    """Ensure attachment topic patch routes return 404 when records are missing."""

    client, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    assert client.patch("/File/999", json={"TopicID": "topic-1"}, headers=headers).status_code == 404
    assert client.patch("/Image/999", json={"TopicID": "topic-1"}, headers=headers).status_code == 404


def test_file_routes_return_raw_bytes(tmp_path: Path) -> None:
    """Ensure raw routes return file bytes and media types."""

    client, api = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    file_path = api._config_manager.config.file_storage_path / "note.txt"  # pylint: disable=protected-access
    file_path.write_bytes(b"payload")
    file_record = api.store_file(file_path, media_type="text/plain")
    image_path = api._config_manager.config.image_storage_path / "photo.jpg"  # pylint: disable=protected-access
    image_path.write_bytes(b"binary")
    image_record = api.store_image(image_path, media_type="image/jpeg")

    file_response = client.get(f"/File/{file_record.file_id}/raw", headers=headers)
    image_response = client.get(f"/Image/{image_record.file_id}/raw", headers=headers)

    assert file_response.status_code == 200
    assert image_response.status_code == 200
    assert file_response.content == b"payload"
    assert image_response.content == b"binary"
    assert "text/plain" in file_response.headers["content-type"]
    assert "image/jpeg" in image_response.headers["content-type"]


def test_file_routes_missing_entries_return_404(tmp_path: Path) -> None:
    """Validate missing file and image lookups return 404 errors."""

    client, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    file_response = client.get("/File/999", headers=headers)
    image_response = client.get("/Image/999", headers=headers)
    file_raw_response = client.get("/File/999/raw", headers=headers)
    image_raw_response = client.get("/Image/999/raw", headers=headers)

    assert file_response.status_code == 404
    assert image_response.status_code == 404
    assert file_raw_response.status_code == 404
    assert image_raw_response.status_code == 404


def test_file_routes_delete_entries(tmp_path: Path) -> None:
    """Ensure delete routes remove files/images from metadata and disk."""

    client, api = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    file_path = api._config_manager.config.file_storage_path / "delete.txt"  # pylint: disable=protected-access
    file_path.write_bytes(b"payload")
    file_record = api.store_file(file_path, media_type="text/plain")
    image_path = api._config_manager.config.image_storage_path / "delete.jpg"  # pylint: disable=protected-access
    image_path.write_bytes(b"image")
    image_record = api.store_image(image_path, media_type="image/jpeg")

    file_response = client.delete(f"/File/{file_record.file_id}", headers=headers)
    image_response = client.delete(f"/Image/{image_record.file_id}", headers=headers)

    assert file_response.status_code == 200
    assert image_response.status_code == 200
    assert file_response.json()["FileID"] == file_record.file_id
    assert image_response.json()["FileID"] == image_record.file_id
    assert not file_path.exists()
    assert not image_path.exists()

    assert client.get(f"/File/{file_record.file_id}", headers=headers).status_code == 404
    assert client.get(f"/Image/{image_record.file_id}", headers=headers).status_code == 404


def test_file_routes_delete_missing_entries_return_404(tmp_path: Path) -> None:
    """Ensure delete routes return 404 when records are missing."""

    client, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    assert client.delete("/File/999", headers=headers).status_code == 404
    assert client.delete("/Image/999", headers=headers).status_code == 404


def test_delete_image_allows_legacy_attachment_paths(tmp_path: Path) -> None:
    """Allow image deletion when the stored record path predates current image roots."""

    client, api = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    legacy_path = legacy_dir / "legacy.jpg"
    legacy_path.write_bytes(b"image")
    timestamp = datetime.now(timezone.utc)
    image_record = api._storage.create_file_record(  # pylint: disable=protected-access
        FileAttachment(
            name="legacy.jpg",
            path=str(legacy_path),
            category="image",
            size=len(b"image"),
            media_type="image/jpeg",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    response = client.delete(f"/Image/{image_record.file_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["FileID"] == image_record.file_id
    assert not legacy_path.exists()


def test_file_routes_require_auth_for_remote_clients(tmp_path: Path) -> None:
    client, _ = _build_client(tmp_path)
    remote_client = TestClient(client.app, client=("198.51.100.10", 50000))

    assert remote_client.get("/File").status_code == 401
    assert remote_client.get("/Image").status_code == 401
