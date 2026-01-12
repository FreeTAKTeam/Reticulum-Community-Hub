"""Core REST routes for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from pathlib import Path
from typing import Callable
from typing import Optional

from fastapi import Body
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import Response
from fastapi import status

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)

from .models import ConfigRollbackPayload
from .services import NorthboundServices


def register_core_routes(
    app: FastAPI,
    *,
    services: NorthboundServices,
    api: ReticulumTelemetryHubAPI,
    telemetry_controller: TelemetryController,
    require_protected: Callable[[], None],
    resolve_openapi_spec: Callable[[], Optional[Path]],
) -> None:
    """Register core REST routes on the FastAPI app.

    Args:
        app (FastAPI): FastAPI application instance.
        services (NorthboundServices): Aggregated services.
        api (ReticulumTelemetryHubAPI): API service instance.
        telemetry_controller (TelemetryController): Telemetry controller instance.
        require_protected (Callable[[], None]): Dependency for protected routes.
        resolve_openapi_spec (Callable[[], Optional[Path]]): OpenAPI spec resolver.

    Returns:
        None: Routes are registered on the application.
    """

    @app.get("/openapi.yaml", include_in_schema=False)
    def openapi_yaml() -> Response:
        """Return the OpenAPI YAML file if available.

        Returns:
            Response: YAML content response.
        """

        spec_path = resolve_openapi_spec()
        if not spec_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="OpenAPI spec not found",
            )
        return Response(spec_path.read_text(encoding="utf-8"), media_type="application/yaml")

    @app.get("/Help")
    def get_help_text() -> Response:
        """Return the list of supported commands.

        Returns:
            Response: Plain text command list.
        """

        return Response(services.help_text(), media_type="text/plain")

    @app.get("/Examples")
    def get_examples_text() -> Response:
        """Return command payload examples.

        Returns:
            Response: Plain text examples.
        """

        return Response(services.examples_text(), media_type="text/plain")

    @app.get("/Status", dependencies=[Depends(require_protected)])
    def get_status() -> dict:
        """Return dashboard status metrics.

        Returns:
            dict: Status payload.
        """

        return services.status_snapshot()

    @app.get("/Events", dependencies=[Depends(require_protected)])
    def get_events() -> list[dict]:
        """Return recent events.

        Returns:
            list[dict]: Event entries.
        """

        return services.list_events()

    @app.get("/Telemetry")
    def get_telemetry(
        since: int = Query(alias="since"),
        topic_id: Optional[str] = Query(default=None, alias="topic_id"),
    ) -> dict:
        """Return telemetry entries since a timestamp.

        Args:
            since (int): Unix timestamp (seconds) for the earliest entries.
            topic_id (Optional[str]): Optional topic filter.

        Returns:
            dict: Telemetry response payload.
        """

        try:
            entries = services.telemetry_entries(since=since, topic_id=topic_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"entries": entries}

    @app.get("/Config", dependencies=[Depends(require_protected)])
    def get_config() -> Response:
        """Return the config.ini payload.

        Returns:
            Response: Plain text configuration payload.
        """

        return Response(api.get_config_text(), media_type="text/plain")

    @app.put("/Config", dependencies=[Depends(require_protected)])
    def apply_config(config_text: str = Body(media_type="text/plain")) -> dict:
        """Apply a new config.ini payload.

        Args:
            config_text (str): Raw config.ini payload.

        Returns:
            dict: Apply result payload.
        """

        result = api.apply_config_text(config_text)
        services.record_event("config_applied", "Configuration applied")
        return result

    @app.post("/Config/Validate", dependencies=[Depends(require_protected)])
    def validate_config(config_text: str = Body(media_type="text/plain")) -> dict:
        """Validate a config.ini payload.

        Args:
            config_text (str): Raw config.ini payload.

        Returns:
            dict: Validation result payload.
        """

        return api.validate_config_text(config_text)

    @app.post("/Config/Rollback", dependencies=[Depends(require_protected)])
    def rollback_config(payload: Optional[ConfigRollbackPayload] = Body(default=None)) -> dict:
        """Rollback config.ini using a backup path.

        Args:
            payload (Optional[ConfigRollbackPayload]): Rollback payload.

        Returns:
            dict: Rollback result payload.
        """

        backup_path = payload.backup_path if payload else None
        result = api.rollback_config_text(backup_path=backup_path)
        services.record_event("config_rolled_back", "Configuration rolled back")
        return result

    @app.post("/Command/FlushTelemetry", dependencies=[Depends(require_protected)])
    def flush_telemetry() -> dict:
        """Flush stored telemetry entries.

        Returns:
            dict: Flush result payload.
        """

        deleted = telemetry_controller.clear_telemetry()
        services.record_event("telemetry_flushed", f"Telemetry flushed ({deleted} rows)")
        return {"deleted": deleted}

    @app.post("/Command/ReloadConfig", dependencies=[Depends(require_protected)])
    def reload_config() -> dict:
        """Reload config.ini from disk.

        Returns:
            dict: Reloaded configuration payload.
        """

        info = services.reload_config()
        services.record_event("config_reloaded", "Configuration reloaded")
        return info.to_dict()

    @app.get("/Command/DumpRouting", dependencies=[Depends(require_protected)])
    def dump_routing() -> dict:
        """Return connected destination hashes.

        Returns:
            dict: Routing summary payload.
        """

        return services.dump_routing()

    @app.get("/Identities", dependencies=[Depends(require_protected)])
    def list_identities() -> list[dict]:
        """Return identity moderation status entries.

        Returns:
            list[dict]: Identity status entries.
        """

        return [status_entry.to_dict() for status_entry in services.list_identity_statuses()]

    @app.post("/Client/{identity}/Ban", dependencies=[Depends(require_protected)])
    def ban_identity(identity: str) -> dict:
        """Ban an identity.

        Args:
            identity (str): Identity to ban.

        Returns:
            dict: Updated identity status.
        """

        status_entry = api.ban_identity(identity)
        services.record_event("identity_banned", f"Identity banned: {identity}")
        return status_entry.to_dict()

    @app.post("/Client/{identity}/Unban", dependencies=[Depends(require_protected)])
    def unban_identity(identity: str) -> dict:
        """Unban an identity.

        Args:
            identity (str): Identity to unban.

        Returns:
            dict: Updated identity status.
        """

        status_entry = api.unban_identity(identity)
        services.record_event("identity_unbanned", f"Identity unbanned: {identity}")
        return status_entry.to_dict()

    @app.post("/Client/{identity}/Blackhole", dependencies=[Depends(require_protected)])
    def blackhole_identity(identity: str) -> dict:
        """Blackhole an identity.

        Args:
            identity (str): Identity to blackhole.

        Returns:
            dict: Updated identity status.
        """

        status_entry = api.blackhole_identity(identity)
        services.record_event("identity_blackholed", f"Identity blackholed: {identity}")
        return status_entry.to_dict()

    @app.post("/RTH")
    def rth_join(identity: str = Query(alias="identity")) -> bool:
        """Join the Reticulum Telemetry Hub.

        Args:
            identity (str): Identity to register.

        Returns:
            bool: ``True`` when the identity is recorded.
        """

        return api.join(identity)

    @app.put("/RTH")
    def rth_leave(identity: str = Query(alias="identity")) -> bool:
        """Leave the Reticulum Telemetry Hub.

        Args:
            identity (str): Identity to remove.

        Returns:
            bool: ``True`` when the identity is removed.
        """

        return api.leave(identity)

    @app.get("/Client", dependencies=[Depends(require_protected)])
    def list_clients() -> list[dict]:
        """List clients.

        Returns:
            list[dict]: Client entries.
        """

        return [client.to_dict() for client in services.list_clients()]

    @app.get("/api/v1/app/info")
    def app_info() -> dict:
        """Return application metadata.

        Returns:
            dict: Application info payload.
        """

        return services.app_info().to_dict()
