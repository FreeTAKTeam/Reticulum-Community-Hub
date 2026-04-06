"""Thread-safe runtime metrics collection for hub diagnostics."""

from __future__ import annotations

from collections import defaultdict
from collections import deque
from dataclasses import dataclass
from dataclasses import field
import threading
import time
from typing import Deque


@dataclass
class _TimerSeries:
    """Rolling timer series used to summarize latency observations."""

    values: Deque[float] = field(default_factory=lambda: deque(maxlen=512))

    def observe(self, value_ms: float) -> None:
        self.values.append(max(float(value_ms), 0.0))

    def snapshot(self) -> dict[str, float]:
        if not self.values:
            return {
                "count": 0,
                "avg_ms": 0.0,
                "p50_ms": 0.0,
                "p95_ms": 0.0,
                "max_ms": 0.0,
            }
        ordered = sorted(self.values)
        count = len(ordered)
        p50_index = min(int(round((count - 1) * 0.50)), count - 1)
        p95_index = min(int(round((count - 1) * 0.95)), count - 1)
        return {
            "count": float(count),
            "avg_ms": round(sum(ordered) / count, 3),
            "p50_ms": round(ordered[p50_index], 3),
            "p95_ms": round(ordered[p95_index], 3),
            "max_ms": round(ordered[-1], 3),
        }


class RuntimeMetricsStore:
    """In-process counter/gauge/timer registry for runtime diagnostics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._timers: dict[str, _TimerSeries] = defaultdict(_TimerSeries)
        self._updated_at = time.time()

    def increment(self, key: str, value: int = 1) -> None:
        """Increment an integer counter."""

        if not key:
            return
        with self._lock:
            self._counters[key] += int(value)
            self._updated_at = time.time()

    def set_gauge(self, key: str, value: float) -> None:
        """Set a floating-point gauge value."""

        if not key:
            return
        with self._lock:
            self._gauges[key] = float(value)
            self._updated_at = time.time()

    def observe_ms(self, key: str, value_ms: float) -> None:
        """Record a duration in milliseconds."""

        if not key:
            return
        with self._lock:
            self._timers[key].observe(value_ms)
            self._updated_at = time.time()

    def snapshot(self) -> dict[str, object]:
        """Return a serializable runtime metrics snapshot."""

        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            timers = {name: series.snapshot() for name, series in self._timers.items()}
            updated_at = self._updated_at
        return {
            "updated_at_unix": round(updated_at, 3),
            "counters": counters,
            "gauges": gauges,
            "timers": timers,
        }
