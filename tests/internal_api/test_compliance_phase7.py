"""Contract compliance tests for internal API boundaries."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INTERNAL_API_ROOT = REPO_ROOT / "reticulum_telemetry_hub" / "internal_api"

FORBIDDEN_PREFIXES = (
    "reticulum_telemetry_hub.api",
    "reticulum_telemetry_hub.northbound",
    "reticulum_telemetry_hub.reticulum_server",
    "reticulum_telemetry_hub.ui",
)


def _iter_imports(tree: ast.AST) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_internal_api_has_no_forbidden_imports() -> None:
    for path in INTERNAL_API_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _iter_imports(tree):
            for forbidden in FORBIDDEN_PREFIXES:
                assert not name.startswith(forbidden), f"{path} imports {name}"
