"""Mission domain persistence lifecycle and event history helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import timedelta
from typing import Any
from typing import Callable

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.service_constants import _dt
from reticulum_telemetry_hub.mission_domain.service_constants import _utcnow
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class MissionLifecycleMixin:
    """Mission domain persistence lifecycle and event history helpers."""

    def _enable_wal_mode(self) -> None:
        try:
            with self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        except OperationalError:
            return

    @contextmanager
    def _session(self):
        session = self._session_factory()
        try:
            yield session
            session.commit()
            pending_notifications = list(
                session.info.pop(MISSION_CHANGE_LISTENER_KEY, [])
            )
            if pending_notifications:
                self._notify_mission_change_listeners(pending_notifications)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _run_additive_migrations(self) -> None:
        """Apply additive schema updates that SQLAlchemy ``create_all`` cannot handle."""

        self._ensure_mission_change_delta_column()
        self._ensure_log_entry_callsign_column()

    def _ensure_mission_change_delta_column(self) -> None:
        """Ensure the mission-change ``delta`` JSON column exists for legacy databases."""

        with self._engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as conn:
            rows = conn.exec_driver_sql(
                "PRAGMA table_info(r3akt_mission_changes);"
            ).fetchall()
            column_names = {str(row[1]) for row in rows if len(row) > 1}
            if "delta" in column_names:
                return
            conn.exec_driver_sql(
                "ALTER TABLE r3akt_mission_changes ADD COLUMN delta JSON;"
            )

    def _ensure_log_entry_callsign_column(self) -> None:
        """Ensure legacy mission-log tables expose the log-author callsign column."""

        with self._engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as conn:
            rows = conn.exec_driver_sql(
                "PRAGMA table_info(r3akt_log_entries);"
            ).fetchall()
            column_names = {str(row[1]) for row in rows if len(row) > 1}
            if "callsign" in column_names:
                return
            conn.exec_driver_sql(
                "ALTER TABLE r3akt_log_entries ADD COLUMN callsign VARCHAR;"
            )

    def register_mission_change_listener(
        self, listener: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Register a callback fired after mission changes commit."""

        self._mission_change_listeners.append(listener)

        def _remove_listener() -> None:
            if listener in self._mission_change_listeners:
                self._mission_change_listeners.remove(listener)

        return _remove_listener

    def _queue_mission_change_listener_notification(
        self, session: Session, mission_change: dict[str, Any]
    ) -> None:
        queue = session.info.setdefault(MISSION_CHANGE_LISTENER_KEY, [])
        if isinstance(queue, list):
            queue.append(dict(mission_change))

    def _notify_mission_change_listeners(
        self, mission_changes: list[dict[str, Any]]
    ) -> None:
        listeners = list(self._mission_change_listeners)
        if not listeners:
            return
        for mission_change in mission_changes:
            for listener in listeners:
                try:
                    listener(dict(mission_change))
                except Exception:
                    continue

    def _prune_domain_history(self, session: Session) -> None:
        cutoff = _utcnow() - timedelta(days=self._event_retention_days)
        session.query(R3aktDomainEventRecord).filter(
            R3aktDomainEventRecord.created_at < cutoff
        ).delete(synchronize_session=False)
        session.query(R3aktDomainSnapshotRecord).filter(
            R3aktDomainSnapshotRecord.created_at < cutoff
        ).delete(synchronize_session=False)

    def _record_event(
        self,
        session: Session,
        *,
        domain: str,
        aggregate_type: str,
        aggregate_uid: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        session.add(
            R3aktDomainEventRecord(
                event_uid=uuid.uuid4().hex,
                domain=domain,
                aggregate_type=aggregate_type,
                aggregate_uid=aggregate_uid,
                event_type=event_type,
                payload_json=payload,
                created_at=_utcnow(),
            )
        )
        self._prune_domain_history(session)

    def _record_snapshot(
        self,
        session: Session,
        *,
        domain: str,
        aggregate_type: str,
        aggregate_uid: str,
        state: dict[str, Any],
    ) -> None:
        latest = (
            session.query(R3aktDomainSnapshotRecord)
            .filter(
                R3aktDomainSnapshotRecord.domain == domain,
                R3aktDomainSnapshotRecord.aggregate_type == aggregate_type,
                R3aktDomainSnapshotRecord.aggregate_uid == aggregate_uid,
            )
            .order_by(R3aktDomainSnapshotRecord.version.desc())
            .first()
        )
        session.add(
            R3aktDomainSnapshotRecord(
                snapshot_uid=uuid.uuid4().hex,
                domain=domain,
                aggregate_type=aggregate_type,
                aggregate_uid=aggregate_uid,
                version=(int(latest.version) + 1) if latest else 1,
                state_json=state,
                created_at=_utcnow(),
            )
        )
        self._prune_domain_history(session)

    def list_domain_events(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = (
                session.query(R3aktDomainEventRecord)
                .order_by(R3aktDomainEventRecord.created_at.desc())
                .limit(max(1, int(limit)))
                .all()
            )
            return [
                {
                    "event_uid": row.event_uid,
                    "domain": row.domain,
                    "aggregate_type": row.aggregate_type,
                    "aggregate_uid": row.aggregate_uid,
                    "event_type": row.event_type,
                    "payload": dict(row.payload_json or {}),
                    "created_at": _dt(row.created_at),
                }
                for row in rows
            ]

    def list_domain_snapshots(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = (
                session.query(R3aktDomainSnapshotRecord)
                .order_by(R3aktDomainSnapshotRecord.created_at.desc())
                .limit(max(1, int(limit)))
                .all()
            )
            return [
                {
                    "snapshot_uid": row.snapshot_uid,
                    "domain": row.domain,
                    "aggregate_type": row.aggregate_type,
                    "aggregate_uid": row.aggregate_uid,
                    "version": int(row.version or 1),
                    "state": dict(row.state_json or {}),
                    "created_at": _dt(row.created_at),
                }
                for row in rows
            ]

