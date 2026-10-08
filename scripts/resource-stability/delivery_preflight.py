#!/usr/bin/env python3
"""Qualify continuing real SDK/Reticulum delivery before a populated soak.

Two isolated daemons exchange encrypted traffic over TCP. A real RCH process
owns one side; the independent public SDK owns the other. This short lane cannot
pass final resource acceptance and does not insert synthetic messages/events.
"""
import argparse
import json
import os
from pathlib import Path
import time
import traceback
import uuid

from baseline import ENV, MIB, clone_db, wait_ready
from clients import Http, LocalRpc, free_ports
from delivery_records import content_for, verify_records
from fixture_preservation import PopulatedFixture, verify_policy
from fixtures import counts
from maintenance_evidence import MaintenanceObserver
from linux_runtime import Service, sample, sha256, write_json
from sdk_peer import SdkPeer
from service_discovery import discover

PERIODIC_ANNOUNCE_INTERVAL_S = 10


def healthy_sample(service):
    row = sample(service.pid, service.group)
    if row['process_start_ticks'] != service.start_ticks:
        raise RuntimeError(f'Owned process identity changed: {service.name}')
    events = row['cgroup']['memory_events']
    if events['oom'] or events['oom_kill'] or events.get('oom_group_kill', 0):
        raise RuntimeError(f'Owned service OOM events: {service.name}: {events}')
    return row


def finish_evidence(root, result, peer, services, fixture):
    """Cleanup and immutable-source checks are part of success, even after delivery."""
    def detail(error):
        return ''.join(traceback.format_exception(error)) if isinstance(error, BaseExceptionGroup) else str(error)
    if peer:
        try: peer.close()
        except BaseException as error: result['errors'].append(f'SDK shutdown: {type(error).__name__}: {detail(error)}')
    for role, service in reversed(list(services.items())):
        try:
            result['shutdown'][role] = service.stop()
            if not result['shutdown'][role]['graceful']: result['errors'].append(f'{role} required forced shutdown')
        except BaseException as error: result['errors'].append(f'{role} shutdown: {type(error).__name__}: {detail(error)}')
    if fixture:
        try:
            fixture.recheck()
            result['immutable_source_verified_after_cleanup'] = True
        except BaseException as error:
            result['errors'].append(f'Source fixture changed: {detail(error)}')
    result['delivery_preflight_passed'] = bool(result.get('delivery_preflight_passed') and not result['errors'])
    write_json(root / 'delivery-result.json', result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['server', 'daemon', 'sdk-peer', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--messages', type=int, default=5)
    parser.add_argument('--fixture-from', type=Path, help='Use immutable populated node0/RCH histories; attribution only')
    args = parser.parse_args()
    if not 1 <= args.messages <= 100:
        parser.error('preflight messages must be between one and 100 per direction')
    if args.fixture_from and args.messages < 65:
        parser.error('populated attribution requires 65..100 pairs at the frozen five-second interval')
    duration_limit = max(480 if args.fixture_from else 90, args.messages * 5 + 60)
    fixture = PopulatedFixture(args.fixture_from, duration_limit + 120) if args.fixture_from else None
    root = args.output.resolve()
    if len(os.fsencode(root / 'node0' / 'rpc.sock')) > 100:
        parser.error('output path too long for a private Unix socket')
    root.mkdir(parents=True, exist_ok=False)
    cpus = sorted(os.sched_getaffinity(0))[:2]
    api, command0, command1, response, peer_response, transport0, transport1 = free_ports(7)
    services = {}
    peer = None
    result = {'passed_final_acceptance': False, 'errors': [], 'shutdown': {},
              'lane': 'populated real delivery attribution' if fixture else 'real delivery preflight, empty history'}
    manifest = {'binary_sha256': {name: sha256(path) for name, path in
                [('rch', args.server), ('daemon', args.daemon), ('sdk_peer', args.sdk_peer)]},
                'messages_per_direction': args.messages, 'observation_deadline_s': duration_limit,
                'periodic_announce_interval_s': PERIODIC_ANNOUNCE_INTERVAL_S,
                'fixture': fixture.metadata if fixture else None, 'inbound_content_bytes': 480, 'outbound_content_bytes': 4096,
                'populated_activation_deadline_s': 120 if fixture else None,
                'cpus': cpus, 'stamp_cost': 0, 'environment': ENV,
                'harness_sha256': {p.name: sha256(p) for p in sorted(Path(__file__).parent.glob('*.py'))}}
    write_json(root / 'manifest.json', manifest)
    try:
        rpcs = []
        for index, (command_port, transport_port, neighbor) in enumerate([
                (command0, transport0, transport1), (command1, transport1, transport0)]):
            directory = root / f'node{index}'
            directory.mkdir()
            if fixture and index == 0:
                clone_db(fixture.paths['daemon'], directory / 'daemon.sqlite3')
                manifest['cloned_daemon_sha256'] = sha256(directory / 'daemon.sqlite3')
            config = directory / 'reticulum.toml'
            config.write_text(f'''[[interfaces]]
type = "tcp_client"
enabled = true
host = "127.0.0.1"
port = {neighbor}
[reticulum]
enable_transport = true
share_instance = false
''')
            if fixture and index == 0:
                with config.open('a') as config_stream:
                    config_stream.write('''[propagation_node]
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
            service = Service(f'node{index}', args.daemon,
                              ['--db', str(directory / 'daemon.sqlite3'), '--config', str(config),
                               '--rpc-unix', str(directory / 'rpc.sock'), '--transport', f'127.0.0.1:{transport_port}',
                               '--zmq-rpc-command', f'tcp://127.0.0.1:{command_port}',
                               '--announce-interval-secs', str(PERIODIC_ANNOUNCE_INTERVAL_S)],
                              directory, 512 * MIB, 768 * MIB, 2048 * MIB, cpus, ENV)
            services[f'node{index}'] = service
            manifest['services'] = {role: owned.manifest for role, owned in services.items()}
            write_json(root / 'manifest.json', manifest)
            rpc = LocalRpc(directory / 'rpc.sock')
            wait_ready(service, lambda: rpc.call('status'))
            rpcs.append(rpc)
        # Both TCP ends must exist before the long populated activation; do not
        # accumulate a minute of broadcasts into a disconnected interface.
        if fixture:
            activation_started = time.monotonic()
            rpc = rpcs[0]
            rpc.timeout = 120  # Same large-fixture setup allowance as baseline.py.
            try:
                manifest['propagation_policy'] = rpc.call('propagation_enable', {
                    'enabled': True, 'target_cost': 0, 'static_peers': fixture.peers,
                    'max_propagation_peers': 512, 'peer_entry_limit': 1_000_000,
                    'peer_entry_limit_per_peer': 1024}, deadline=activation_started + 120)
            finally:
                rpc.timeout = 10
            manifest['populated_activation_elapsed_s'] = time.monotonic() - activation_started
            verify_policy(manifest['propagation_policy'], fixture.peers)
            manifest['post_activation_counts'] = counts(root / 'node0' / 'daemon.sqlite3')
            write_json(root / 'manifest.json', manifest)
        destinations = [rpc.call('daemon_status_ex')['delivery_destination_hash'] for rpc in rpcs]
        if any(not isinstance(destination, str) or len(destination) != 32 for destination in destinations):
            raise RuntimeError(f'Invalid real delivery destinations: {destinations}')
        server_dir = root / 'rch'
        server_dir.mkdir()
        if fixture:
            clone_db(fixture.paths['rch'], server_dir / 'rch.sqlite3')
            manifest['cloned_rch_sha256'] = sha256(server_dir / 'rch.sqlite3')
        server = Service('rch', args.server, ['--bind', f'127.0.0.1:{api}', '--api-key', 'local-resource-fixture',
                         '--db-path', str(server_dir / 'rch.sqlite3'),
                         '--lxmf-zmq-command', f'tcp://127.0.0.1:{command0}',
                         '--lxmf-zmq-response', f'tcp://127.0.0.1:{response}'], server_dir,
                         768 * MIB, 1024 * MIB, 2048 * MIB, cpus, ENV)
        services['rch'] = server
        manifest['services'] = {role: owned.manifest for role, owned in services.items()}
        write_json(root / 'manifest.json', manifest)
        http = Http(api, 'local-resource-fixture')
        wait_ready(server, lambda: http.request('/Status'))
        destinations[0] = http.request('/api/v1/app/info')['reticulum_destination']
        if not isinstance(destinations[0], str) or len(destinations[0]) != 32:
            raise RuntimeError('RCH did not expose its registered service destination')
        before = http.request('/diagnostics/runtime')['counters']
        peer = SdkPeer(args.sdk_peer, f'tcp://127.0.0.1:{command1}', f'tcp://127.0.0.1:{peer_response}', root, cpus)
        destinations[1] = peer.destination
        if destinations[0] == destinations[1]:
            raise RuntimeError('Bidirectional test requires distinct service identities')
        manifest.update(destinations=destinations, http_url=http.base,
                        services={role: service.manifest for role, service in services.items()})
        write_json(root / 'manifest.json', manifest)
        manifest['discovery'] = discover(peer, http, rpcs, destinations, root)
        write_json(root / 'manifest.json', manifest)
        expected_in, expected_out, sdk_ids = {}, {}, {}
        observed_in, observed_out = {}, {}
        cursor = None
        if fixture:
            fixture.require_fresh(duration_limit)  # Recheck against actual post-setup time.
        started = time.monotonic()
        deadline = started + duration_limit
        maintenance = MaintenanceObserver(root / 'node0' / 'node0.log') if fixture else None
        admitted_pairs = {}
        completed_pairs = {}
        pair_outbound = {}
        dashboard_at = started
        resources_at = started
        def peer_call(operation, token, **payload):
            return peer.call(operation, token, timeout=min(10, deadline - time.monotonic()), **payload)

        next_send = started
        outbound_states = {}
        with (root / 'samples.jsonl').open('w') as samples:
            while time.monotonic() < deadline:
                now = time.monotonic()
                if maintenance:
                    maintenance.poll()
                if len(expected_in) < args.messages and now >= next_send:
                    nonce = uuid.uuid4().hex
                    inbound = f'resource-peer-to-rch-{nonce}'
                    outbound = f'resource-rch-to-peer-{nonce}'
                    pair_outbound[inbound] = outbound
                    content_in = content_for(inbound, True)
                    content_out = content_for(outbound, False)
                    sent = peer_call('send', inbound, destination=destinations[0], content=content_in)
                    expected_in[inbound] = sent['message_id']
                    admitted_pairs[inbound] = now
                    sent = http.request('/Chat/Message', {'Content': content_out, 'Scope': 'dm',
                                        'Destination': destinations[1], 'FileIDs': [], 'ImageIDs': []}, deadline=deadline)
                    expected_out[outbound] = sent['MessageID']
                    next_send = now + 5
                batch = peer_call('poll', uuid.uuid4().hex, cursor=cursor)['batch']
                cursor = batch['next_cursor']
                for event in batch['events']:
                    message = event.get('payload', {}).get('message', {})
                    content = message.get('content', '')
                    for token in expected_out:
                        if token in content:
                            if content != content_for(token, False):
                                raise RuntimeError('Peer received changed message content')
                            observed_out.setdefault(token, set()).add(message['id'])
                for message in http.request('/Chat/Messages?limit=200', deadline=deadline):
                    if message.get('MessageID') in expected_out.values():
                        outbound_states[message['MessageID']] = message.get('State')
                    for token in expected_in:
                        if token in message.get('Content', ''):
                            if message['Content'] != content_for(token, True):
                                raise RuntimeError('RCH received changed message content')
                            observed_in.setdefault(token, set()).add(message['MessageID'])
                for token, message_id in expected_in.items():
                    previous = sdk_ids.get(token)
                    if previous and previous.get('terminal') and previous.get('state') == 'delivered':
                        continue
                    status = peer_call('status', uuid.uuid4().hex, message_id=message_id)['status']
                    if status and status.get('message_id') != message_id:
                        raise RuntimeError('SDK status response has a different sender message ID')
                    sdk_ids[token] = status
                for inbound, outbound in pair_outbound.items():
                    status = sdk_ids.get(inbound)
                    if (inbound in observed_in and outbound in observed_out and status
                            and status.get('state') == 'delivered' and status.get('terminal')
                            and outbound_states.get(expected_out[outbound]) == 'delivered'):
                        completed_pairs.setdefault(inbound, time.monotonic())
                row = {'elapsed_s': time.monotonic() - started,
                       'expected_each': len(expected_in), 'received_rch': len(observed_in), 'received_peer': len(observed_out),
                       'diagnostics': http.request('/diagnostics/runtime', deadline=deadline)}
                if fixture and now >= dashboard_at:
                    row['dashboard'] = {}
                    for path in ('/Client', '/Identities', '/api/rem/peers', '/Chat/Messages?limit=200'):
                        request_started = time.monotonic()
                        payload = http.request(path, deadline=deadline)
                        row['dashboard'][path] = {'duration_s': time.monotonic() - request_started, 'response_items': len(payload)}
                    dashboard_at = now + 30
                if fixture and now >= resources_at:
                    row['daemon_resources'] = rpcs[0].call('daemon_status_ex', deadline=deadline)['resources']
                    resources_at = now + 5
                if maintenance:
                    row['maintenance'] = list(maintenance.completions)
                for role, service in services.items(): row[role] = healthy_sample(service)
                samples.write(json.dumps(row) + '\n')
                samples.flush()
                receipts_complete = (all(status and status.get('state') == 'delivered' and status.get('terminal')
                                         for status in sdk_ids.values()) and len(sdk_ids) == args.messages and
                                     all(outbound_states.get(message_id) == 'delivered' for message_id in expected_out.values()))
                if len(expected_in) == args.messages and len(observed_in) == args.messages and len(observed_out) == args.messages and receipts_complete:
                    if maintenance:
                        try:
                            maintenance.verify_post_cycle(admitted_pairs, completed_pairs)
                        except RuntimeError:
                            time.sleep(0.25)
                            continue
                    break
                time.sleep(0.25)
        if len(observed_in) != args.messages or len(observed_out) != args.messages:
            raise RuntimeError(f'Delivery deadline: RCH {len(observed_in)}/{args.messages}, peer {len(observed_out)}/{args.messages}')
        if not receipts_complete:
            raise RuntimeError(f'Receipt deadline: SDK {sdk_ids}, RCH {outbound_states}')
        if any(len(ids) != 1 for ids in [*observed_in.values(), *observed_out.values()]):
            raise RuntimeError('Duplicate unique message IDs for one sent token')
        if maintenance:
            maintenance.poll()
            maintenance.verify_post_cycle(admitted_pairs, completed_pairs)
            result['maintenance'] = maintenance.completions
            result['pair_admitted_monotonic_s'] = admitted_pairs
            result['pair_completed_monotonic_s'] = completed_pairs
            result['fixture_qualification'] = fixture.qualify(
                root / 'node0' / 'daemon.sqlite3', root / 'rch' / 'rch.sqlite3',
                sum(item['pruned_peer_entries'] for item in maintenance.completions), deadline=deadline)
        authenticated_received = verify_records(root, destinations, expected_in, expected_out, observed_in, observed_out, deadline=deadline)
        after = http.request('/diagnostics/runtime', deadline=deadline)['counters']
        polls = after['reticulumd_inbound_event_polls_total'] - before['reticulumd_inbound_event_polls_total']
        poll_errors = after['reticulumd_inbound_event_poll_errors_total'] - before['reticulumd_inbound_event_poll_errors_total']
        if polls <= 0 or poll_errors != 0:
            raise RuntimeError(f'Polling unavailable or failing: {polls} attempts, {poll_errors} errors')
        result['final_runtime'] = {role: healthy_sample(service) for role, service in services.items()}
        if time.monotonic() >= deadline:
            raise TimeoutError('Whole delivery qualification deadline exceeded')
        result.update(delivery_preflight_passed=True, polls=polls, poll_errors=poll_errors, expected_in=expected_in, expected_out=expected_out,
                      observed_in={k: list(v) for k, v in observed_in.items()}, observed_out={k: list(v) for k, v in observed_out.items()},
                      sender_status=sdk_ids, authenticated_received=authenticated_received, rch_outbound_states=outbound_states, duration_s=time.monotonic() - started)
    except BaseException as error:
        result['errors'].append(''.join(traceback.format_exception(error)))
    finally:
        finish_evidence(root, result, peer, services, fixture)
    print(json.dumps(result, indent=2))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
