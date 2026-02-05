"""Consistency checks for release metadata and desktop packaging settings."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
ELECTRON_PACKAGE_PATH = REPO_ROOT / "electron" / "package.json"
ELECTRON_LOCK_PATH = REPO_ROOT / "electron" / "package-lock.json"
BUILD_PS1_PATH = REPO_ROOT / "build-electron.ps1"
BUILD_SH_PATH = REPO_ROOT / "build-electron.sh"


def _read_python_version() -> str:
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    return data["tool"]["poetry"]["version"]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_electron_version_matches_python_version() -> None:
    """Ensure desktop app metadata stays aligned with Python package version."""

    python_version = _read_python_version()
    electron_package = _read_json(ELECTRON_PACKAGE_PATH)
    electron_lock = _read_json(ELECTRON_LOCK_PATH)

    assert electron_package["version"] == python_version
    assert electron_lock["version"] == python_version
    assert electron_lock["packages"][""]["version"] == python_version


def test_windows_artifact_naming_convention() -> None:
    """Ensure Windows installer and portable outputs follow release naming."""

    electron_package = _read_json(ELECTRON_PACKAGE_PATH)
    nsis_name = electron_package["build"]["nsis"]["artifactName"]
    portable_name = electron_package["build"]["portable"]["artifactName"]

    assert nsis_name == "RCH_win Install_${version}.${ext}"
    assert portable_name == "RCH_win Portable_${version}.${ext}"


def test_build_scripts_sync_electron_version_before_build() -> None:
    """Ensure top-level build scripts trigger version sync automatically."""

    ps1_text = BUILD_PS1_PATH.read_text(encoding="utf-8")
    sh_text = BUILD_SH_PATH.read_text(encoding="utf-8")

    assert "npm\" @(\"run\", \"sync:version\")" in ps1_text
    assert "npm run sync:version" in sh_text
