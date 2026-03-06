"""Helpers for recording non-fatal runtime failures."""

from __future__ import annotations

from typing import Mapping

import RNS

from .event_log import EventLog


def report_nonfatal_exception(
    event_log: EventLog | None,
    event_type: str,
    message: str,
    exc: Exception,
    *,
    metadata: Mapping[str, object] | None = None,
    log_level: int | None = None,
) -> dict[str, object] | None:
    """Mirror a handled exception to the runtime log and shared event feed.

    Args:
        event_log (EventLog | None): Shared event log sink when available.
        event_type (str): Event category recorded for the UI feed.
        message (str): Human readable description of the failure.
        exc (Exception): The handled exception instance.
        metadata (Mapping[str, object] | None): Optional extra context.
        log_level (int | None): Desired Reticulum log level.

    Returns:
        dict[str, object] | None: Recorded event entry when an event log exists,
            otherwise ``None``.
    """

    level = log_level if log_level is not None else getattr(RNS, "LOG_ERROR", 1)
    try:
        RNS.log(message, level)
    except Exception:
        # Reason: exception reporting must never interrupt the caller.
        pass

    event_metadata = dict(metadata or {})
    event_metadata["exception_type"] = type(exc).__name__
    event_metadata["exception_message"] = str(exc)

    if event_log is None:
        return None

    try:
        return event_log.add_event(event_type, message, metadata=event_metadata)
    except Exception:
        # Reason: reporting helpers are best-effort and must not cascade.
        return None
