import logging
from configparser import ConfigParser

import asyncio
import pytest

from reticulum_telemetry_hub.atak_cot import pytak_client


def test_cli_tool_logs_connection_success(caplog, monkeypatch):
    async def fake_protocol_factory(config):
        return object(), object()

    monkeypatch.setattr(pytak_client.pytak, "protocol_factory", fake_protocol_factory)
    config = ConfigParser()
    config["fts"] = {"COT_URL": "tcp://example:8087"}

    cli_tool = pytak_client.FTSCLITool(config["fts"])

    caplog.set_level(logging.INFO)
    original_propagate = cli_tool._logger.propagate
    cli_tool._logger.propagate = True
    asyncio.run(cli_tool.setup())
    cli_tool._logger.propagate = original_propagate

    assert "Connected to TAK server at tcp://example:8087" in caplog.text


def test_cli_tool_logs_connection_failure(caplog, monkeypatch):
    async def failing_protocol_factory(config):  # pragma: no cover - injected failure
        raise RuntimeError("socket error")

    monkeypatch.setattr(
        pytak_client.pytak, "protocol_factory", failing_protocol_factory
    )
    config = ConfigParser()
    config["fts"] = {"COT_URL": "tcp://example:8087"}

    cli_tool = pytak_client.FTSCLITool(config["fts"])

    caplog.set_level(logging.ERROR)
    original_propagate = cli_tool._logger.propagate
    cli_tool._logger.propagate = True
    with pytest.raises(RuntimeError):
        asyncio.run(cli_tool.setup())
    cli_tool._logger.propagate = original_propagate

    assert "Failed to connect to TAK server" in caplog.text
