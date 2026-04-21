"""Tests for northbound service helpers."""

from datetime import datetime
from datetime import timezone
from pathlib import Path

from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.api.storage_models import IdentityAnnounceRecord
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.services import NorthboundServices
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


def _build_api(tmp_path: Path) -> ReticulumTelemetryHubAPI:
    """Create an API instance backed by a temp database.

    Args:
        tmp_path (Path): Temporary directory for storage.

    Returns:
        ReticulumTelemetryHubAPI: Configured API service.
    """

    config_manager = HubConfigurationManager(storage_path=tmp_path)
    storage = HubStorage(tmp_path / "hub.sqlite")
    return ReticulumTelemetryHubAPI(config_manager=config_manager, storage=storage)


def test_status_snapshot_includes_counts(tmp_path: Path) -> None:
    """Ensure status snapshots reflect topic counts."""

    api = _build_api(tmp_path)
    api.create_topic(Topic(topic_name="Topic", topic_path="/topic"))
    event_log = EventLog()
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)

    services = NorthboundServices(
        api=api,
        telemetry=telemetry,
        event_log=event_log,
        started_at=datetime.now(timezone.utc),
    )

    snapshot = services.status_snapshot()

    assert snapshot["topics"] == 1
    assert snapshot["clients"] == 0
    assert "runtime" in snapshot


def test_status_snapshot_includes_runtime_provider_payload(tmp_path: Path) -> None:
    """Ensure runtime diagnostics are surfaced in status snapshots."""

    api = _build_api(tmp_path)
    event_log = EventLog()
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    runtime_snapshot = {"counters": {"outbound_enqueued_total": 5}}
    services = NorthboundServices(
        api=api,
        telemetry=telemetry,
        event_log=event_log,
        started_at=datetime.now(timezone.utc),
        runtime_metrics_provider=lambda: runtime_snapshot,
    )

    snapshot = services.status_snapshot()
    diagnostics = services.runtime_diagnostics()

    assert snapshot["runtime"] == runtime_snapshot
    assert diagnostics == runtime_snapshot


def test_resolve_identity_announce_last_seen_prefers_fresh_canonical_record(
    tmp_path: Path,
) -> None:
    """Ensure announce freshness uses the merged canonical identity view."""

    api = _build_api(tmp_path)
    identity = "aa" * 16
    destination = "bb" * 16
    stale_seen = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fresh_seen = datetime(2026, 1, 2, tzinfo=timezone.utc)
    api.record_identity_announce(
        identity,
        display_name="Alpha",
        source_interface="identity",
    )
    api.record_identity_announce(
        destination,
        announced_identity_hash=identity,
        display_name="Alpha",
        source_interface="destination",
    )

    with api._storage._Session() as session:  # pylint: disable=protected-access
        session.get(IdentityAnnounceRecord, identity).last_seen = stale_seen
        session.get(IdentityAnnounceRecord, destination).last_seen = fresh_seen
        session.commit()

    assert api.resolve_identity_announce_last_seen(identity) == fresh_seen


def test_dump_routing_defaults_to_clients(tmp_path: Path) -> None:
    """Ensure routing summaries fall back to clients when no provider."""

    api = _build_api(tmp_path)
    api.join("abc")
    event_log = EventLog()
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)

    services = NorthboundServices(
        api=api,
        telemetry=telemetry,
        event_log=event_log,
        started_at=datetime.now(timezone.utc),
    )

    routing = services.dump_routing()

    assert routing["destinations"] == ["abc"]
