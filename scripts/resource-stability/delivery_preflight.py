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

from baseline import ENV, MIB, wait_ready
from clients import Http, LocalRpc, free_ports
from delivery_records import content_for, verify_records
from linux_runtime import Service, sample, sha256, write_json
from sdk_peer import SdkPeer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['server', 'daemon', 'sdk-peer', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--messages', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.messages <= 100:
        parser.error('preflight messages must be between one and 100 per direction')
    root = args.output.resolve()
    if len(os.fsencode(root / 'node0' / 'rpc.sock')) > 100:
        parser.error('output path too long for a private Unix socket')
    root.mkdir(parents=True, exist_ok=False)
    cpus = sorted(os.sched_getaffinity(0))[:2]
    api, command0, command1, response, peer_response, transport0, transport1 = free_ports(7)
    services = {}
    peer = None
    result = {'passed_final_acceptance': False, 'errors': [], 'shutdown': {},
              'lane': 'real delivery preflight, empty history'}
    manifest = {'binary_sha256': {name: sha256(path) for name, path in
                [('rch', args.server), ('daemon', args.daemon), ('sdk_peer', args.sdk_peer)]},
                'messages_per_direction': args.messages, 'inbound_content_bytes': 480, 'outbound_content_bytes': 4096,
                'cpus': cpus, 'stamp_cost': 0, 'environment': ENV,
                'harness_sha256': {p.name: sha256(p) for p in sorted(Path(__file__).parent.glob('*.py'))}}
    write_json(root / 'manifest.json', manifest)
    try:
        rpcs = []
        for index, (command_port, transport_port, neighbor) in enumerate([
                (command0, transport0, transport1), (command1, transport1, transport0)]):
            directory = root / f'node{index}'
            directory.mkdir()
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
            service = Service(f'node{index}', args.daemon,
                              ['--db', str(directory / 'daemon.sqlite3'), '--config', str(config),
                               '--rpc-unix', str(directory / 'rpc.sock'), '--transport', f'127.0.0.1:{transport_port}',
                               '--zmq-rpc-command', f'tcp://127.0.0.1:{command_port}', '--announce-interval-secs', '1'],
                              directory, 512 * MIB, 768 * MIB, 2048 * MIB, cpus, ENV)
            services[f'node{index}'] = service
            rpc = LocalRpc(directory / 'rpc.sock')
            wait_ready(service, lambda: rpc.call('status'))
            rpcs.append(rpc)
        destinations = [rpc.call('daemon_status_ex')['delivery_destination_hash'] for rpc in rpcs]
        if any(not isinstance(destination, str) or len(destination) != 32 for destination in destinations):
            raise RuntimeError(f'Invalid real delivery destinations: {destinations}')
        server_dir = root / 'rch'
        server_dir.mkdir()
        server = Service('rch', args.server, ['--bind', f'127.0.0.1:{api}', '--api-key', 'local-resource-fixture',
                         '--db-path', str(server_dir / 'rch.sqlite3'),
                         '--lxmf-zmq-command', f'tcp://127.0.0.1:{command0}',
                         '--lxmf-zmq-response', f'tcp://127.0.0.1:{response}'], server_dir,
                         768 * MIB, 1024 * MIB, 2048 * MIB, cpus, ENV)
        services['rch'] = server
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
        # Wait for real signed announces on both sides before sending traffic.
        # Re-announcing is a public SDK operation; do not seed identity tables.
        announce_deadline = time.monotonic() + 30
        while True:
            peer.call('announce', uuid.uuid4().hex)
            learned = [any(record['peer'] == destinations[1 - index]
                           for record in rpc.call('list_announces', {'limit': 100})['announces'])
                       for index, rpc in enumerate(rpcs)]
            if all(learned):
                break
            if time.monotonic() >= announce_deadline:
                raise RuntimeError(f'Real service announces not learned: {learned}')
            time.sleep(1)
        expected_in, expected_out, sdk_ids = {}, {}, {}
        observed_in, observed_out = {}, {}
        cursor = None
        started = time.monotonic()
        deadline = started + max(90, args.messages * 5 + 60)
        def peer_call(operation, token, **payload):
            return peer.call(operation, token, timeout=min(10, deadline - time.monotonic()), **payload)

        next_send = started
        outbound_states = {}
        with (root / 'samples.jsonl').open('w') as samples:
            while time.monotonic() < deadline:
                now = time.monotonic()
                if len(expected_in) < args.messages and now >= next_send:
                    nonce = uuid.uuid4().hex
                    inbound = f'resource-peer-to-rch-{nonce}'
                    outbound = f'resource-rch-to-peer-{nonce}'
                    content_in = content_for(inbound, True)
                    content_out = content_for(outbound, False)
                    sent = peer_call('send', inbound, destination=destinations[0], content=content_in)
                    expected_in[inbound] = sent['message_id']
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
                    status = peer_call('status', uuid.uuid4().hex, message_id=message_id)['status']
                    if status and status.get('message_id') != message_id:
                        raise RuntimeError('SDK status response has a different sender message ID')
                    sdk_ids[token] = status
                row = {'elapsed_s': time.monotonic() - started,
                       'expected_each': len(expected_in), 'received_rch': len(observed_in), 'received_peer': len(observed_out),
                       'diagnostics': http.request('/diagnostics/runtime', deadline=deadline)}
                for role, service in services.items(): row[role] = sample(service.pid, service.group)
                samples.write(json.dumps(row) + '\n')
                samples.flush()
                receipts_complete = (all(status and status.get('state') == 'delivered' and status.get('terminal')
                                         for status in sdk_ids.values()) and len(sdk_ids) == args.messages and
                                     all(outbound_states.get(message_id) == 'delivered' for message_id in expected_out.values()))
                if len(expected_in) == args.messages and len(observed_in) == args.messages and len(observed_out) == args.messages and receipts_complete:
                    break
                time.sleep(0.25)
        if len(observed_in) != args.messages or len(observed_out) != args.messages:
            raise RuntimeError(f'Delivery deadline: RCH {len(observed_in)}/{args.messages}, peer {len(observed_out)}/{args.messages}')
        if not receipts_complete:
            raise RuntimeError(f'Receipt deadline: SDK {sdk_ids}, RCH {outbound_states}')
        if any(len(ids) != 1 for ids in [*observed_in.values(), *observed_out.values()]):
            raise RuntimeError('Duplicate unique message IDs for one sent token')
        authenticated_received = verify_records(root, destinations, expected_in, expected_out, observed_in, observed_out)
        after = http.request('/diagnostics/runtime', deadline=deadline)['counters']
        polls = after['reticulumd_inbound_event_polls_total'] - before['reticulumd_inbound_event_polls_total']
        poll_errors = after['reticulumd_inbound_event_poll_errors_total'] - before['reticulumd_inbound_event_poll_errors_total']
        if polls <= 0 or poll_errors != 0:
            raise RuntimeError(f'Polling unavailable or failing: {polls} attempts, {poll_errors} errors')
        if time.monotonic() >= deadline:
            raise TimeoutError('Whole delivery qualification deadline exceeded')
        result.update(delivery_preflight_passed=True, polls=polls, poll_errors=poll_errors, expected_in=expected_in, expected_out=expected_out,
                      observed_in={k: list(v) for k, v in observed_in.items()}, observed_out={k: list(v) for k, v in observed_out.items()},
                      sender_status=sdk_ids, authenticated_received=authenticated_received, rch_outbound_states=outbound_states, duration_s=time.monotonic() - started)
    except Exception as error:
        result['errors'].append(''.join(traceback.format_exception(error)))
    finally:
        if peer:
            try: peer.close()
            except Exception as error: result['errors'].append(f'SDK shutdown: {error}')
        for role, service in reversed(list(services.items())):
            try:
                result['shutdown'][role] = service.stop()
                if not result['shutdown'][role]['graceful']: result['errors'].append(f'{role} required forced shutdown')
            except Exception as error: result['errors'].append(f'{role} shutdown: {error}')
        result['delivery_preflight_passed'] = bool(result.get('delivery_preflight_passed') and not result['errors'])
        write_json(root / 'delivery-result.json', result)
    print(json.dumps(result, indent=2))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
