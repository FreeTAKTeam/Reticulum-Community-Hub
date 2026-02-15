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


def test_app_metadata_comes_from_config(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[app]\n"
        "name = Sample Hub\n"
        "version = 1.2.3\n"
        "description = Demo instance\n"
    )

    manager = HubConfigurationManager(storage_path=tmp_path, config_path=config_path)
    info = manager.reticulum_info_snapshot()

    assert info["app_name"] == "Sample Hub"
    assert info["app_version"] == "1.2.3"
    assert info["app_description"] == "Demo instance"


def test_default_file_and_image_paths_created(tmp_path):
    manager = HubConfigurationManager(storage_path=tmp_path)

    assert manager.runtime_config.file_storage_path == tmp_path / "files"
    assert manager.runtime_config.image_storage_path == tmp_path / "images"
    assert manager.runtime_config.file_storage_path.is_dir()
    assert manager.runtime_config.image_storage_path.is_dir()


def test_file_and_image_overrides_expand_and_create(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[files]\n"
        "path = ~/custom/files\n"
        "\n"
        "[images]\n"
        "directory = ~/custom/images\n"
    )

    manager = HubConfigurationManager(
        storage_path="~/store", config_path=config_path
    )

    expected_storage = tmp_path / "store"
    assert manager.storage_path == expected_storage
    assert manager.runtime_config.file_storage_path == tmp_path / "custom/files"
    assert manager.runtime_config.image_storage_path == tmp_path / "custom/images"
    assert manager.runtime_config.file_storage_path.is_dir()
    assert manager.runtime_config.image_storage_path.is_dir()


def test_announce_capabilities_defaults(tmp_path):
    manager = HubConfigurationManager(storage_path=tmp_path)

    runtime = manager.runtime_config

    assert runtime.announce_capabilities_enabled is True
    assert runtime.announce_capabilities_max_bytes == 256
    assert runtime.announce_capabilities_include_version is True
    assert runtime.announce_capabilities_include_timestamp is False


def test_announce_capabilities_config_section_overrides(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[announce.capabilities]\n"
        "enabled = false\n"
        "max_bytes = 128\n"
        "include_version = false\n"
        "include_timestamp = true\n"
    )

    manager = HubConfigurationManager(storage_path=tmp_path, config_path=config_path)
    runtime = manager.runtime_config

    assert runtime.announce_capabilities_enabled is False
    assert runtime.announce_capabilities_max_bytes == 128
    assert runtime.announce_capabilities_include_version is False
    assert runtime.announce_capabilities_include_timestamp is True


def test_lxmf_startup_options_loaded_from_propagation_section(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[propagation]\n"
        "startup_mode = blocking\n"
        "startup_prune_enabled = yes\n"
        "startup_max_messages = 20000\n"
        "startup_max_age_days = 30\n"
    )

    manager = HubConfigurationManager(storage_path=tmp_path, config_path=config_path)
    lxmf = manager.config.lxmf_router

    assert lxmf.propagation_start_mode == "blocking"
    assert lxmf.propagation_startup_prune_enabled is True
    assert lxmf.propagation_startup_max_messages == 20000
    assert lxmf.propagation_startup_max_age_days == 30


def test_resolve_hub_display_name_prefers_configured_value(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[app]\n"
        "version = 9.9.9\n"
        "\n"
        "[hub]\n"
        "display_name = Mission Relay\n"
    )

    manager = HubConfigurationManager(storage_path=tmp_path, config_path=config_path)

    resolved = manager.resolve_hub_display_name(destination_hash="aa" * 16)

    assert resolved == "Mission Relay"


def test_resolve_hub_display_name_uses_default_template_when_unset(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[app]\n"
        "version = 1.2.3\n"
        "\n"
        "[hub]\n"
        "display_name =\n"
    )

    manager = HubConfigurationManager(storage_path=tmp_path, config_path=config_path)

    resolved = manager.resolve_hub_display_name(destination_hash="AA" * 16)

    assert resolved == f"RCH_1.2.3_{'aa' * 16}"


def test_resolve_hub_display_name_prefers_override(tmp_path):
    manager = HubConfigurationManager(storage_path=tmp_path)

    resolved = manager.resolve_hub_display_name(
        override="CLI Relay",
        destination_hash="bb" * 16,
    )

    assert resolved == "CLI Relay"
