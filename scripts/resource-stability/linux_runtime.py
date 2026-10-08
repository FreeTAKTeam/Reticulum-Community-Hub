"""Isolated systemd user services and Linux accounting for resource qualification."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid


def command(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=20).stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def numeric_fields(path: Path) -> dict[str, int]:
    result = {}
    for line in path.read_text().splitlines():
        name, value = line.split(maxsplit=1)
        result[name.rstrip(':')] = int(value.split()[0])
    return result


def pressure(path: Path) -> dict:
    return {parts[0]: {key: float(value) for key, value in
                      (pair.split('=', 1) for pair in parts[1:])}
            for parts in (line.split() for line in path.read_text().splitlines())}


def sample(pid: int, group: Path) -> dict:
    proc = Path('/proc') / str(pid)
    status = {}
    for line in (proc / 'status').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in {'VmRSS', 'VmSwap', 'RssAnon', 'RssFile', 'VmHWM', 'Threads'}:
            status[key] = int(value.split()[0])
    rollup = {}
    # The first smaps_rollup line is a mapping header, not a numeric field.
    for line in (proc / 'smaps_rollup').read_text().splitlines()[1:]:
        key, value = line.split(':', 1)
        rollup[key] = int(value.split()[0])
    stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    return {
        'pid': pid, 'process_start_ticks': int(stat[19]),
        'status_kib': status, 'rollup_kib': rollup,
        'rss_plus_swap_bytes': 1024 * (status['VmRSS'] + status['VmSwap']),
        'anonymous_plus_swap_bytes': 1024 * (status['RssAnon'] + status['VmSwap']),
        'private_plus_swap_bytes': 1024 * (rollup['Private_Clean'] + rollup['Private_Dirty']
                                          + rollup.get('Private_Hugetlb', 0) + rollup['Swap']),
        'fds': len(list((proc / 'fd').iterdir())),
        'io': numeric_fields(proc / 'io'),
        'cgroup': {
            'memory_current': int((group / 'memory.current').read_text()),
            'swap_current': int((group / 'memory.swap.current').read_text()),
            'memory_events': numeric_fields(group / 'memory.events'),
            'memory_stat': numeric_fields(group / 'memory.stat'),
            'cpu_stat': numeric_fields(group / 'cpu.stat'),
            'pressure': pressure(group / 'memory.pressure'),
        },
    }


class Service:
    """Own one transient service; never attach to or stop an existing service."""
    def __init__(self, role: str, executable: Path, args: list[str], directory: Path,
                 high: int, maximum: int, swap: int, cpus: list[int], environment: dict[str, str]):
        self.name = f'rch-resource-{role}-{uuid.uuid4().hex}.service'
        self.pid = None
        self.group = None
        self.start_ticks = None
        self.requested = {'memory.high': high, 'memory.max': maximum,
                          'memory.swap.max': swap, 'cpus': cpus, 'cpu.max_quota_percent': 200}
        self.manifest = {'unit': self.name, 'binary': str(executable.resolve()),
                         'sha256': sha256(executable), 'arguments': args,
                         'environment': environment, 'requested': self.requested}
        properties = {'Type': 'exec', 'RemainAfterExit': 'yes', 'MemoryAccounting': 'yes', 'CPUAccounting': 'yes',
                      'MemoryHigh': str(high), 'MemoryMax': str(maximum),
                      'MemorySwapMax': str(swap), 'CPUQuota': '200%',
                      'CPUAffinity': ' '.join(map(str, cpus)),
                      'WorkingDirectory': str(directory.resolve()), 'TimeoutStopSec': '15s',
                      'StandardOutput': f'append:{directory.resolve() / (role + ".log")}',
                      'StandardError': 'inherit'}
        run = ['systemd-run', '--user', '--quiet', f'--unit={self.name}']
        for key, value in properties.items():
            run += ['--property', f'{key}={value}']
        for key, value in environment.items():
            run += ['--setenv', f'{key}={value}']
        run += [str(executable.resolve()), *args]
        try:
            command(*run)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                pid = command('systemctl', '--user', 'show', self.name, '--property=MainPID', '--value')
                if pid and int(pid) > 0:
                    self.pid = int(pid)
                    break
                time.sleep(0.1)
            if self.pid is None:
                raise RuntimeError(f'{role} did not start: inspect {directory / (role + ".log")}')
            path = command('systemctl', '--user', 'show', self.name, '--property=ControlGroup', '--value')
            self.group = Path('/sys/fs/cgroup') / path.lstrip('/')
            effective = {name: (self.group / name).read_text().strip()
                         for name in ('memory.high', 'memory.max', 'memory.swap.max', 'cpu.max')}
            effective['cpus'] = sorted(os.sched_getaffinity(self.pid))
            for name in ('memory.high', 'memory.max', 'memory.swap.max'):
                if int(effective[name]) != self.requested[name]:
                    raise RuntimeError(f'{name}: requested {self.requested[name]}, got {effective[name]}')
            quota, period = effective['cpu.max'].split()
            if quota == 'max' or int(quota) != 2 * int(period) or effective['cpus'] != cpus:
                raise RuntimeError(f'CPU controls not effective: {effective}')
            self.manifest.update(pid=self.pid, cgroup=str(self.group), effective=effective)
            self.start_ticks = sample(self.pid, self.group)['process_start_ticks']
        except BaseException as original:
            self.cleanup_after_error(original)
            raise

    def cleanup_after_error(self, original: BaseException):
        try:
            self.force_stop()
        except BaseException as cleanup:
            raise BaseExceptionGroup(f'Operation and cleanup failed for owned unit {self.name}',
                                     [original, cleanup]) from None

    def running(self) -> bool:
        # Start-time identity prevents confusing a reused PID with the owned process.
        if self.pid is None:
            return False
        try:
            fields = Path(f'/proc/{self.pid}/stat').read_text().rsplit(')', 1)[1].split()
            return int(fields[19]) == self.start_ticks
        except FileNotFoundError:
            return False

    def stop(self, timeout: float = 10) -> dict:
        started = time.monotonic()
        try:
            if not self.running():
                result = {'graceful': False, 'reason': 'exited_before_shutdown',
                          'forced': self.populated()}
            else:
                command('systemctl', '--user', 'kill', '--signal=SIGINT', '--kill-whom=main', self.name)
                while (self.running() or self.populated()) and time.monotonic() - started < timeout:
                    time.sleep(0.1)
                # Children count too. Check BEFORE forced cleanup so a clean main
                # exit cannot disguise a child subsequently killed by systemd.
                finished = not self.running() and not self.populated()
                outcome = command('systemctl', '--user', 'show', self.name,
                                  '--property=Result', '--property=ExecMainStatus', '--property=ExecMainCode')
                status = dict(line.split('=', 1) for line in outcome.splitlines())
                graceful = (finished and status.get('Result') == 'success'
                            and status.get('ExecMainCode') == '1' and status.get('ExecMainStatus') == '0')
                result = {'graceful': graceful, 'forced': not finished, 'systemd_result': status}
        except BaseException as original:
            self.cleanup_after_error(original)
            raise
        self.force_stop()
        result['duration_s'] = time.monotonic() - started
        return result

    def populated(self) -> bool:
        if self.group is None:
            raise RuntimeError(f'Cannot verify owned cgroup for {self.name}')
        try:
            return numeric_fields(self.group / 'cgroup.events')['populated'] != 0
        except FileNotFoundError:
            return False

    def force_stop(self):
        # This exact random unit was created by this owner. No other unit is touched.
        result = subprocess.run(['systemctl', '--user', 'stop', self.name],
                                capture_output=True, text=True, timeout=20)
        if result.returncode and 'not loaded' not in result.stderr:
            raise RuntimeError(f'Failed to stop owned unit {self.name}: {result.stderr}')
        # cgroup.events includes descendant groups, unlike cgroup.procs. A successful
        # systemctl invocation alone is not proof that every owned process exited.
        if self.group is not None:
            deadline = time.monotonic() + 5
            while self.group.exists():
                try:
                    if numeric_fields(self.group / 'cgroup.events')['populated'] == 0:
                        break
                except FileNotFoundError:
                    break  # The stopped group was collected between the reads.
                if time.monotonic() >= deadline:
                    raise RuntimeError(f'Owned cgroup still populated after stop: {self.name}: {self.group}')
                time.sleep(0.05)


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
