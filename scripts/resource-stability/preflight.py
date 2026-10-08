#!/usr/bin/env python3
"""Prove effective local resource controls before running a constrained workload."""
import argparse
import os
from pathlib import Path
import platform
import sys

from linux_runtime import Service, command, sample, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('Two available CPUs required')
    probe = None
    evidence = {'kernel': platform.release(), 'cpus': cpus,
                'systemd': command('systemctl', '--version').splitlines()[0],
                'browser_instrumentation': 'not qualified by this Linux-control preflight'}
    try:
        probe = Service('preflight', Path(sys.executable), ['-u', '-c',
                        'import signal,time; signal.signal(signal.SIGINT,lambda *_:exit(0)); time.sleep(60)'],
                        args.output, 512 * 1048576, 768 * 1048576, 2 * 1073741824, cpus,
                        {'TOKIO_WORKER_THREADS': '2', 'MALLOC_ARENA_MAX': '16'})
        evidence.update(service=probe.manifest, accounting=sample(probe.pid, probe.group))
        evidence['shutdown'] = probe.stop()
        probe = None
        evidence['linux_controls_passed'] = evidence['shutdown']['graceful']
        if not evidence['linux_controls_passed']:
            raise RuntimeError('Preflight service did not shut down gracefully')
    except BaseException as error:
        evidence['error'] = str(error)
        raise
    finally:
        if probe:
            evidence['cleanup'] = probe.stop()
        write_json(args.output / 'preflight.json', evidence)
    print(args.output / 'preflight.json')


if __name__ == '__main__':
    main()
