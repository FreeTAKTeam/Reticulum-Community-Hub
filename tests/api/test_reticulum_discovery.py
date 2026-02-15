"""Tests for Reticulum discovery runtime helpers."""

from __future__ import annotations

from reticulum_telemetry_hub.api import reticulum_discovery as discovery


def test_capabilities_and_discovery_fallback_when_runtime_unavailable(monkeypatch) -> None:
    """Return safe fallback payloads when the RNS runtime is unavailable."""

    monkeypatch.setattr(discovery, "RNS", None)
    monkeypatch.setattr(discovery, "Discovery", None)

    capabilities = discovery.get_interface_capabilities()
    snapshot = discovery.get_discovery_snapshot()

    assert capabilities["runtime_active"] is False
    assert capabilities["rns_version"] == "unavailable"
    assert isinstance(capabilities["supported_interface_types"], list)
    assert isinstance(capabilities["unsupported_interface_types"], list)
    assert capabilities["supported_interface_types"] == []
    assert capabilities["unsupported_interface_types"]

    assert snapshot["runtime_active"] is False
    assert snapshot["discovered_interfaces"] == []
    assert snapshot["interface_discovery_sources"] == []
    assert isinstance(snapshot["refreshed_at"], str)


def test_capabilities_and_discovery_runtime_snapshot(monkeypatch) -> None:
    """Return normalized runtime capabilities and discovery entries."""

    class _FakeReticulum:
        TRUNCATED_HASHLENGTH = 80
        should_autoconnect_discovered_interfaces = True
        max_autoconnected_interfaces = 8
        required_discovery_value = 14
        interface_discovery_sources = [bytes.fromhex("aabb"), "ff00"]
        discovered_interfaces = {
            "entry-1": {
                "discovery_hash": "0011",
                "status": "available",
                "status_code": 1,
                "type": "TCPClientInterface",
                "name": "North Relay",
                "transport": "tcp",
                "transport_id": "relay-1",
                "network_id": "ops-net",
                "hops": 2,
                "value": 15,
                "received": "2026-02-14T12:00:00+00:00",
                "last_heard": "2026-02-14T12:00:30+00:00",
                "heard_count": 3,
                "reachable_on": "10.0.0.44",
                "port": 4242,
                "config_entry": {
                    "name": "Imported Relay",
                    "type": "TCPClientInterface",
                    "target_host": "10.0.0.44",
                    "target_port": 4242,
                },
            }
        }

        @staticmethod
        def get_instance():
            return object()

    class _FakeRNS:
        __version__ = "1.1.3"
        Reticulum = _FakeReticulum

    class _FakeAnnouncer:
        DISCOVERABLE_INTERFACE_TYPES = ["TCPClientInterface", "UDPInterface"]

    class _FakeDiscoveryRuntime:
        AUTOCONNECT_TYPES = ["TCPClientInterface"]

    class _FakeDiscovery:
        InterfaceAnnouncer = _FakeAnnouncer
        InterfaceDiscovery = _FakeDiscoveryRuntime

    monkeypatch.setattr(discovery, "RNS", _FakeRNS)
    monkeypatch.setattr(discovery, "Discovery", _FakeDiscovery)
    monkeypatch.setattr(
        discovery,
        "_supports_interface_type",
        lambda interface_type, _: interface_type in {"TCPClientInterface", "UDPInterface"},
    )

    capabilities = discovery.get_interface_capabilities()
    snapshot = discovery.get_discovery_snapshot()

    assert capabilities["runtime_active"] is True
    assert capabilities["rns_version"] == "1.1.3"
    assert capabilities["identity_hash_hex_length"] == 20
    assert "TCPClientInterface" in capabilities["supported_interface_types"]
    assert "UDPInterface" in capabilities["supported_interface_types"]
    assert "RNodeIPInterface" in capabilities["unsupported_interface_types"]
    assert capabilities["discoverable_interface_types"] == ["TCPClientInterface", "UDPInterface"]
    assert capabilities["autoconnect_interface_types"] == ["TCPClientInterface"]

    assert snapshot["runtime_active"] is True
    assert snapshot["should_autoconnect"] is True
    assert snapshot["max_autoconnected_interfaces"] == 8
    assert snapshot["required_discovery_value"] == 14
    assert snapshot["interface_discovery_sources"] == ["aabb", "ff00"]
    assert len(snapshot["discovered_interfaces"]) == 1

    entry = snapshot["discovered_interfaces"][0]
    assert entry["discovery_hash"] == "0011"
    assert entry["type"] == "TCPClientInterface"
    assert entry["transport"] == "tcp"
    assert entry["port"] == 4242
    assert entry["config_entry"]["target_host"] == "10.0.0.44"
