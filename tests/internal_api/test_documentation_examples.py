"""Validate documentation examples against internal API schemas."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandResult
from reticulum_telemetry_hub.internal_api.v1.schemas import EventEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryResult


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DOC = REPO_ROOT / "docs" / "internal-api-examples.md"

MODEL_MAP = {
    "CommandEnvelope": CommandEnvelope,
    "EventEnvelope": EventEnvelope,
    "QueryEnvelope": QueryEnvelope,
    "CommandResult": CommandResult,
    "QueryResult": QueryResult,
}


def _iter_examples(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r"<!--\s*schema:\s*(\w+)\s*-->\s*```json\s*(.*?)```",
        re.DOTALL,
    )
    return [(match.group(1), match.group(2).strip()) for match in pattern.finditer(text)]


def test_documentation_examples_validate() -> None:
    content = EXAMPLES_DOC.read_text(encoding="utf-8")
    examples = _iter_examples(content)
    assert examples, "No documentation examples found."

    for schema_name, payload_text in examples:
        model = MODEL_MAP.get(schema_name)
        assert model is not None, f"Unknown schema {schema_name}"
        payload = json.loads(payload_text)
        model.model_validate(payload)
