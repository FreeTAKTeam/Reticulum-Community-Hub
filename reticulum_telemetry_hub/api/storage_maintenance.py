"""Database engine, schema, index, and normalization helpers."""

from __future__ import annotations

import logging
from pathlib import Path
import uuid

from sqlalchemy import create_engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import QueuePool
from sqlalchemy.sql import text

from .rights_storage_models import SubjectOperationGrantRecord
from .storage_models import IdentityCapabilityGrantRecord
from .storage_models import _utcnow


class StorageMaintenanceMixin:
    """Database engine, schema, index, and normalization helpers."""

    def _create_engine(self, db_path: Path) -> Engine:
        """Build a SQLite engine configured for concurrency.

        Args:
            db_path (Path): Database path for the engine.

        Returns:
            Engine: Configured SQLAlchemy engine.
        """
        return create_engine(
            f"sqlite:///{db_path}",
            connect_args={
                "check_same_thread": False,
                "timeout": self._CONNECT_TIMEOUT_SECONDS,
            },
            poolclass=QueuePool,
            pool_size=self._POOL_SIZE,
            max_overflow=self._POOL_OVERFLOW,
            pool_pre_ping=True,
        )

    def _enable_wal_mode(self) -> None:
        """Enable write-ahead logging on the SQLite connection."""
        try:
            with self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        except OperationalError as exc:
            logging.warning("Failed to enable WAL mode: %s", exc)

    def _ensure_indexes(self) -> None:
        """Create hot-path SQLite indexes for existing databases."""

        statements = (
            "CREATE INDEX IF NOT EXISTS ix_subscribers_topic_id ON subscribers(topic_id);",
            "CREATE INDEX IF NOT EXISTS ix_subscribers_destination ON subscribers(destination);",
            (
                "CREATE INDEX IF NOT EXISTS ix_chat_messages_topic_created_at "
                "ON chat_messages(topic_id, created_at DESC);"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_chat_messages_destination_created_at "
                "ON chat_messages(destination, created_at DESC);"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_chat_messages_source_created_at "
                "ON chat_messages(source, created_at DESC);"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_identity_announces_announced_identity_hash "
                "ON identity_announces(announced_identity_hash);"
            ),
        )
        try:
            with self._engine.begin() as conn:
                for statement in statements:
                    conn.exec_driver_sql(statement)
        except OperationalError as exc:
            logging.warning("Failed to create SQLite indexes: %s", exc)

    def _ensure_identity_announce_columns(self) -> None:
        """Ensure REM announce metadata columns exist on legacy databases."""

        statements = []
        try:
            with self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                result = conn.execute(text("PRAGMA table_info(identity_announces);"))
                column_names = {str(row[1]) for row in result.fetchall()}
                if "announce_capabilities" not in column_names:
                    statements.append(
                        "ALTER TABLE identity_announces ADD COLUMN announce_capabilities JSON;"
                    )
                if "announced_identity_hash" not in column_names:
                    statements.append(
                        "ALTER TABLE identity_announces ADD COLUMN announced_identity_hash VARCHAR;"
                    )
                if "client_type" not in column_names:
                    statements.append(
                        "ALTER TABLE identity_announces ADD COLUMN client_type VARCHAR;"
                    )
                if "last_capability_seen_at" not in column_names:
                    statements.append(
                        "ALTER TABLE identity_announces ADD COLUMN last_capability_seen_at DATETIME;"
                    )
                for statement in statements:
                    conn.execute(text(statement))
                conn.execute(
                    text(
                        "UPDATE identity_announces "
                        "SET announced_identity_hash = destination_hash "
                        "WHERE (source_interface IS NULL OR source_interface = 'identity') "
                        "AND announced_identity_hash IS NULL"
                    )
                )
        except OperationalError as exc:
            logging.warning("Failed to ensure identity_announces REM columns: %s", exc)

    def _backfill_identity_capability_grants(self) -> None:
        """Copy legacy identity capability grants into subject-aware rights."""

        with self._engine.begin() as conn:
            legacy_rows = conn.execute(
                IdentityCapabilityGrantRecord.__table__.select()
            ).mappings()
            for row in legacy_rows:
                identity = str(row["identity"] or "").strip().lower()
                capability = str(row["capability"] or "").strip()
                if not identity or not capability:
                    continue
                insert_values = {
                    "grant_uid": uuid.uuid4().hex,
                    "subject_type": "identity",
                    "subject_id": identity,
                    "operation": capability,
                    "scope_type": "global",
                    "scope_id": "",
                    "granted": bool(row["granted"]),
                    "granted_by": row["granted_by"],
                    "granted_at": row["granted_at"] or _utcnow(),
                    "expires_at": row["expires_at"],
                    "updated_at": row["updated_at"] or _utcnow(),
                }
                stmt = sqlite_insert(SubjectOperationGrantRecord).values(**insert_values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[
                        SubjectOperationGrantRecord.subject_type,
                        SubjectOperationGrantRecord.subject_id,
                        SubjectOperationGrantRecord.operation,
                        SubjectOperationGrantRecord.scope_type,
                        SubjectOperationGrantRecord.scope_id,
                    ],
                    set_={
                        "granted": insert_values["granted"],
                        "granted_by": insert_values["granted_by"],
                        "granted_at": insert_values["granted_at"],
                        "expires_at": insert_values["expires_at"],
                        "updated_at": insert_values["updated_at"],
                    },
                )
                conn.execute(stmt)

    @staticmethod
    def _normalize_subject_type(subject_type: str) -> str:
        normalized_subject_type = str(subject_type or "").strip().lower()
        if normalized_subject_type not in {"identity", "team_member"}:
            raise ValueError("subject_type must be one of: identity, team_member")
        return normalized_subject_type

    @staticmethod
    def _normalize_subject_id(subject_type: str, subject_id: str) -> str:
        normalized_subject_id = str(subject_id or "").strip()
        if not normalized_subject_id:
            raise ValueError("subject_id is required")
        if subject_type == "identity":
            return normalized_subject_id.lower()
        return normalized_subject_id

    @staticmethod
    def _normalize_operation(operation: str) -> str:
        normalized_operation = str(operation or "").strip()
        if not normalized_operation:
            raise ValueError("operation is required")
        return normalized_operation

    @staticmethod
    def _normalize_scope(
        scope_type: str | None,
        scope_id: str | None,
    ) -> tuple[str, str]:
        normalized_scope_type = str(scope_type or "global").strip().lower() or "global"
        if normalized_scope_type == "global":
            return "global", ""
        if normalized_scope_type != "mission":
            raise ValueError("scope_type must be one of: global, mission")
        normalized_scope_id = str(scope_id or "").strip()
        if not normalized_scope_id:
            raise ValueError("scope_id is required for mission scope")
        return normalized_scope_type, normalized_scope_id
