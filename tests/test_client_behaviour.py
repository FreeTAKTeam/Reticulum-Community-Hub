from pathlib import Path
from typing import Any

from tests import test_client as client_example


def test_received_announce_appends_destination(monkeypatch):
    created_destinations: list[Any] = []

    class DummyDestination:
        OUT = "out"
        SINGLE = "single"

        def __init__(self, identity, direction, dest_type, app, aspect):
            self.identity = identity
            self.direction = direction
            self.dest_type = dest_type
            self.app = app
            self.aspect = aspect
            created_destinations.append(self)

    monkeypatch.setattr(client_example.RNS, "Destination", DummyDestination)
    monkeypatch.setattr(client_example.RNS, "log", lambda *_: None)
    monkeypatch.setattr(client_example.RNS, "prettyhexrep", lambda value: f"hex:{value}")

    connections = []
    handler = client_example.AnnounceHandler(
        connections=connections, my_lxmf_dest=None, lxm_router=None
    )

    handler.received_announce(b"abc", "identity", {"app": "data"})

    assert len(connections) == 1
    assert connections[0].identity == "identity"
    assert created_destinations[0].aspect == "delivery"


def test_delivery_callback_processes_commands_and_stream(monkeypatch, capsys):
    logs: list[str] = []
    commands_seen: list[list[int]] = []

    class DummyMessage:
        def __init__(self):
            self.timestamp = 1700000000
            self.signature_validated = True
            self.unverified_reason = ""
            self.fields = {
                client_example.LXMF.FIELD_COMMANDS: [[1, 2, 3]],
                client_example.LXMF.FIELD_TELEMETRY_STREAM: {"stream": True},
            }
            self.source_hash = b"\x01" * 4
            self.destination_hash = b"\x02" * 4
            self.transport_encryption = False

        def title_as_string(self):
            return "Title"

        def content_as_string(self):
            return "Content"

        def get_source(self):
            return "source"

        def get_destination(self):
            return "dest"

    monkeypatch.setattr(client_example.RNS, "log", lambda message: logs.append(str(message)))
    monkeypatch.setattr(
        client_example.RNS, "prettyhexrep", lambda value: f"hex:{value}"
    )
    monkeypatch.setattr(
        client_example,
        "command_handler",
        lambda commands, message, lxm_router, my_lxmf_dest: commands_seen.append(commands),
    )

    client_example.delivery_callback(
        DummyMessage(), connections=[], my_lxmf_dest=None, lxm_router=None
    )

    assert commands_seen == [[[1, 2, 3]]]
    captured = capsys.readouterr()
    assert "Telemetry stream received" in captured.out


def test_load_or_generate_identity_reads_existing_file(tmp_path, monkeypatch):
    identity_path = tmp_path / "identity"
    logs: list[str] = []

    class FakeIdentity:
        def __init__(self, name: str = "new") -> None:
            self.name = name

        def to_file(self, path: str | Path) -> None:
            Path(path).write_text(self.name)

        @classmethod
        def from_file(cls, path: str | Path) -> "FakeIdentity":
            name = Path(path).read_text()
            return cls(name=name)

    monkeypatch.setattr(client_example.RNS, "Identity", FakeIdentity)
    monkeypatch.setattr(client_example.RNS, "log", lambda message: logs.append(str(message)))

    created = client_example.load_or_generate_identity(identity_path)
    stored = client_example.load_or_generate_identity(identity_path)

    assert identity_path.exists()
    assert getattr(created, "name", None) == "new"
    assert getattr(stored, "name", None) == "new"
    assert "Loading existing identity" in logs[-1]
