"""Baseline contract checks for the internal API."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from reticulum_telemetry_hub.internal_api.v1 import CONTRACT_VERSION


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DOC = REPO_ROOT / "internal-api.md"
MANIFEST_PATH = (
    REPO_ROOT / "reticulum_telemetry_hub" / "internal_api" / "v1" / "manifest.json"
)
V1_ROOT = MANIFEST_PATH.parent


def _read_contract_version() -> str:
    """Return the version declared in internal-api.md."""

    content = CONTRACT_DOC.read_text(encoding="utf-8")
    for line in content.splitlines():
        if line.strip().startswith("Version:"):
            return line.split("Version:", 1)[1].strip()
    raise AssertionError("Version line not found in internal-api.md")


def _load_manifest() -> dict:
    """Load the internal API manifest."""

    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _hash_file(path: Path) -> str:
    """Return the SHA256 hash for a file."""

    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest().upper()


def test_contract_doc_declares_out_of_scope_section() -> None:
    """Ensure the contract doc includes an Out of Scope section."""

    content = CONTRACT_DOC.read_text(encoding="utf-8")
    assert "Out of Scope" in content


def test_contract_version_alignment() -> None:
    """Ensure contract version matches code and manifest."""

    version = _read_contract_version()
    manifest = _load_manifest()

    assert version == CONTRACT_VERSION
    assert manifest["contract_version"] == CONTRACT_VERSION


def test_manifest_matches_internal_api_files() -> None:
    """Ensure internal API v1 files match the manifest."""

    manifest = _load_manifest()
    expected = manifest.get("files", {})
    actual = {
        path.name: _hash_file(path)
        for path in V1_ROOT.iterdir()
        if path.is_file() and path.name != "manifest.json"
    }

    assert set(actual.keys()) == set(expected.keys())
    for name, digest in actual.items():
        assert expected[name] == digest
