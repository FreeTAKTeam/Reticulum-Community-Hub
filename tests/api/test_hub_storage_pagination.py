"""Storage pagination tests for hub list operations."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path

from reticulum_telemetry_hub.api.models import FileAttachment
from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.pagination import PageRequest
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.api.storage_models import ClientRecord


class TrackingHubStorage(HubStorage):
    """Storage subclass that records client announce lookup scopes."""

    def __init__(self, db_path: Path):
        """Create tracking storage backed by a SQLite database."""

        super().__init__(db_path)
        self.announce_identity_scopes: list[tuple[str, ...] | None] = []

    def _identity_announce_map(self, session, identities=None):  # noqa: ANN001
        """Record the identity scope before delegating to the base implementation."""

        scope = None
        if identities is not None:
            scope = tuple(sorted(str(identity) for identity in identities))
        self.announce_identity_scopes.append(scope)
        return super()._identity_announce_map(session, identities=identities)


def test_topic_and_subscriber_pagination_returns_metadata(tmp_path: Path) -> None:
    """Verify SQL-backed topic and subscriber pagination totals."""

    storage = HubStorage(tmp_path / "hub.sqlite")
    for index in range(5):
        topic = storage.create_topic(
            Topic(
                topic_id=f"topic-{index}",
                topic_name=f"topic-{index}",
                topic_path=f"topic-{index}",
            )
        )
        storage.create_subscriber(
            Subscriber(
                subscriber_id=f"subscriber-{index}",
                destination=f"dest-{index}",
                topic_id=topic.topic_id,
            )
        )

    topic_page = storage.paginate_topics(PageRequest(page=2, per_page=2))
    subscriber_page = storage.paginate_subscribers(PageRequest(page=3, per_page=2))

    assert [topic.topic_id for topic in topic_page.items] == ["topic-2", "topic-3"]
    assert topic_page.total == 5
    assert topic_page.total_pages == 3
    assert topic_page.has_next is True
    assert [subscriber.subscriber_id for subscriber in subscriber_page.items] == ["subscriber-4"]
    assert subscriber_page.total == 5
    assert subscriber_page.has_next is False
    assert subscriber_page.has_previous is True


def test_file_record_pagination_filters_by_category(tmp_path: Path) -> None:
    """Verify file-record pagination applies category filters before counting."""

    storage = HubStorage(tmp_path / "hub.sqlite")
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(3):
        storage.create_file_record(
            FileAttachment(
                name=f"file-{index}.txt",
                path=str(tmp_path / f"file-{index}.txt"),
                category="file",
                size=index + 1,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    storage.create_file_record(
        FileAttachment(
            name="image.jpg",
            path=str(tmp_path / "image.jpg"),
            category="image",
            size=10,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    page = storage.paginate_file_records(PageRequest(page=1, per_page=2), category="file")

    assert [attachment.category for attachment in page.items] == ["file", "file"]
    assert page.total == 3
    assert page.total_pages == 2
    assert page.has_next is True


def test_client_pagination_scopes_announce_lookup_to_page(tmp_path: Path) -> None:
    """Verify paginated client queries do not load announce metadata for every client."""

    storage = TrackingHubStorage(tmp_path / "hub.sqlite")
    for identity in ("client-1", "client-2", "client-3"):
        storage.upsert_client(identity)
        storage.upsert_identity_announce(
            identity,
            display_name=f"Display {identity}",
        )
    storage.upsert_identity_announce("outside-client", display_name="Outside")

    with storage._Session() as session:  # pylint: disable=protected-access
        session.get(ClientRecord, "client-1").last_seen = datetime(2026, 1, 1, tzinfo=timezone.utc)
        session.get(ClientRecord, "client-2").last_seen = datetime(2026, 1, 2, tzinfo=timezone.utc)
        session.get(ClientRecord, "client-3").last_seen = datetime(2026, 1, 3, tzinfo=timezone.utc)
        session.commit()

    page = storage.paginate_clients(PageRequest(page=1, per_page=2))

    assert [client.identity for client in page.items] == ["client-3", "client-2"]
    assert [client.display_name for client in page.items] == ["Display client-3", "Display client-2"]
    assert page.total == 3
    assert storage.announce_identity_scopes[-1] == ("client-2", "client-3")
