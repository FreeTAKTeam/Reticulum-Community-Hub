"""Architecture regression tests for reticulum server module boundaries."""

from __future__ import annotations

import ast
from pathlib import Path


PACKAGE_PREFIX = "reticulum_telemetry_hub.reticulum_server"
TARGET_MODULES = {
    "__main__",
    "delivery_service",
    "message_router",
    "message_events",
    "outbound_queue",
}


def _module_path(module_name: str) -> Path:
    return Path("reticulum_telemetry_hub/reticulum_server") / f"{module_name}.py"


def _module_dependencies(module_name: str) -> set[str]:
    path = _module_path(module_name)
    tree = ast.parse(path.read_text(), filename=str(path))
    dependencies: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported = node.module or ""
            if node.level:
                base = f"{PACKAGE_PREFIX}.{module_name}"
                parts = base.split(".")
                base_parts = parts[:-node.level]
                if imported:
                    imported = ".".join(base_parts + imported.split("."))
                else:
                    imported = ".".join(base_parts)
            if imported.startswith(PACKAGE_PREFIX):
                target = imported.rsplit(".", 1)[-1]
                if target in TARGET_MODULES:
                    dependencies.add(target)
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported = alias.name
                if imported.startswith(PACKAGE_PREFIX):
                    target = imported.rsplit(".", 1)[-1]
                    if target in TARGET_MODULES:
                        dependencies.add(target)
    return dependencies


def _dependency_graph() -> dict[str, set[str]]:
    return {module: _module_dependencies(module) for module in TARGET_MODULES}


def _has_cycle(graph: dict[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def _visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for neighbor in graph.get(node, set()):
            if _visit(neighbor):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(_visit(node) for node in graph)


def test_new_services_do_not_import_runtime_main_module() -> None:
    """Ensure extracted helpers stay independent from runtime entrypoint internals."""

    for module in {"delivery_service", "message_router", "message_events"}:
        deps = _module_dependencies(module)
        assert "__main__" not in deps


def test_main_runtime_imports_extracted_services() -> None:
    """Ensure runtime module wires extracted helper modules explicitly."""

    deps = _module_dependencies("__main__")
    assert {"delivery_service", "message_router", "message_events"}.issubset(deps)


def test_reticulum_server_subset_has_no_circular_imports() -> None:
    """Guard against circular imports across the outbound refactor boundary."""

    graph = _dependency_graph()
    assert not _has_cycle(graph), f"Detected circular import graph: {graph}"
