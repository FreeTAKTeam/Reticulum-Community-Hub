"""Bounded observation of successful maintenance in one owned append-only log."""
import re
from datetime import datetime
import time


class MaintenanceObserver:
    def __init__(self, path):
        self.path = path
        self.offset = path.stat().st_size  # Ignore every pre-observation line.
        self.pending = b''
        self.completions = []
        self.failure = None

    def poll(self):
        if self.failure:
            raise RuntimeError(self.failure)
        if self.path.stat().st_size < self.offset:
            raise RuntimeError('Owned maintenance log was truncated')
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            chunk = stream.read(1_048_576)
        self.offset += len(chunk)
        lines = (self.pending + chunk).split(b'\n')
        self.pending = lines.pop()
        if len(self.pending) > 65_536:
            raise RuntimeError('Owned maintenance log line exceeds 64 KiB')
        for line in lines:
            if len(line) > 65_536:
                raise RuntimeError('Owned maintenance log line exceeds 64 KiB')
            if re.search(rb'propagation storage maintenance (?:worker )?failed:', line):
                self.failure = 'Owned daemon maintenance failed: ' + line[:1024].decode(errors='replace')
                raise RuntimeError(self.failure)
            match = re.search(rb'propagation storage maintenance complete elapsed_ms=(\d+) pruned_peer_entries=(\d+)', line)
            if match:
                if len(self.completions) == 16:
                    raise RuntimeError('Maintenance evidence exceeds bounded preflight window')
                timestamp = re.search(rb'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', line)
                if timestamp is None:
                    raise RuntimeError('Maintenance completion lacks a daemon timestamp')
                completed_wall = datetime.fromisoformat(timestamp[0].decode().replace('Z', '+00:00')).timestamp()
                observed = time.monotonic()
                wall_delay = time.time() - completed_wall
                if wall_delay < -1:
                    raise RuntimeError('Maintenance completion timestamp is in the future')
                completed = observed - wall_delay
                self.completions.append({'observed_monotonic_s': observed,
                                         'completed_monotonic_estimate_s': completed,
                                         'began_monotonic_estimate_s': completed - int(match[1]) / 1000,
                                         'daemon_completed_utc': timestamp[0].decode(),
                                         'clock_note': 'same-host wall timestamp converted to monotonic at observation',
                                         'observed_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                                         'through_file_offset': self.offset,
                                         'elapsed_ms': int(match[1]), 'pruned_peer_entries': int(match[2])})
        return self.completions

    def verify_post_cycle(self, admitted_pairs, completed_pairs):
        if self.failure:
            raise RuntimeError(self.failure)
        if not self.completions:
            raise RuntimeError('No successful storage maintenance observed during delivery')
        first = self.completions[0]
        if not any(at < first['began_monotonic_estimate_s'] for at in completed_pairs.values()):
            raise RuntimeError('No completed real delivery pair admitted before maintenance')
        if not any(at > first['observed_monotonic_s'] and token in completed_pairs for token, at in admitted_pairs.items()):
            raise RuntimeError('No completed real delivery pair admitted after observing maintenance')
