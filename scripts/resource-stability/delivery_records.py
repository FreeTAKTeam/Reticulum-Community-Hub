"""Cross-check real traffic through distinct SDK, RCH and wire identifier spaces."""
import json
from pathlib import Path

import msgpack
from evidence_db import readonly


def content_for(token, inbound):
    return token + 'x' * ((480 if inbound else 4096) - len(token))


def verify_records(root: Path, destinations, expected_in, expected_out, observed_in, observed_out, *, deadline=None):
    sender_ids = [*expected_in.values(), *expected_out.values()]
    if len(set(sender_ids)) != len(sender_ids):
        raise RuntimeError('Returned sender message IDs are not unique')
    if set(observed_in) != set(expected_in) or set(observed_out) != set(expected_out):
        raise RuntimeError('Observed traffic does not match every admitted token')
    if any(len(ids) != 1 for ids in [*observed_in.values(), *observed_out.values()]):
        raise RuntimeError('Each token must have exactly one receiver message ID')
    daemon_out = verify_rch_records(root, destinations, expected_out, observed_in, deadline=deadline)
    sender_ids = [*expected_in.values(), *daemon_out.values()]
    if len(set(sender_ids)) != len(sender_ids):
        raise RuntimeError('Admitted daemon sender message IDs are not unique')
    authenticated = {}
    for index, expected in [(0, expected_in), (1, expected_out)]:
        with readonly(root / f'node{index}' / 'daemon.sqlite3', deadline=deadline) as connection:
            for token in expected:
                rows = connection.execute(
                    "SELECT id, fields FROM messages WHERE direction = 'in' AND source = ? AND destination = ? AND content = ? LIMIT 2",
                    [destinations[1 - index], destinations[index], content_for(token, index == 0)]).fetchall()
                if len(rows) != 1:
                    raise RuntimeError('Receiver durable payload is missing, changed or duplicated')
                metadata = json.loads(rows[0][1])['_lxmf']
                if metadata.get('signature_valid') is not True or metadata.get('transport_encrypted') is not True:
                    raise RuntimeError(f'Received payload not authenticated/encrypted: {metadata}')
                if index == 1 and rows[0][0] not in observed_out[token]:
                    raise RuntimeError('SDK event and receiver durable message IDs do not match')
                authenticated[token] = rows[0][0]
            outgoing = daemon_out if index == 0 else expected_in
            for token, sender_id in outgoing.items():
                rows = connection.execute(
                    'SELECT source, destination, content, direction, receipt_status FROM messages WHERE id = ? LIMIT 2',
                    [sender_id]).fetchall()
                wanted = (destinations[index], destinations[1 - index], content_for(token, index == 1), 'out', 'delivered')
                if rows != [wanted]:
                    raise RuntimeError('Sender durable row does not match its unique ID, payload, identities and receipt')
    return authenticated


def verify_rch_records(root, destinations, expected_out, observed_in, *, deadline):
    daemon_out = {}
    with readonly(root / 'rch' / 'rch.sqlite3', deadline=deadline) as connection:
        for inbound, observed in [(True, observed_in), (False, {k: {v} for k, v in expected_out.items()})]:
            for token, ids in observed.items():
                if len(ids) != 1:
                    raise RuntimeError('One token has multiple RCH message IDs')
                message_id = next(iter(ids))
                rows = connection.execute('SELECT payload FROM rch_messages WHERE message_id = ? LIMIT 2', [message_id]).fetchall()
                if len(rows) != 1:
                    raise RuntimeError('RCH durable row missing or duplicated')
                record = msgpack.unpackb(rows[0][0], raw=False)
                if record['message_id'] != message_id or record['content'] != content_for(token, inbound):
                    raise RuntimeError('RCH durable ID or full content differs from observed traffic')
                metadata = record['delivery_metadata']
                if inbound:
                    if (record['sender'] != destinations[1] or record['delivery_state'] != 'received'
                            or metadata.get('direction') != 'inbound' or metadata.get('reticulumd_inbound') is not True):
                        raise RuntimeError('RCH durable inbound source/state differs from observed traffic')
                else:
                    targets = metadata.get('reticulumd_receipt_targets', [])
                    daemon_id = metadata.get('reticulumd_message_id')
                    if (record['destination'] != destinations[1] or record['delivery_state'] != 'delivered'
                            or record.get('delivery_method') != 'durable_broker'
                            or metadata.get('acked') is not True
                            or metadata.get('receipt_pending') is not False
                            or metadata.get('dispatch_status') != 'accepted' or metadata.get('reticulumd_dispatch_count') != 1
                            or not isinstance(daemon_id, str) or not daemon_id
                            or len(targets) != 1 or targets[0].get('message_id') != daemon_id
                            or targets[0].get('destination') != destinations[1]
                            or targets[0].get('status') != 'delivered'):
                        raise RuntimeError('RCH durable outbound receipt is missing or does not match admitted work')
                    # Bind the business ID to the durable admission owner before
                    # looking up its distinct daemon sender ID. A presentation
                    # receipt alone must not qualify missing or mismatched work.
                    rows = connection.execute(
                        'SELECT daemon_message_id, state, receipt_status FROM rch_broker_dispatch WHERE message_id = ? LIMIT 2',
                        [message_id]).fetchall()
                    if rows != [(daemon_id, 'terminal', 'delivered')]:
                        raise RuntimeError('RCH durable admission does not match its terminal delivered receipt')
                    daemon_out[token] = daemon_id
    return daemon_out
