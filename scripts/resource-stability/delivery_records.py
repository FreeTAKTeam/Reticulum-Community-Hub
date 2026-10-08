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
            outgoing = expected_out if index == 0 else expected_in
            for token, sender_id in outgoing.items():
                rows = connection.execute(
                    'SELECT source, destination, content, direction, receipt_status FROM messages WHERE id = ? LIMIT 2',
                    [sender_id]).fetchall()
                wanted = (destinations[index], destinations[1 - index], content_for(token, index == 1), 'out', 'delivered')
                if rows != [wanted]:
                    raise RuntimeError('Sender durable row does not match its unique ID, payload, identities and receipt')
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
                            or metadata.get('source') != destinations[1]
                            or metadata.get('direction') != 'inbound' or metadata.get('reticulumd_inbound') is not True):
                        raise RuntimeError('RCH durable inbound source/state differs from observed traffic')
                else:
                    targets = metadata.get('reticulumd_receipt_targets', [])
                    if (record['destination'] != destinations[1] or record['delivery_state'] != 'delivered'
                            or metadata.get('acked') is not True or metadata.get('receipt_status') != 'delivered'
                            or len(targets) != 1 or targets[0].get('sdk_message_id') != message_id
                            or targets[0].get('destination') != destinations[1]
                            or targets[0].get('sdk_terminal') is not True or targets[0].get('status') != 'delivered'):
                        raise RuntimeError('RCH durable outbound receipt is missing or does not match admitted work')
    return authenticated
