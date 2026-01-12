"""Northbound FastAPI interface for the Reticulum Telemetry Hub."""

from .app import create_app

__all__ = ["create_app"]
