"""Tests for LXMF runtime compatibility patches."""

from __future__ import annotations

import sys
import time
from types import SimpleNamespace

from reticulum_telemetry_hub.lxmf_runtime import _patch_generate_stamp_function
from reticulum_telemetry_hub.lxmf_runtime import _safe_rounds_per_second


def test_safe_rounds_per_second_handles_zero_duration() -> None:
    """Zero-length stamp timing should not raise during speed calculation."""

    assert _safe_rounds_per_second(12, 0.0) == 0.0
    assert _safe_rounds_per_second(12, -1.0) == 0.0
    assert _safe_rounds_per_second(12, 0.5) == 24.0


def test_generate_stamp_patch_avoids_zero_division(monkeypatch) -> None:
    """Patched LXMF stamp generation should survive a zero-duration timing sample."""

    logs: list[tuple[str, str]] = []

    fake_rns = SimpleNamespace(
        LOG_DEBUG="debug",
        log=lambda message, level: logs.append((message, level)),
        prettyhexrep=lambda message_id: message_id.hex(),
        prettytime=lambda duration: f"{duration:.6f}s",
        vendor=SimpleNamespace(
            platformutils=SimpleNamespace(
                is_windows=lambda: False,
                is_darwin=lambda: False,
                is_android=lambda: False,
            )
        ),
    )
    monkeypatch.setitem(sys.modules, "RNS", fake_rns)

    lxstamper_module = SimpleNamespace(
        WORKBLOCK_EXPAND_ROUNDS=11,
        generate_stamp=lambda message_id, stamp_cost, expand_rounds=11: (None, 0),
        stamp_workblock=lambda message_id, expand_rounds: b"workblock",
        job_simple=lambda stamp_cost, workblock, message_id: (b"stamp", 5),
        job_android=lambda stamp_cost, workblock, message_id: (b"stamp", 5),
        job_linux=lambda stamp_cost, workblock, message_id: (b"stamp", 5),
        stamp_value=lambda workblock, stamp: 73,
    )

    times = iter((100.0, 100.0))
    monkeypatch.setattr(time, "time", lambda: next(times))

    _patch_generate_stamp_function(lxstamper_module)

    stamp, value = lxstamper_module.generate_stamp(b"\x01\x02", 4)

    assert stamp == b"stamp"
    assert value == 73
    assert logs[-1][1] == "debug"
    assert "0 rounds per second" in logs[-1][0]
