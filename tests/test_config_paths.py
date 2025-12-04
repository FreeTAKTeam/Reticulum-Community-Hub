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


def test_config_manager_expands_optional_config_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    reticulum_path = "~/custom/.reticulum/config"
    lxmf_path = "~/custom/.lxmd/config"

    manager = HubConfigurationManager(
        storage_path="~/rth_store",
        config_path="~/config.ini",
        reticulum_config_path=reticulum_path,
        lxmf_router_config_path=lxmf_path,
    )

    assert manager.reticulum_config_path == (tmp_path / "custom/.reticulum/config")
    assert manager.lxmf_router_config_path == tmp_path / "custom/.lxmd/config"


def test_tak_config_includes_proto_and_compat(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[TAK]\n" "cot_url = tcp://example:8087\n" "tak_proto = 0\n" "fts_compat = 1\n"
    )

    manager = HubConfigurationManager(storage_path=tmp_path, config_path=config_path)

    assert manager.tak_config.cot_url == "tcp://example:8087"
    assert manager.tak_config.tak_proto == 0
    assert manager.tak_config.fts_compat == 1
