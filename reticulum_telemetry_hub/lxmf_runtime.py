"""Runtime compatibility patches for the external LXMF package."""

from __future__ import annotations

import importlib
from functools import wraps
from typing import Any
from typing import Callable

_OFFER_RESPONSE_PATCHED = "__rch_offer_response_patched__"


def apply_lxmf_runtime_patches() -> None:
    """Patch external LXMF runtime behavior required by the hub."""

    lxmpeer_module = importlib.import_module("LXMF.LXMPeer")
    _patch_offer_response_class(lxmpeer_module.LXMPeer)


def _patch_offer_response_class(peer_class: type[Any]) -> None:
    """Wrap ``offer_response`` so integer error codes are handled safely."""

    offer_response = getattr(peer_class, "offer_response", None)
    if not callable(offer_response):
        return

    if getattr(offer_response, _OFFER_RESPONSE_PATCHED, False):
        return

    patched_offer_response = _build_offer_response_wrapper(offer_response)
    setattr(patched_offer_response, _OFFER_RESPONSE_PATCHED, True)
    setattr(peer_class, "offer_response", patched_offer_response)


def _build_offer_response_wrapper(
    original_offer_response: Callable[..., Any],
) -> Callable[..., Any]:
    """Build a wrapper around the installed LXMF ``offer_response`` handler."""

    @wraps(original_offer_response)
    def patched_offer_response(self: Any, request_receipt: Any) -> Any:
        response = getattr(request_receipt, "response", None)
        if type(response) is int and _handle_integer_offer_response(self, response):
            return None

        return original_offer_response(self, request_receipt)

    return patched_offer_response


def _handle_integer_offer_response(peer: Any, response: int) -> bool:
    """Return True when an integer response has been handled locally."""

    peer_class = peer.__class__
    known_error_responses = (
        (
            getattr(peer_class, "ERROR_INVALID_KEY", None),
            "Remote indicated that the peering key was invalid, sync aborted",
        ),
        (
            getattr(peer_class, "ERROR_INVALID_DATA", None),
            "Remote indicated that the sync offer data was invalid, sync aborted",
        ),
        (
            getattr(peer_class, "ERROR_INVALID_STAMP", None),
            "Remote indicated that the sync offer stamp was invalid, sync aborted",
        ),
        (
            getattr(peer_class, "ERROR_TIMEOUT", None),
            "Remote indicated that the sync offer timed out, sync aborted",
        ),
    )
    for expected_response, message in known_error_responses:
        if expected_response is not None and response == expected_response:
            _abort_sync_offer(peer, message)
            return True

    pass_through_responses = {
        expected_response
        for expected_response in (
            getattr(peer_class, "ERROR_NO_IDENTITY", None),
            getattr(peer_class, "ERROR_NO_ACCESS", None),
            getattr(peer_class, "ERROR_THROTTLED", None),
        )
        if expected_response is not None
    }
    if response in pass_through_responses:
        return False

    _abort_sync_offer(
        peer,
        f"Remote returned unknown sync offer response {response}, sync aborted",
    )
    return True


def _abort_sync_offer(peer: Any, message: str) -> None:
    """Abort the current LXMF sync and tear down the active peer link."""

    import RNS

    RNS.log(message, RNS.LOG_VERBOSE)

    link = getattr(peer, "link", None)
    if link is not None:
        link.teardown()

    peer.link = None
    peer.state = getattr(peer.__class__, "IDLE", getattr(peer, "state", None))
