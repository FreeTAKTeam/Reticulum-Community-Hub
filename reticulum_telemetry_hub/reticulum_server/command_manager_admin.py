"""Subscriber, identity, config, and diagnostics command handlers."""

from __future__ import annotations

import json
import time

import LXMF

from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND


class CommandAdminMixin:
    """Subscriber, identity, config, and diagnostics command handlers."""

    def _handle_create_subscriber(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        destination = self._field_value(command, "Destination")
        if not destination:
            command = dict(command)
            command["Destination"] = self._sender_key(message)
        missing = self._missing_fields(command, ["Destination"])
        if missing:
            return self._prompt_for_fields(
                self.CMD_CREATE_SUBSCRIBER, missing, message, command
            )
        subscriber = Subscriber.from_dict(command)
        try:
            created = self.api.create_subscriber(subscriber)
        except ValueError as exc:
            return self._reply(message, f"Subscriber creation failed: {exc}")
        payload = json.dumps(created.to_dict(), sort_keys=True)
        self._record_event(
            "subscriber_created",
            f"Subscriber created: {created.subscriber_id}",
        )
        return self._reply(message, f"Subscriber created: {payload}")

    def _handle_retrieve_subscriber(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        subscriber_id = self._extract_subscriber_id(command)
        if not subscriber_id:
            return self._prompt_for_fields(
                self.CMD_RETRIEVE_SUBSCRIBER, ["SubscriberID"], message, command
            )
        try:
            subscriber = self.api.retrieve_subscriber(subscriber_id)
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(subscriber.to_dict(), sort_keys=True)
        return self._reply(message, payload)

    def _handle_delete_subscriber(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        subscriber_id = self._extract_subscriber_id(command)
        if not subscriber_id:
            return self._prompt_for_fields(
                self.CMD_DELETE_SUBSCRIBER, ["SubscriberID"], message, command
            )
        try:
            subscriber = self.api.delete_subscriber(subscriber_id)
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(subscriber.to_dict(), sort_keys=True)
        self._record_event(
            "subscriber_deleted",
            f"Subscriber deleted: {subscriber.subscriber_id}",
        )
        return self._reply(message, f"Subscriber deleted: {payload}")

    def _handle_patch_subscriber(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        subscriber_id = self._extract_subscriber_id(command)
        if not subscriber_id:
            return self._prompt_for_fields(
                self.CMD_PATCH_SUBSCRIBER, ["SubscriberID"], message, command
            )
        updates = {k: v for k, v in command.items() if k != PLUGIN_COMMAND}
        try:
            subscriber = self.api.patch_subscriber(subscriber_id, **updates)
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(subscriber.to_dict(), sort_keys=True)
        self._record_event(
            "subscriber_updated",
            f"Subscriber updated: {subscriber.subscriber_id}",
        )
        return self._reply(message, f"Subscriber updated: {payload}")

    def _handle_status(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Return the dashboard status snapshot."""

        uptime_seconds = int(time.time() - self._start_time)
        status = {
            "uptime_seconds": uptime_seconds,
            "clients": len(self.connections),
            "topics": len(self.api.list_topics()),
            "subscribers": len(self.api.list_subscribers()),
            "files": len(self.api.list_files()),
            "images": len(self.api.list_images()),
            "telemetry": self.tel_controller.telemetry_stats(),
        }
        payload = json.dumps(status, sort_keys=True)
        return self._reply(message, payload)

    def _handle_list_events(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Return recent event entries for the dashboard."""

        events = []
        if self.event_log is not None:
            events = self.event_log.list_events(limit=50)
        payload = json.dumps(events, sort_keys=True)
        return self._reply(message, payload)

    def _handle_ban_identity(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        """Mark an identity as banned."""

        identity = self._extract_identity(command)
        if not identity:
            return self._prompt_for_fields(
                self.CMD_BAN_IDENTITY, ["Identity"], message, command
            )
        status = self.api.ban_identity(identity)
        payload = json.dumps(status.to_dict(), sort_keys=True)
        self._record_event("identity_banned", f"Identity banned: {identity}")
        return self._reply(message, payload)

    def _handle_unban_identity(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        """Remove a ban/blackhole from an identity."""

        identity = self._extract_identity(command)
        if not identity:
            return self._prompt_for_fields(
                self.CMD_UNBAN_IDENTITY, ["Identity"], message, command
            )
        status = self.api.unban_identity(identity)
        payload = json.dumps(status.to_dict(), sort_keys=True)
        self._record_event("identity_unbanned", f"Identity unbanned: {identity}")
        return self._reply(message, payload)

    def _handle_blackhole_identity(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        """Mark an identity as blackholed."""

        identity = self._extract_identity(command)
        if not identity:
            return self._prompt_for_fields(
                self.CMD_BLACKHOLE_IDENTITY, ["Identity"], message, command
            )
        status = self.api.blackhole_identity(identity)
        payload = json.dumps(status.to_dict(), sort_keys=True)
        self._record_event("identity_blackholed", f"Identity blackholed: {identity}")
        return self._reply(message, payload)

    def _handle_list_identities(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Return identity status entries for admin tools."""

        identities = self.api.list_identity_statuses()
        payload = json.dumps([entry.to_dict() for entry in identities], sort_keys=True)
        return self._reply(message, payload)

    def _handle_get_config(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Return the current config.ini content."""

        config_text = self.api.get_config_text()
        return self._reply(message, config_text)

    def _handle_validate_config(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        """Validate config content without applying changes."""

        config_text = command.get("ConfigText") or command.get("config_text")
        if not config_text:
            return self._prompt_for_fields(
                self.CMD_VALIDATE_CONFIG, ["ConfigText"], message, command
            )
        result = self.api.validate_config_text(str(config_text))
        payload = json.dumps(result, sort_keys=True)
        return self._reply(message, payload)

    def _handle_apply_config(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        """Apply a new config.ini payload."""

        config_text = command.get("ConfigText") or command.get("config_text")
        if not config_text:
            return self._prompt_for_fields(
                self.CMD_APPLY_CONFIG, ["ConfigText"], message, command
            )
        try:
            result = self.api.apply_config_text(str(config_text))
        except ValueError as exc:
            return self._reply(message, f"Config apply failed: {exc}")
        payload = json.dumps(result, sort_keys=True)
        self._record_event("config_applied", "Configuration updated")
        return self._reply(message, payload)

    def _handle_rollback_config(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        """Rollback configuration using the latest backup."""

        backup_path = command.get("BackupPath") or command.get("backup_path")
        backup_value = str(backup_path) if backup_path else None
        result = self.api.rollback_config_text(backup_path=backup_value)
        payload = json.dumps(result, sort_keys=True)
        self._record_event("config_rollback", "Configuration rollback applied")
        return self._reply(message, payload)

    def _handle_flush_telemetry(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Clear stored telemetry records."""

        deleted = self.tel_controller.clear_telemetry()
        payload = json.dumps({"deleted": deleted}, sort_keys=True)
        self._record_event("telemetry_flushed", f"Telemetry flushed ({deleted} rows)")
        return self._reply(message, payload)

    def _handle_reload_config(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Reload configuration from disk."""

        config = self.api.reload_config()
        payload = json.dumps(config.to_dict(), sort_keys=True)
        self._record_event("config_reloaded", "Configuration reloaded")
        return self._reply(message, payload)

    def _handle_dump_routing(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Return a summary of connected destinations."""

        destinations = [
            self._identity_hex(dest.identity) for dest in self.connections.values()
        ]
        payload = json.dumps({"destinations": destinations}, sort_keys=True)
        return self._reply(message, payload)

