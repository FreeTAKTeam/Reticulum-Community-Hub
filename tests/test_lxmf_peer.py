"""Regression tests for LXMF peer offer-response handling."""

from __future__ import annotations

import importlib


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
