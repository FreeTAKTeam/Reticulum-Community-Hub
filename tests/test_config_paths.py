from reticulum_telemetry_hub.config import HubConfigurationManager


def test_config_manager_expands_user_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    storage_path = "~/rth_store"
    config_path = "~/config.ini"

    manager = HubConfigurationManager(
        storage_path=storage_path,
        config_path=config_path,
    )

    assert manager.storage_path == tmp_path / "rth_store"
    assert manager.config_path == tmp_path / "config.ini"

    default_config_manager = HubConfigurationManager(storage_path=storage_path)
    assert default_config_manager.storage_path == tmp_path / "rth_store"
    assert default_config_manager.config_path == (tmp_path / "rth_store" / "config.ini")
