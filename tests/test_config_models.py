from importlib import metadata

import pytest

from reticulum_telemetry_hub.config.models import HubAppConfig
from reticulum_telemetry_hub.config.models import HubRuntimeConfig
from reticulum_telemetry_hub.config.models import LXMFRouterConfig
from reticulum_telemetry_hub.config.models import RNSInterfaceConfig
from reticulum_telemetry_hub.config.models import ReticulumConfig
from reticulum_telemetry_hub.config.models import TakConnectionConfig


def test_rns_and_reticulum_configs_serialize_paths(tmp_path):
    interface = RNSInterfaceConfig(listen_ip="127.0.0.1", listen_port=5151)
    reticulum = ReticulumConfig(path=tmp_path / "reticulum.conf", tcp_interface=interface)

    result = reticulum.to_dict()

    assert result["path"] == str(tmp_path / "reticulum.conf")
    assert result["enable_transport"] is True
    assert result["share_instance"] is True
    assert result["tcp_interface"]["listen_ip"] == "127.0.0.1"
    assert result["tcp_interface"]["listen_port"] == 5151


def test_lxmf_router_config_to_dict_includes_all_fields(tmp_path):
    router_config = LXMFRouterConfig(
        path=tmp_path / "router.ini",
        enable_node=False,
        display_name="Relay",
        peer_announce_at_start=False,
        peer_announce_interval_minutes=15,
        delivery_transfer_max_accepted_size_kb=768.0,
        on_inbound="python handler.py",
        node_name="Relay Node",
        auth_required=True,
        node_announce_at_start=False,
        node_announce_interval_minutes=25,
        autopeer=False,
        autopeer_maxdepth=3,
        message_storage_limit_megabytes=42.5,
        propagation_transfer_max_accepted_size_kb=512.0,
        propagation_sync_max_accepted_size_kb=4096.0,
        propagation_stamp_cost_target=12,
        propagation_stamp_cost_flexibility=2,
        peering_cost=7,
        remote_peering_cost_max=21,
        prioritised_lxmf_destinations=("aa" * 16, "bb" * 16),
        control_allowed_identities=("cc" * 16,),
        static_peers=("dd" * 16,),
        max_peers=8,
        from_static_only=True,
        propagation_start_mode="blocking",
        propagation_startup_prune_enabled=True,
        propagation_startup_max_messages=5000,
        propagation_startup_max_age_days=14,
    )

    serialized = router_config.to_dict()

    assert serialized["path"] == str(tmp_path / "router.ini")
    assert serialized["enable_node"] is False
    assert serialized["display_name"] == "Relay"
    assert serialized["peer_announce_at_start"] is False
    assert serialized["peer_announce_interval_minutes"] == 15
    assert serialized["delivery_transfer_max_accepted_size_kb"] == pytest.approx(768.0)
    assert serialized["on_inbound"] == "python handler.py"
    assert serialized["node_name"] == "Relay Node"
    assert serialized["auth_required"] is True
    assert serialized["announce_interval_minutes"] == 25
    assert serialized["node_announce_at_start"] is False
    assert serialized["node_announce_interval_minutes"] == 25
    assert serialized["autopeer"] is False
    assert serialized["autopeer_maxdepth"] == 3
    assert serialized["message_storage_limit_megabytes"] == pytest.approx(42.5)
    assert serialized["propagation_transfer_max_accepted_size_kb"] == pytest.approx(
        512.0
    )
    assert serialized["propagation_sync_max_accepted_size_kb"] == pytest.approx(
        4096.0
    )
    assert serialized["propagation_stamp_cost_target"] == 12
    assert serialized["propagation_stamp_cost_flexibility"] == 2
    assert serialized["peering_cost"] == 7
    assert serialized["remote_peering_cost_max"] == 21
    assert serialized["prioritised_lxmf_destinations"] == ["aa" * 16, "bb" * 16]
    assert serialized["control_allowed_identities"] == ["cc" * 16]
    assert serialized["static_peers"] == ["dd" * 16]
    assert serialized["max_peers"] == 8
    assert serialized["from_static_only"] is True
    assert serialized["propagation_start_mode"] == "blocking"
    assert serialized["propagation_startup_prune_enabled"] is True
    assert serialized["propagation_startup_max_messages"] == 5000
    assert serialized["propagation_startup_max_age_days"] == 14


def test_safe_get_version_handles_missing_distribution(monkeypatch):
    def _missing_version(_: str) -> str:
        raise metadata.PackageNotFoundError("missing-package")

    monkeypatch.setattr(metadata, "version", _missing_version)

    result = HubAppConfig._safe_get_version("missing-package")

    assert result == "unknown"


def test_safe_get_version_handles_unexpected_errors(monkeypatch):
    def _broken_version(_: str) -> str:
        raise RuntimeError("metadata failure")

    monkeypatch.setattr(metadata, "version", _broken_version)

    result = HubAppConfig._safe_get_version("broken-package")

    assert result == "unknown"


def test_tak_connection_config_to_config_parser_sets_defaults():
    config = TakConnectionConfig(
        tls_client_cert="/path/cert.pem",
        tls_client_key="/path/key.pem",
        tls_ca="/path/ca.pem",
        tls_insecure=True,
        tak_proto=1,
        fts_compat=0,
    )

    parser = config.to_config_parser()
    fts_section = parser["fts"]

    assert fts_section["COT_URL"] == "tcp://127.0.0.1:8087"
    assert fts_section["CALLSIGN"] == "RTH"
    assert fts_section["SSL_CLIENT_CERT"] == "/path/cert.pem"
    assert fts_section["SSL_CLIENT_KEY"] == "/path/key.pem"
    assert fts_section["SSL_CLIENT_CAFILE"] == "/path/ca.pem"
    assert fts_section["SSL_VERIFY"] == "false"
    assert fts_section["TAK_PROTO"] == "1"
    assert fts_section["FTS_COMPAT"] == "0"


def test_tak_connection_config_to_dict_reflects_values():
    config = TakConnectionConfig(
        cot_url="ssl://tak.example:8089",
        callsign="RTH1",
        poll_interval_seconds=15.5,
        keepalive_interval_seconds=45.5,
        tls_insecure=False,
        tak_proto=2,
        fts_compat=1,
    )

    config_dict = config.to_dict()

    assert config_dict["cot_url"] == "ssl://tak.example:8089"
    assert config_dict["callsign"] == "RTH1"
    assert config_dict["poll_interval_seconds"] == pytest.approx(15.5)
    assert config_dict["keepalive_interval_seconds"] == pytest.approx(45.5)
    assert config_dict["tls_insecure"] is False
    assert config_dict["tak_proto"] == 2
    assert config_dict["fts_compat"] == 1


def test_hub_app_config_uses_defaults_when_metadata_missing(tmp_path, monkeypatch):
    runtime = HubRuntimeConfig()
    reticulum = ReticulumConfig(path=tmp_path / "reticulum.conf")
    lxmf_router = LXMFRouterConfig(path=tmp_path / "lxmf.conf")
    app_config = HubAppConfig(
        storage_path=tmp_path,
        database_path=tmp_path / "rth.db",
        hub_database_path=tmp_path / "hub.db",
        file_storage_path=tmp_path / "files",
        image_storage_path=tmp_path / "images",
        runtime=runtime,
        reticulum=reticulum,
        lxmf_router=lxmf_router,
        app_name="",
        app_version=None,
        app_description=None,
    )
    monkeypatch.setattr(metadata, "version", lambda dist: f"{dist}-version")

    snapshot = app_config.to_reticulum_info_dict()

    assert snapshot["app_name"] == "ReticulumTelemetryHub"
    assert snapshot["app_version"] == "ReticulumTelemetryHub-version"
    assert snapshot["rns_version"] == "RNS-version"
    assert snapshot["lxmf_version"] == "LXMF-version"
    assert snapshot["app_description"] == ""
