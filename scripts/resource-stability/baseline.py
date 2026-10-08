#!/usr/bin/env python3
"""Measure current binaries with populated histories and UI/API traffic.

This attribution lane deliberately cannot pass final acceptance: real peer delivery
and browser qualification are separate required work. It never changes production.
"""
from contextlib import closing
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

from clients import Http, LocalRpc, free_ports
from fixtures import counts, seed_daemon
from linux_runtime import Service, sample, sha256, write_json

MIB = 1048576
# Freeze source identity at import, before launching processes or generating data.
HARNESS_SHA256 = {path.name: sha256(path) for path in sorted(Path(__file__).parent.glob('*.py'))}
ENV = {'RUST_LOG': 'info', 'TOKIO_WORKER_THREADS': '2', 'MALLOC_ARENA_MAX': '16',
       'R3AKT_ENABLE_ZMQ_EVENT_POLL': '1'}


def wait_ready(service, probe, timeout=60):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        if not service.running():
            raise RuntimeError(f'{service.name} exited before readiness; inspect its log')
        try:
            return probe()
        except (OSError, RuntimeError, ValueError) as error:
            last_error = str(error)
            time.sleep(0.1)
    raise RuntimeError(f'Readiness deadline: {last_error}')


def clone_db(source, target):
    with closing(sqlite3.connect(f'file:{source.resolve()}?mode=ro', uri=True)) as src, closing(sqlite3.connect(target)) as dst, dst:
        src.backup(dst)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--daemon', type=Path, required=True)
    parser.add_argument('--rch-fixture', type=Path, required=True)
    parser.add_argument('--wire-fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=600)
    parser.add_argument('--small', action='store_true')
    parser.add_argument('--ui-dist-path', type=Path, help='Serve an existing frozen UI bundle for browser preflight')
    parser.add_argument('--fixture-from', type=Path, help='Reuse immutable fixture databases from a previous attribution run')
    parser.add_argument('--resource-diagnostics', action='store_true', help='Sample daemon_status_ex owned-buffer diagnostics')
    args = parser.parse_args()
    if args.duration < 10:
        parser.error('duration must be at least ten seconds')
    args.output = args.output.resolve()
    if len(os.fsencode(args.output / 'fixture' / 'init' / 'rpc.sock')) > 100:
        parser.error('Choose a shorter output path: private Unix socket paths must fit within 100 bytes')
    args.output.mkdir(parents=True, exist_ok=False)
    fixture = args.output / 'fixture'
    run = args.output / 'runtime'
    fixture.mkdir()
    run.mkdir()
    services = {}
    cpus = sorted(os.sched_getaffinity(0))[:2]
    api, command, response, transport = free_ports(4)
    config = args.output / 'reticulum.toml'
    config.write_text('''interfaces = []
[reticulum]
enable_transport = true
share_instance = false
[propagation_node]
enabled = true
stamp_cost = 0
peering_cost = 0
message_storage_limit_mb = 256
peer_entry_limit = 1000000
peer_entry_limit_per_peer = 1024
peer_entry_ttl_secs = 604800
completed_peer_entry_ttl_secs = 2592000
max_propagation_peers = 512
storage_maintenance_interval_secs = 300
''')
    manifest = {'lane': 'baseline attribution only', 'final_acceptance_qualified': False,
                'reason': 'Continuing independent real delivery and browser workload are not yet present.',
                'duration_s': args.duration, 'sample_interval_s': 5, 'dashboard_interval_s': 30,
                'environment': ENV, 'allocator_note': '16 arenas models old production geometry; not an allocator fix.',
                'historical_stamp_cost': 0, 'config': config.read_text(),
                'harness_sha256': HARNESS_SHA256,
                'binary_sha256': {'rch': sha256(args.server), 'daemon': sha256(args.daemon)}}
    ui_args = []
    if args.ui_dist_path:
        bundle = args.ui_dist_path.resolve()
        if not (bundle / 'index.html').is_file():
            parser.error('--ui-dist-path must contain index.html')
        manifest['ui_sha256'] = {str(path.relative_to(bundle)): sha256(path) for path in sorted(bundle.rglob('*')) if path.is_file()}
        ui_args = ['--ui-dist-path', str(bundle)]
    result = {'passed_final_acceptance': False, 'errors': [], 'shutdown': {}}
    try:
        if args.fixture_from:
            source = args.fixture_from.resolve() / 'fixture'
            clone_db(source / 'daemon.sqlite3', fixture / 'daemon.sqlite3')
            clone_db(source / 'rch.sqlite3', fixture / 'rch.sqlite3')
            manifest['fixture'] = counts(fixture / 'daemon.sqlite3')
            manifest['fixture']['database_sha256'] = sha256(fixture / 'daemon.sqlite3')
            manifest['fixture_source'] = str(source)
            manifest['fixture_source_manifest_sha256'] = sha256(args.fixture_from / 'manifest.json')
            source_manifest = json.loads((args.fixture_from / 'manifest.json').read_text())
            manifest['rch_fixture'] = source_manifest['rch_fixture']
            peers = manifest['fixture']['peers']
        else:
            generate_fixture(args, fixture, config, cpus, services, manifest)
            peers = manifest['fixture']['peers']
        clone_db(fixture / 'daemon.sqlite3', run / 'daemon.sqlite3')
        clone_db(fixture / 'rch.sqlite3', run / 'rch.sqlite3')
        daemon = Service('daemon', args.daemon,
                         ['--db', str(run / 'daemon.sqlite3'), '--config', str(config),
                          '--rpc-unix', str(run / 'rpc.sock'), '--transport', f'127.0.0.1:{transport}',
                          '--zmq-rpc-command', f'tcp://127.0.0.1:{command}'], run,
                         512 * MIB, 768 * MIB, 2048 * MIB, cpus, ENV)
        services['daemon'] = daemon
        rpc = LocalRpc(run / 'rpc.sock', timeout=120)
        wait_ready(daemon, lambda: rpc.call('status'))
        # Activate a bounded current peer set; remaining stored histories stay durable.
        active_peers = [f'{index + 1:032x}' for index in range(min(512, peers))]
        policy = rpc.call('propagation_enable', {'enabled': True, 'target_cost': 0,
                         'static_peers': active_peers, 'max_propagation_peers': 512,
                         'peer_entry_limit': 1_000_000, 'peer_entry_limit_per_peer': 1024})
        manifest['active_peers'] = len(active_peers)
        manifest['post_activation_counts'] = counts(run / 'daemon.sqlite3')
        manifest['propagation_policy'] = policy
        rpc.timeout = 10
        server = Service('rch', args.server,
                         ['--bind', f'127.0.0.1:{api}', '--api-key', 'local-resource-fixture',
                          '--db-path', str(run / 'rch.sqlite3'),
                          '--lxmf-zmq-command', f'tcp://127.0.0.1:{command}',
                          '--lxmf-zmq-response', f'tcp://127.0.0.1:{response}'] + ui_args, run,
                         768 * MIB, 1024 * MIB, 2048 * MIB, cpus, ENV)
        services['rch'] = server
        http = Http(api, 'local-resource-fixture')
        manifest['http_url'] = http.base
        status = wait_ready(server, lambda: http.request('/Status'))
        manifest['initial_status'] = status
        before = http.request('/diagnostics/runtime')
        if not before['reticulumd_source_configured']:
            raise RuntimeError('RCH is not using the real daemon')
        manifest['services'] = {role: service.manifest for role, service in services.items()}
        manifest['observation_started_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        write_json(args.output / 'manifest.json', manifest)  # Freeze before observation.
        print(f'Observation running: {args.output}', flush=True)
        started = time.monotonic()
        dashboard_at = 0
        announce_at = 0
        dashboard_requests = 0
        with (args.output / 'samples.jsonl').open('w') as output:
            while True:
                elapsed = time.monotonic() - started
                row = {'elapsed_s': elapsed, 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
                for role, service in services.items():
                    if not service.running():
                        raise RuntimeError(f'{role} exited during observation')
                    row[role] = sample(service.pid, service.group)
                if elapsed >= dashboard_at:
                    dashboard = {}
                    for path in ('/Client', '/Identities', '/api/rem/peers', '/Chat/Messages?limit=200'):
                        request_started = time.monotonic()
                        response_payload = http.request(path)
                        dashboard[path] = {'duration_s': time.monotonic() - request_started,
                                           'response_items': len(response_payload)}
                        dashboard_requests += 1
                    row['dashboard'] = dashboard
                    dashboard_at = elapsed + 30
                if elapsed >= announce_at:
                    # Existing test/control API; records this is synthetic announce ingress.
                    rpc.call('announce_received', {'peer': active_peers[int(elapsed) % len(active_peers)],
                             'timestamp': int(time.time()), 'name': 'resource-active-peer',
                             'capabilities': ['lxmf'], 'aspect': 'lxmf.propagation', 'hops': 1,
                             'stamp_cost': 0, 'peering_cost': 0})
                    announce_at = elapsed + 5
                row['diagnostics'] = http.request('/diagnostics/runtime')
                if args.resource_diagnostics and 'dashboard' in row:
                    row['daemon_resources'] = rpc.call('daemon_status_ex')['resources']
                output.write(json.dumps(row, sort_keys=True) + '\n')
                output.flush()
                if elapsed >= args.duration:
                    break
                time.sleep(min(5, max(0, args.duration - (time.monotonic() - started))))
        after = row['diagnostics']
        result.update(baseline_observation_complete=True, dashboard_requests=dashboard_requests,
                      fixture_counts_after=counts(run / 'daemon.sqlite3'),
                      event_poll_delta=after['reticulumd_inbound']['event_polls_total'] - before['reticulumd_inbound']['event_polls_total'],
                      event_poll_error_delta=after['reticulumd_inbound']['event_poll_errors_total'] - before['reticulumd_inbound']['event_poll_errors_total'])
    except BaseException as error:
        result['errors'].append(str(error))
        raise
    finally:
        for role in reversed(list(services)):
            try:
                result['shutdown'][role] = services[role].stop()
            except Exception as error:
                result['shutdown'][role] = {'graceful': False, 'error': str(error)}
        write_json(args.output / 'manifest.json', manifest)
        write_json(args.output / 'baseline-result.json', result)
    print(json.dumps(result, indent=2))


def generate_fixture(args, fixture, config, cpus, services, manifest):
    # Let the real daemon create its schema, then stop it before any fixture write.
    init = fixture / 'init'
    init.mkdir()
    initializer = Service('initializer', args.daemon,
                          ['--db', str(fixture / 'daemon.sqlite3'), '--config', str(config),
                           '--rpc-unix', str(init / 'rpc.sock')], init,
                          512 * MIB, 768 * MIB, 2048 * MIB, cpus, ENV)
    services['initializer'] = initializer
    wait_ready(initializer, lambda: LocalRpc(init / 'rpc.sock').call('status'))
    init_shutdown = initializer.stop()
    del services['initializer']
    if not init_shutdown['graceful']:
        raise RuntimeError(f'Initializer shutdown failed: {init_shutdown}')
    payloads, peers, associations, announces, messages = (
        (1024, 8, 4096, 200, 100) if args.small else (135_893, 940, 1_000_000, 100_000, 25_000))
    manifest['fixture'] = seed_daemon(fixture / 'daemon.sqlite3', args.wire_fixture,
                                      payloads, peers, associations)
    generated = subprocess.run([str(args.rch_fixture.resolve()), str(fixture / 'rch.sqlite3'),
                                str(announces), str(messages)], check=True,
                               capture_output=True, text=True, timeout=600)
    manifest['rch_fixture'] = json.loads(generated.stdout)
    manifest['rch_fixture']['generator_sha256'] = sha256(args.rch_fixture)
    manifest['rch_fixture']['database_sha256'] = sha256(fixture / 'rch.sqlite3')


if __name__ == '__main__':
    main()
