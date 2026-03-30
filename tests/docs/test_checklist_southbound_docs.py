from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_southbound_doc_describes_shared_excheck_workflow() -> None:
    content = _read("docs/southbound.md")

    assert "Excheck/task sharing uses the existing checklist southbound command family" in content
    assert "`checklist.create.online` -> `checklist.task.row.add` /" in content
    assert "`checklist.task.cell.set` / `checklist.task.status.set`" in content


def test_supported_commands_doc_calls_out_shared_excheck_commands() -> None:
    content = _read("docs/supportedCommands.md")

    assert "Shared Excheck/task workflow" in content
    assert "`checklist.create.online`" in content
    assert "`checklist.task.row.add`" in content
    assert "`checklist.task.cell.set`" in content
    assert "`checklist.task.status.set`" in content
