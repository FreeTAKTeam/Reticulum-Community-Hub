"""Database storage helpers for the Reticulum Telemetry Hub API."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import sessionmaker

from .storage_chat import ChatStorageMixin
from .storage_files import ClientFileStorageMixin
from .storage_identity import IdentityStorageMixin
from .storage_maintenance import StorageMaintenanceMixin
from .storage_rights import RightsStorageMixin
from .storage_topics import TopicSubscriberStorageMixin
from .storage_base import HubStorageBase
from .storage_models import Base
from .storage_models import ChatMessageRecord
from .storage_models import ClientRecord
from .storage_models import FileRecord
from .storage_models import IdentityAnnounceRecord
from .storage_models import IdentityCapabilityGrantRecord
from .storage_models import IdentityRemModeRecord
from .storage_models import IdentityStateRecord
from .storage_models import MarkerRecord
from .storage_models import SubscriberRecord
from .storage_models import TopicRecord
from .storage_models import ZoneRecord

__all__ = [
    "Base",
    "ChatMessageRecord",
    "ClientRecord",
    "FileRecord",
    "HubStorage",
    "IdentityAnnounceRecord",
    "IdentityCapabilityGrantRecord",
    "IdentityRemModeRecord",
    "IdentityStateRecord",
    "MarkerRecord",
    "SubscriberRecord",
    "TopicRecord",
    "ZoneRecord",
]


class HubStorage(
    TopicSubscriberStorageMixin,
    ClientFileStorageMixin,
    IdentityStorageMixin,
    RightsStorageMixin,
    ChatStorageMixin,
    StorageMaintenanceMixin,
    HubStorageBase,
):
    """SQLAlchemy-backed persistence layer for the RTH API."""
    _POOL_SIZE = 25
    _POOL_OVERFLOW = 50
    _CONNECT_TIMEOUT_SECONDS = 30
    _session_retries = 3
    _session_backoff = 0.1

    def __init__(self, db_path: Path):
        """Create a storage instance backed by SQLite.

        Args:
            db_path (Path): Path to the SQLite database file.
        """
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = self._create_engine(db_path)
        self._enable_wal_mode()
        Base.metadata.create_all(self._engine)
        self._ensure_file_topic_column()
        self._ensure_chat_delivery_metadata_column()
        self._ensure_identity_announce_columns()
        self._ensure_indexes()
        self._backfill_identity_capability_grants()
        self._session_factory = sessionmaker(  # pylint: disable=invalid-name
            bind=self._engine, expire_on_commit=False
        )

    @property
    def _Session(self):  # pylint: disable=invalid-name
        """Return a session factory for backward compatibility in tests."""
        return self._session_factory

