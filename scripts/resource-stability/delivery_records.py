"""Cross-check real traffic through distinct SDK, RCH and wire identifier spaces."""
import json
from pathlib import Path

import msgpack
from evidence_db import readonly


def content_for(token, inbound):
    return token + 'x' * ((480 if inbound else 4096) - len(token))


def verify_records(root: Path, destinations, expected_in, expected_out, observed_in, observed_out, *,
                   deadline=None, recipients=None, outbound_recipients=None):
    """Verify DM traffic, or explicit complete fanout plans across recipient nodes.

    Optional recipients maps delivery destinations to node directories. Every
    outbound_recipients[token] must map that complete recipient set to distinct
    admitted daemon IDs; observed_out[token] then maps destinations to singleton
    wire-ID sets. Outbound results in this mode map destinations to verified IDs.
    Omitting both options preserves the existing DM arguments and result shape.
    """
    sender_ids = [*expected_in.values(), *expected_out.values()]
    if len(set(sender_ids)) != len(sender_ids):
        raise RuntimeError('Returned sender message IDs are not unique')
    if set(observed_in) != set(expected_in) or set(observed_out) != set(expected_out):
        raise RuntimeError('Observed traffic does not match every admitted token')
    fanout = recipients is not None or outbound_recipients is not None
    if fanout:
        verify_fanout_plan(recipients, outbound_recipients, expected_out, observed_out)
        receiver_ids = [ids for by_recipient in observed_out.values() for ids in by_recipient.values()]
    else:
        receiver_ids = list(observed_out.values())
    if any(len(ids) != 1 for ids in [*observed_in.values(), *receiver_ids]):
        raise RuntimeError('Each token must have exactly one receiver message ID')
    daemon_out = verify_rch_records(root, destinations, expected_out, observed_in, deadline=deadline,
                                    outbound_recipients=outbound_recipients)
    plans = daemon_out if fanout else {token: {destinations[1]: sender_id} for token, sender_id in daemon_out.items()}
    routes = recipients if fanout else {destinations[1]: 'node1'}
    observed = observed_out if fanout else {token: {destinations[1]: ids} for token, ids in observed_out.items()}
    sender_ids = [*expected_in.values(), *(sender_id for plan in plans.values() for sender_id in plan.values())]
    if len(set(sender_ids)) != len(sender_ids):
        raise RuntimeError('Admitted daemon sender message IDs are not unique')
    authenticated = {}
    with readonly(root / 'node0' / 'daemon.sqlite3', deadline=deadline) as connection:
        for token in expected_in:
            authenticated[token] = verify_receiver(connection, token, destinations[1], destinations[0], True)
        for token, plan in plans.items():
            for recipient, sender_id in plan.items():
                verify_sender(connection, token, sender_id, destinations[0], recipient, False)
    with readonly(root / 'node1' / 'daemon.sqlite3', deadline=deadline) as connection:
        for token, sender_id in expected_in.items():
            verify_sender(connection, token, sender_id, destinations[1], destinations[0], True)
    for recipient, directory in routes.items():
        with readonly(root / directory / 'daemon.sqlite3', deadline=deadline) as connection:
            for token in expected_out:
                wire_id = verify_receiver(connection, token, destinations[0], recipient, False, observed[token][recipient])
                if fanout:
                    authenticated.setdefault(token, {})[recipient] = wire_id
                else:
                    authenticated[token] = wire_id
    return authenticated


def verify_sender(connection, token, sender_id, source, destination, inbound):
    rows = connection.execute(
        'SELECT source, destination, content, direction, receipt_status FROM messages WHERE id = ? LIMIT 2',
        [sender_id]).fetchall()
    if rows != [(source, destination, content_for(token, inbound), 'out', 'delivered')]:
        raise RuntimeError('Sender durable row does not match its unique ID, payload, identities and receipt')


def verify_receiver(connection, token, source, destination, inbound, observed_ids=None):
    rows = connection.execute(
        "SELECT id, fields FROM messages WHERE direction = 'in' AND source = ? AND destination = ? AND content = ? LIMIT 2",
        [source, destination, content_for(token, inbound)]).fetchall()
    if len(rows) != 1:
        raise RuntimeError('Receiver durable payload is missing, changed or duplicated')
    metadata = json.loads(rows[0][1])['_lxmf']
    if metadata.get('signature_valid') is not True or metadata.get('transport_encrypted') is not True:
        raise RuntimeError(f'Received payload not authenticated/encrypted: {metadata}')
    if observed_ids is not None and set(observed_ids) != {rows[0][0]}:
        raise RuntimeError('SDK event and receiver durable message IDs do not match')
    return rows[0][0]


def verify_fanout_plan(recipients, plans, expected_out, observed_out):
    if (not isinstance(recipients, dict) or not recipients
            or any(not isinstance(recipient, str) or not recipient for recipient in recipients)
            or any(not isinstance(directory, (str, Path)) or not str(directory) for directory in recipients.values())
            or not isinstance(plans, dict) or set(plans) != set(expected_out)):
        raise RuntimeError('Explicit fanout recipients and per-token admission plans are required')
    for token, plan in plans.items():
        if (not isinstance(plan, dict) or set(plan) != set(recipients)
                or any(not isinstance(sender_id, str) or not sender_id for sender_id in plan.values())
                or not isinstance(observed_out[token], dict) or set(observed_out[token]) != set(recipients)):
            raise RuntimeError('Fanout recipient coverage differs from the complete explicit plan')


def verify_rch_records(root, destinations, expected_out, observed_in, *, deadline, outbound_recipients=None):
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
                    if outbound_recipients is not None:
                        daemon_out[token] = verify_fanout_admission(connection, record, token, outbound_recipients[token])
                        continue
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


def verify_fanout_admission(connection, record, token, expected):
    metadata = record['delivery_metadata']
    targets = metadata.get('reticulumd_receipt_targets', [])
    if (record.get('destination') is not None or record.get('delivery_mode') != 'fanout'
            or not record.get('topic_id') or record.get('delivery_state') != 'delivered'
            or record.get('delivery_method') != 'durable_broker' or metadata.get('acked') is not True
            or metadata.get('receipt_pending') is not False or metadata.get('dispatch_status') != 'accepted'
            or metadata.get('reticulumd_dispatch_count') != len(expected)
            or not isinstance(targets, list) or len(targets) != len(expected)
            or any(not isinstance(target, dict) or target.get('status') != 'delivered' for target in targets)
            or {target.get('destination'): target.get('message_id') for target in targets} != expected):
        raise RuntimeError('RCH fanout recipient receipts do not match complete admitted work')
    rows = connection.execute(
        'SELECT daemon_message_id, state, receipt_status, payload FROM rch_broker_dispatch WHERE message_id = ? LIMIT ?',
        [record['message_id'], len(expected) + 1]).fetchall()
    canonical = {}
    for daemon_id, state, status, payload in rows:
        try:
            intent = json.loads(payload)
            recipient = intent['request']['destination']
            if (intent['message']['message_id'] != record['message_id']
                    or intent['message']['content'] != content_for(token, False)
                    or intent['request']['content'] != content_for(token, False)):
                raise ValueError('dispatch payload belongs to different work')
        except (ValueError, TypeError, KeyError) as error:
            raise RuntimeError('RCH durable fanout admission payload differs from its business message') from error
        if recipient in canonical or state != 'terminal' or status != 'delivered':
            raise RuntimeError('RCH durable fanout admission is duplicated or lacks a terminal delivered receipt')
        canonical[recipient] = daemon_id
    if len(rows) != len(expected) or canonical != expected:
        raise RuntimeError('RCH durable fanout admission does not match the complete recipient plan')
    return canonical
