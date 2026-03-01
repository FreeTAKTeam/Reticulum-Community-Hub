"""Regression tests for LXMF peer offer-response handling."""

from __future__ import annotations

import importlib

import RNS

from reticulum_telemetry_hub.lxmf_runtime import _patch_offer_response_class


def test_offer_response_handles_integer_error_without_iterating(monkeypatch) -> None:
    """Abort cleanly when a remote peer returns an integer error code."""

    lxmpeer_module = importlib.import_module("reticulum_telemetry_hub.lxmf_daemon.LXMPeer")
    monkeypatch.setattr(lxmpeer_module.RNS, "log", lambda *args, **kwargs: None)

    class DummyLink:
        def __init__(self) -> None:
            self.torn_down = False

        def teardown(self) -> None:
            self.torn_down = True

    class DummyReceipt:
        def __init__(self, response: int) -> None:
            self.response = response

    peer = lxmpeer_module.LXMPeer.__new__(lxmpeer_module.LXMPeer)
    link = DummyLink()
    peer.link = link
    peer.state = lxmpeer_module.LXMPeer.REQUEST_SENT
    peer.destination = "dummy-peer"

    peer.offer_response(DummyReceipt(lxmpeer_module.LXMPeer.ERROR_INVALID_KEY))

    assert link.torn_down is True
    assert peer.link is None
    assert peer.state == lxmpeer_module.LXMPeer.IDLE


def test_runtime_patch_handles_installed_lxmf_integer_errors(monkeypatch) -> None:
    """Intercept installed LXMF integer errors before the upstream handler iterates them."""

    monkeypatch.setattr(RNS, "log", lambda *args, **kwargs: None)

    class DummyLink:
        def __init__(self) -> None:
            self.torn_down = False

        def teardown(self) -> None:
            self.torn_down = True

    class DummyReceipt:
        def __init__(self, response: int) -> None:
            self.response = response

    class DummyPeer:
        ERROR_NO_IDENTITY = 1
        ERROR_NO_ACCESS = 2
        ERROR_THROTTLED = 3
        ERROR_INVALID_KEY = 4
        ERROR_INVALID_DATA = 5
        ERROR_INVALID_STAMP = 6
        ERROR_TIMEOUT = 7
        IDLE = "idle"

        def __init__(self) -> None:
            self.link = None
            self.state = "busy"
            self.original_called = False
            self.last_response = None

        def offer_response(self, request_receipt) -> None:
            self.original_called = True
            self.last_response = request_receipt.response

    _patch_offer_response_class(DummyPeer)

    rejected_peer = DummyPeer()
    rejected_peer.link = DummyLink()

    rejected_peer.offer_response(DummyReceipt(DummyPeer.ERROR_INVALID_KEY))

    assert rejected_peer.original_called is False
    assert rejected_peer.link is None
    assert rejected_peer.state == DummyPeer.IDLE

    passthrough_peer = DummyPeer()
    passthrough_peer.link = DummyLink()

    passthrough_peer.offer_response(DummyReceipt(DummyPeer.ERROR_NO_ACCESS))

    assert passthrough_peer.original_called is True
    assert passthrough_peer.link is not None
    assert passthrough_peer.last_response == DummyPeer.ERROR_NO_ACCESS
