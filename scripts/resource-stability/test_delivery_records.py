"""Qualification must fail on durable corruption despite successful receiver counters."""
from contextlib import closing, contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

import msgpack
from delivery_records import content_for, verify_records


@contextmanager
def database(path):
    with closing(sqlite3.connect(path)) as connection, connection:
        yield connection


class DurableEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='rch-delivery-records-')
        self.root = Path(self.directory.name)
        self.destinations = ['rch-identity', 'peer-identity']
        self.expected_in, self.expected_out = {'test-in': 'sdk-in'}, {'test-out': 'rch-out'}
        self.observed_in, self.observed_out = {'test-in': {'rch-in'}}, {'test-out': {'wire-out'}}
        crypto = json.dumps({'_lxmf': {'signature_valid': True, 'transport_encrypted': True}})
        for index in [0, 1]:
            (self.root / f'node{index}').mkdir()
            with self.daemon(index) as connection:
                connection.execute('CREATE TABLE messages(id, source, destination, content, direction, receipt_status, fields)')
                token = 'test-in' if index == 0 else 'test-out'
                connection.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',
                                   ['wire-in' if index == 0 else 'wire-out', self.destinations[1-index],
                                    self.destinations[index], content_for(token, index == 0), 'in', None, crypto])
                token = 'test-out' if index == 0 else 'test-in'
                connection.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',
                                   ['rch-out' if index == 0 else 'sdk-in', self.destinations[index],
                                    self.destinations[1-index], content_for(token, index == 1), 'out', 'delivered', None])
        (self.root / 'rch').mkdir()
        with self.rch() as connection:
            connection.execute('CREATE TABLE rch_messages(message_id, payload)')
            for record in [
                {'message_id': 'rch-in', 'content': content_for('test-in', True), 'sender': self.destinations[1],
                 'delivery_state': 'received', 'delivery_metadata': {'source': self.destinations[1], 'direction': 'inbound', 'reticulumd_inbound': True}},
                {'message_id': 'rch-out', 'content': content_for('test-out', False), 'destination': self.destinations[1],
                 'delivery_state': 'delivered', 'delivery_metadata': {'acked': True, 'receipt_status': 'delivered',
                    'reticulumd_receipt_targets': [{'sdk_message_id': 'rch-out', 'destination': self.destinations[1],
                        'sdk_terminal': True, 'status': 'delivered'}]}},
            ]:
                connection.execute('INSERT INTO rch_messages VALUES(?,?)', [record['message_id'], msgpack.packb(record, use_bin_type=True)])

    def tearDown(self):
        self.directory.cleanup()

    def daemon(self, index):
        return database(self.root / f'node{index}' / 'daemon.sqlite3')

    def rch(self):
        return database(self.root / 'rch' / 'rch.sqlite3')

    def verify(self):
        return verify_records(self.root, self.destinations, self.expected_in, self.expected_out, self.observed_in, self.observed_out)

    def patch_rch(self, message_id, change):
        with self.rch() as connection:
            blob = connection.execute('SELECT payload FROM rch_messages WHERE message_id=?', [message_id]).fetchone()[0]
            record = msgpack.unpackb(blob, raw=False)
            change(record)
            connection.execute('UPDATE rch_messages SET payload=? WHERE message_id=?', [msgpack.packb(record, use_bin_type=True), message_id])

    def test_distinct_sender_rch_and_wire_identifiers_are_valid(self):
        self.assertEqual(self.verify(), {'test-in': 'wire-in', 'test-out': 'wire-out'})

    def test_expired_deadline_applies_to_durable_delivery_proof(self):
        with self.assertRaises(TimeoutError):
            verify_records(self.root, self.destinations, self.expected_in, self.expected_out,
                           self.observed_in, self.observed_out, deadline=time.monotonic() - 1)

    def test_duplicate_sender_ids_cannot_pass_on_receiver_counts(self):
        self.expected_out['test-out'] = 'sdk-in'
        with self.assertRaisesRegex(RuntimeError, 'not unique'):
            self.verify()

    def test_sender_failed_receipt_cannot_pass(self):
        with self.daemon(1) as connection:
            connection.execute("UPDATE messages SET receipt_status='failed' WHERE id='sdk-in'")
        with self.assertRaisesRegex(RuntimeError, 'Sender durable row'):
            self.verify()

    def test_receiver_prefix_match_cannot_hide_changed_content(self):
        with self.daemon(0) as connection:
            connection.execute("UPDATE messages SET content='test-in-corrupted' WHERE direction='in'")
        with self.assertRaisesRegex(RuntimeError, 'Receiver durable payload'):
            self.verify()

    def test_duplicate_receiver_payload_cannot_pass(self):
        with self.daemon(1) as connection:
            connection.execute("INSERT INTO messages SELECT 'duplicate',source,destination,content,direction,receipt_status,fields FROM messages WHERE id='wire-out'")
        with self.assertRaisesRegex(RuntimeError, 'Receiver durable payload'):
            self.verify()

    def test_unauthenticated_receiver_cannot_pass(self):
        with self.daemon(0) as connection:
            connection.execute("UPDATE messages SET fields=? WHERE direction='in'", [json.dumps({'_lxmf': {'signature_valid': False, 'transport_encrypted': True}})])
        with self.assertRaisesRegex(RuntimeError, 'not authenticated'):
            self.verify()

    def test_changed_rch_payload_cannot_pass(self):
        self.patch_rch('rch-in', lambda record: record.update(content='corrupted'))
        with self.assertRaisesRegex(RuntimeError, 'full content differs'):
            self.verify()

    def test_rch_delivered_state_without_matching_receipt_cannot_pass(self):
        self.patch_rch('rch-out', lambda record: record['delivery_metadata'].update(acked=False))
        with self.assertRaisesRegex(RuntimeError, 'outbound receipt'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
