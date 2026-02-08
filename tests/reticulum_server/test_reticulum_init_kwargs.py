from types import SimpleNamespace

from reticulum_telemetry_hub.reticulum_server.__main__ import (
    _build_reticulum_init_kwargs,
    _resolve_reticulum_config_dir,
)


def test_resolve_reticulum_config_dir_none_when_manager_missing() -> None:
    assert _resolve_reticulum_config_dir(None) is None


def test_resolve_reticulum_config_dir_uses_parent_for_config_file_path(tmp_path) -> None:
    config_path = tmp_path / "custom-reticulum" / "config"
    manager = SimpleNamespace(reticulum_config_path=config_path)

    assert _resolve_reticulum_config_dir(manager) == str(config_path.parent)


def test_resolve_reticulum_config_dir_keeps_directory_value(tmp_path) -> None:
    config_dir = tmp_path / "reticulum-dir"
    config_dir.mkdir(parents=True)
    manager = SimpleNamespace(reticulum_config_path=config_dir)

    assert _resolve_reticulum_config_dir(manager) == str(config_dir)


def test_build_reticulum_init_kwargs_includes_resolved_configdir(tmp_path) -> None:
    config_path = tmp_path / "profile" / "config"
    manager = SimpleNamespace(reticulum_config_path=config_path)

    kwargs = _build_reticulum_init_kwargs(loglevel=3, config_manager=manager)

    assert kwargs["loglevel"] == 3
    assert kwargs["configdir"] == str(config_path.parent)


def test_build_reticulum_init_kwargs_omits_configdir_without_path() -> None:
    kwargs = _build_reticulum_init_kwargs(loglevel=4, config_manager=SimpleNamespace())

    assert kwargs == {"loglevel": 4}
