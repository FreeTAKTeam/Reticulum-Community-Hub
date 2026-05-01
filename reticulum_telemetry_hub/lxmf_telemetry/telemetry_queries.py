"""Telemetry query and listing helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy import bindparam
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.telemeter import Telemeter
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.lxmf_propagation import LXMFPropagation
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import SID_LOCATION


class TelemetryQueryMixin:
    """Load and list telemetry records."""

    def _load_telemetry(
        self,
        session: Session,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list[Telemeter]:
        query = session.query(Telemeter)
        if start_time:
            query = query.filter(Telemeter.time >= start_time)
        if end_time:
            query = query.filter(Telemeter.time <= end_time)
        query = query.order_by(Telemeter.time.desc())
        tels = query.options(
            selectinload(Telemeter.sensors),
            selectinload(Telemeter.sensors.of_type(LXMFPropagation)).selectinload(
                LXMFPropagation.peers
            ),
        ).all()
        return tels

    def _latest_telemeter_ids(
        self,
        session: Session,
        *,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        peer_destinations: set[str] | None = None,
    ) -> list[int]:
        """Return ordered latest telemeter IDs for peers with location data."""

        if peer_destinations is not None and not peer_destinations:
            return []

        query = text(
            """
            WITH latest AS (
                SELECT peer_dest, MAX(time) AS max_time
                FROM Telemeter
                WHERE (:start_time IS NULL OR time >= :start_time)
                  AND (:end_time IS NULL OR time <= :end_time)
                  AND (:has_dest_filter = 0 OR peer_dest IN :peer_destinations)
                GROUP BY peer_dest
            )
            SELECT t.id, t.peer_dest
            FROM Telemeter AS t
            JOIN latest
              ON t.peer_dest = latest.peer_dest
             AND t.time = latest.max_time
            WHERE EXISTS (
                SELECT 1
                FROM Sensor AS s
                JOIN Location AS l ON l.id = s.id
                WHERE s.telemeter_id = t.id
                  AND s.sid = :location_sid
                  AND l.latitude IS NOT NULL
                  AND l.longitude IS NOT NULL
            )
            ORDER BY t.time DESC, t.id DESC
            """
        ).bindparams(bindparam("peer_destinations", expanding=True))
        rows = session.execute(
            query,
            {
                "start_time": start_time,
                "end_time": end_time,
                "has_dest_filter": 1 if peer_destinations is not None else 0,
                "peer_destinations": sorted(peer_destinations or []),
                "location_sid": SID_LOCATION,
            },
        ).mappings()

        ordered_ids: list[int] = []
        seen_peers: set[str] = set()
        for row in rows:
            peer_dest = str(row["peer_dest"] or "").strip()
            telemeter_id = row["id"]
            if not peer_dest or peer_dest in seen_peers or not isinstance(telemeter_id, int):
                continue
            seen_peers.add(peer_dest)
            ordered_ids.append(telemeter_id)
        return ordered_ids

    def _load_telemeters_by_ids(
        self, session: Session, telemeter_ids: list[int]
    ) -> list[Telemeter]:
        """Load telemeters and sensors for the provided ordered IDs."""

        if not telemeter_ids:
            return []
        telemeters = (
            session.query(Telemeter)
            .filter(Telemeter.id.in_(telemeter_ids))
            .options(
                selectinload(Telemeter.sensors),
                selectinload(Telemeter.sensors.of_type(LXMFPropagation)).selectinload(
                    LXMFPropagation.peers
                ),
            )
            .all()
        )
        by_id = {telemeter.id: telemeter for telemeter in telemeters}
        return [by_id[telemeter_id] for telemeter_id in telemeter_ids if telemeter_id in by_id]

    def _load_latest_telemetry(
        self,
        session: Session,
        *,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        peer_destinations: set[str] | None = None,
    ) -> list[Telemeter]:
        """Return the newest telemetry row per peer for the requested window."""

        telemeter_ids = self._latest_telemeter_ids(
            session,
            start_time=start_time,
            end_time=end_time,
            peer_destinations=peer_destinations,
        )
        return self._load_telemeters_by_ids(session, telemeter_ids)

    def get_telemetry(
        self, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None
    ) -> list[Telemeter]:
        """Get the telemetry data."""
        with self._session_scope() as ses:
            return self._load_telemetry(ses, start_time, end_time)

    def list_telemetry_entries(
        self, *, since: int, topic_id: str | None = None
    ) -> list[dict[str, object]]:
        """Return telemetry entries as JSON-friendly dictionaries.

        Args:
            since (int): Unix timestamp (seconds) for the earliest telemetry
                records to include.
            topic_id (str | None): Optional topic identifier for filtering.

        Returns:
            list[dict[str, object]]: Telemetry entries formatted for the
                northbound API.

        Raises:
            KeyError: If ``topic_id`` is provided but does not exist.
            ValueError: If topic filtering is requested without an API service.
        """

        timebase_dt = datetime.fromtimestamp(int(since))
        allowed_destinations: set[str] | None = None
        if topic_id:
            if self._api is None:
                raise ValueError("Topic filtering requires an API service")
            subscribers = self._api.list_subscribers_for_topic(topic_id)
            allowed_destinations = {sub.destination for sub in subscribers if sub.destination}

        with self._session_scope() as ses:
            telemeters = self._load_latest_telemetry(
                ses,
                start_time=timebase_dt,
                peer_destinations=allowed_destinations,
            )
            display_name_by_peer: dict[str, str | None] = {}
            peer_destinations = [telemeter.peer_dest for telemeter in telemeters if telemeter.peer_dest]
            if self._api is not None and hasattr(
                self._api, "resolve_identity_display_names_bulk"
            ):
                try:
                    resolver = getattr(self._api, "resolve_identity_display_names_bulk")
                    display_name_by_peer = resolver(peer_destinations) or {}
                except Exception:  # pragma: no cover - defensive
                    display_name_by_peer = {}

            entries: list[dict[str, object]] = []
            for telemeter in telemeters:
                timestamp = int(telemeter.time.timestamp()) if telemeter.time else 0
                payload = self._serialize_telemeter(telemeter)
                readable_payload = self._humanize_telemetry(payload)
                display_name = display_name_by_peer.get(telemeter.peer_dest)
                if display_name is None and self._api is not None and hasattr(
                    self._api, "resolve_identity_display_name"
                ):
                    try:
                        display_name = self._api.resolve_identity_display_name(
                            telemeter.peer_dest
                        )
                    except Exception:  # pragma: no cover - defensive
                        display_name = None
                entries.append(
                    {
                        "peer_destination": telemeter.peer_dest,
                        "timestamp": timestamp,
                        "telemetry": self._json_safe(readable_payload),
                        "display_name": display_name,
                        "identity_label": display_name,
                    }
                )
            return entries

    async def list_telemetry_entries_async(
        self, *, since: int, topic_id: str | None = None
    ) -> list[dict[str, object]]:
        """Return telemetry entries without blocking the event loop.

        This method is intended for async callers (for example websocket
        handlers) and offloads synchronous SQLAlchemy access to a thread.

        Args:
            since (int): Unix timestamp (seconds) for the earliest telemetry
                records to include.
            topic_id (str | None): Optional topic identifier for filtering.

        Returns:
            list[dict[str, object]]: Telemetry entries formatted for async
                northbound consumers.
        """

        return await asyncio.to_thread(
            self.list_telemetry_entries,
            since=since,
            topic_id=topic_id,
        )

