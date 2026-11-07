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


class DeliveryFixture:
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
                                   ['daemon-out' if index == 0 else 'sdk-in', self.destinations[index],
                                    self.destinations[1-index], content_for(token, index == 1), 'out', 'delivered', None])
        (self.root / 'rch').mkdir()
        with self.rch() as connection:
            connection.execute('CREATE TABLE rch_messages(message_id, payload)')
            connection.execute('CREATE TABLE rch_broker_dispatch(message_id, daemon_message_id, state, receipt_status)')
            connection.execute("INSERT INTO rch_broker_dispatch VALUES('rch-out','daemon-out','terminal','delivered')")
            for record in [
                {'message_id': 'rch-in', 'content': content_for('test-in', True), 'sender': self.destinations[1],
                 'delivery_state': 'received', 'delivery_metadata': {'direction': 'inbound', 'reticulumd_inbound': True}},
                {'message_id': 'rch-out', 'content': content_for('test-out', False), 'destination': self.destinations[1],
                 'delivery_method': 'durable_broker', 'delivery_state': 'delivered',
                 'delivery_metadata': {'acked': True, 'last_broker_receipt': 'delivered',
                    'receipt_pending': False, 'dispatch_status': 'accepted', 'reticulumd_dispatch_count': 1,
                    'reticulumd_message_id': 'daemon-out',
                    'reticulumd_receipt_targets': [{'message_id': 'daemon-out', 'destination': self.destinations[1],
                        'status': 'delivered'}]}},
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


class DurableEvidenceTests(DeliveryFixture, unittest.TestCase):
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

    def test_conflicting_rch_receipt_and_daemon_identifiers_cannot_pass(self):
        self.patch_rch('rch-out', lambda record: record['delivery_metadata']['reticulumd_receipt_targets'][0].update(message_id='different'))
        with self.assertRaisesRegex(RuntimeError, 'outbound receipt'):
            self.verify()

    def test_late_nonterminal_diagnostic_cannot_replace_authoritative_terminal_receipt(self):
        # last_broker_receipt records the raw last input, including a late stale
        # receipt; dispatch state and target status own terminal completion.
        self.patch_rch('rch-out', lambda record: record['delivery_metadata'].update(last_broker_receipt='sent'))
        self.assertEqual(self.verify(), {'test-in': 'wire-in', 'test-out': 'wire-out'})

    def test_delivered_presentation_cannot_hide_missing_or_conflicting_admission(self):
        for sql in ["UPDATE rch_broker_dispatch SET daemon_message_id='different'",
                    "UPDATE rch_broker_dispatch SET state='admitted'",
                    "UPDATE rch_broker_dispatch SET receipt_status='failed'",
                    "INSERT INTO rch_broker_dispatch SELECT * FROM rch_broker_dispatch",
                    "DELETE FROM rch_broker_dispatch"]:
            with self.subTest(sql=sql):
                with self.rch() as connection:
                    connection.execute("DELETE FROM rch_broker_dispatch")
                    connection.execute("INSERT INTO rch_broker_dispatch VALUES('rch-out','daemon-out','terminal','delivered')")
                    connection.execute(sql)
                with self.assertRaisesRegex(RuntimeError, 'durable admission'):
                    self.verify()

    def test_daemon_sender_receipt_is_required_even_with_valid_rch_admission(self):
        with self.daemon(0) as connection:
            connection.execute("UPDATE messages SET receipt_status='sent' WHERE id='daemon-out'")
        with self.assertRaisesRegex(RuntimeError, 'Sender durable row'):
            self.verify()

    def test_missing_observed_token_cannot_pass_with_complete_database_rows(self):
        self.observed_in.clear()
        with self.assertRaisesRegex(RuntimeError, 'every admitted token'):
            self.verify()

    def test_extra_receiver_id_cannot_pass_with_one_valid_database_row(self):
        self.observed_out['test-out'].add('unexpected-wire-id')
        with self.assertRaisesRegex(RuntimeError, 'exactly one receiver message ID'):
            self.verify()


class FanoutEvidenceTests(DeliveryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.second = 'second-peer-identity'
        self.recipients = {self.destinations[1]: 'node1', self.second: 'node1'}
        self.plan = {'test-out': {self.destinations[1]: 'daemon-out', self.second: 'daemon-out-2'}}
        self.observed_out = {'test-out': {self.destinations[1]: {'wire-out'}, self.second: {'wire-out-2'}}}
        with self.daemon(0) as connection:
            connection.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',
                ['daemon-out-2', self.destinations[0], self.second, content_for('test-out', False), 'out', 'delivered', None])
        with self.daemon(1) as connection:
            connection.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',
                ['wire-out-2', self.destinations[0], self.second, content_for('test-out', False), 'in', None,
                 json.dumps({'_lxmf': {'signature_valid': True, 'transport_encrypted': True}})])
        self.patch_rch('rch-out', lambda record: record.update(destination=None, topic_id='fanout', delivery_mode='fanout'))
        self.patch_rch('rch-out', lambda record: record['delivery_metadata'].update(
            reticulumd_dispatch_count=2, reticulumd_receipt_targets=[
                {'destination': recipient, 'message_id': daemon_id, 'status': 'delivered'}
                for recipient, daemon_id in self.plan['test-out'].items()]))
        self.patch_rch('rch-out', lambda record: record['delivery_metadata'].pop('reticulumd_message_id'))
        with self.rch() as connection:
            connection.execute('ALTER TABLE rch_broker_dispatch ADD COLUMN payload')
            connection.execute('DELETE FROM rch_broker_dispatch')
            for recipient, daemon_id in self.plan['test-out'].items():
                intent = {'message': {'message_id': 'rch-out', 'content': content_for('test-out', False)},
                          'request': {'destination': recipient, 'content': content_for('test-out', False)}}
                connection.execute('INSERT INTO rch_broker_dispatch VALUES(?,?,?,?,?)',
                    ['rch-out', daemon_id, 'terminal', 'delivered', json.dumps(intent)])

    def verify(self):
        return verify_records(self.root, self.destinations, self.expected_in, self.expected_out,
            self.observed_in, self.observed_out, recipients=self.recipients, outbound_recipients=self.plan)

    def test_two_service_identities_on_one_daemon_require_independent_complete_delivery(self):
        self.assertEqual(self.verify(), {'test-in': 'wire-in', 'test-out': {
            self.destinations[1]: 'wire-out', self.second: 'wire-out-2'}})

    def test_recipient_options_are_explicit_and_required_together(self):
        for options in [{'recipients': self.recipients}, {'outbound_recipients': self.plan}]:
            with self.subTest(options=options), self.assertRaisesRegex(RuntimeError, 'recipients'):
                verify_records(self.root, self.destinations, self.expected_in, self.expected_out,
                    self.observed_in, self.observed_out, **options)

    def test_missing_extra_and_wrong_planned_recipients_cannot_pass(self):
        original = self.plan['test-out'].copy()
        for changed in [
                {self.destinations[1]: 'daemon-out'},
                {**original, 'unexpected': 'another-id'},
                {self.destinations[1]: 'daemon-out', 'wrong-recipient': 'daemon-out-2'}]:
            with self.subTest(changed=changed):
                self.plan['test-out'] = changed
                with self.assertRaisesRegex(RuntimeError, 'recipient coverage'):
                    self.verify()

    def test_missing_extra_and_wrong_observed_recipients_cannot_pass(self):
        original = self.observed_out['test-out'].copy()
        for changed in [
                {self.destinations[1]: {'wire-out'}},
                {**original, 'unexpected': {'another-wire-id'}},
                {self.destinations[1]: {'wire-out'}, 'wrong-recipient': {'wire-out-2'}}]:
            with self.subTest(changed=changed):
                self.observed_out['test-out'] = changed
                with self.assertRaisesRegex(RuntimeError, 'recipient coverage'):
                    self.verify()

    def test_missing_extra_and_wrong_receipt_targets_cannot_pass(self):
        targets = [{'destination': recipient, 'message_id': daemon_id, 'status': 'delivered'}
                   for recipient, daemon_id in self.plan['test-out'].items()]
        for changed in [targets[:1], targets + [{'destination': 'extra', 'message_id': 'extra', 'status': 'delivered'}],
                        [targets[0], {**targets[1], 'destination': 'wrong'}]]:
            with self.subTest(changed=changed):
                self.patch_rch('rch-out', lambda record: record['delivery_metadata'].update(reticulumd_receipt_targets=changed))
                with self.assertRaisesRegex(RuntimeError, 'recipient receipts'):
                    self.verify()

    def test_receipts_cannot_be_cross_attributed_between_recipients(self):
        self.patch_rch('rch-out', lambda record: record['delivery_metadata'].update(reticulumd_receipt_targets=[
            {'destination': self.destinations[1], 'message_id': 'daemon-out-2', 'status': 'delivered'},
            {'destination': self.second, 'message_id': 'daemon-out', 'status': 'delivered'}]))
        with self.assertRaisesRegex(RuntimeError, 'recipient receipts'):
            self.verify()

    def test_correlated_inputs_and_admissions_cannot_hide_actual_sender_destination_mismatch(self):
        self.plan['test-out'] = {self.destinations[1]: 'daemon-out-2', self.second: 'daemon-out'}
        self.patch_rch('rch-out', lambda record: record['delivery_metadata'].update(reticulumd_receipt_targets=[
            {'destination': recipient, 'message_id': daemon_id, 'status': 'delivered'}
            for recipient, daemon_id in self.plan['test-out'].items()]))
        with self.rch() as connection:
            connection.execute("UPDATE rch_broker_dispatch SET daemon_message_id=CASE daemon_message_id WHEN 'daemon-out' THEN 'daemon-out-2' ELSE 'daemon-out' END")
        with self.assertRaisesRegex(RuntimeError, 'Sender durable row'):
            self.verify()

    def test_valid_receipt_plan_cannot_hide_missing_extra_or_nonterminal_admission(self):
        with self.rch() as connection:
            original = connection.execute('SELECT * FROM rch_broker_dispatch').fetchall()
        for sql in ["DELETE FROM rch_broker_dispatch WHERE daemon_message_id='daemon-out-2'",
                    "INSERT INTO rch_broker_dispatch SELECT * FROM rch_broker_dispatch LIMIT 1",
                    "UPDATE rch_broker_dispatch SET state='admitted' WHERE daemon_message_id='daemon-out-2'",
                    "UPDATE rch_broker_dispatch SET receipt_status='failed' WHERE daemon_message_id='daemon-out-2'"]:
            with self.subTest(sql=sql):
                with self.rch() as connection:
                    connection.execute('DELETE FROM rch_broker_dispatch')
                    connection.executemany('INSERT INTO rch_broker_dispatch VALUES(?,?,?,?,?)', original)
                    connection.execute(sql)
                with self.assertRaisesRegex(RuntimeError, 'fanout admission'):
                    self.verify()

    def test_dispatch_payload_cannot_belong_to_another_business_message_recipient_or_content(self):
        with self.rch() as connection:
            payload = json.loads(connection.execute("SELECT payload FROM rch_broker_dispatch WHERE daemon_message_id='daemon-out-2'").fetchone()[0])
        for change in [lambda item: item['message'].update(message_id='other-business-id'),
                       lambda item: item['request'].update(destination='wrong-recipient'),
                       lambda item: item['request'].update(content='changed-content')]:
            with self.subTest(change=change):
                changed = json.loads(json.dumps(payload))
                change(changed)
                with self.rch() as connection:
                    connection.execute("UPDATE rch_broker_dispatch SET payload=? WHERE daemon_message_id='daemon-out-2'", [json.dumps(changed)])
                with self.assertRaisesRegex(RuntimeError, 'fanout admission'):
                    self.verify()

    def test_second_receiver_requires_its_own_authenticated_full_payload_and_event_id(self):
        with self.daemon(1) as connection:
            original = connection.execute("SELECT content, fields FROM messages WHERE id='wire-out-2'").fetchone()
        for sql, values, reason in [
                ("UPDATE messages SET content='changed' WHERE id='wire-out-2'", [], 'Receiver durable payload'),
                ("UPDATE messages SET fields=? WHERE id='wire-out-2'", [json.dumps({'_lxmf': {'signature_valid': False, 'transport_encrypted': True}})], 'not authenticated')]:
            with self.subTest(sql=sql):
                with self.daemon(1) as connection:
                    connection.execute("UPDATE messages SET content=?,fields=? WHERE id='wire-out-2'", original)
                    connection.execute(sql, values)
                with self.assertRaisesRegex(RuntimeError, reason):
                    self.verify()
        with self.daemon(1) as connection:
            connection.execute("UPDATE messages SET content=?,fields=? WHERE id='wire-out-2'", original)
        self.observed_out['test-out'][self.second] = {'wire-out'}
        with self.assertRaisesRegex(RuntimeError, 'receiver durable message IDs'):
            self.verify()

    def test_recipient_mapping_reads_each_actual_node_database(self):
        (self.root / 'node2').mkdir()
        with self.daemon(1) as source, self.daemon(2) as destination:
            source.backup(destination)
        with self.daemon(1) as connection:
            connection.execute("DELETE FROM messages WHERE id='wire-out-2'")
        self.recipients[self.second] = 'node2'
        self.assertEqual(self.verify()['test-out'][self.second], 'wire-out-2')

    def test_wrong_node_mapping_cannot_substitute_another_recipient_database(self):
        self.recipients[self.second] = 'node0'
        with self.assertRaisesRegex(RuntimeError, 'Receiver durable payload'):
            self.verify()

    def test_second_sender_requires_an_actual_delivered_receipt(self):
        with self.daemon(0) as connection:
            connection.execute("UPDATE messages SET receipt_status='sent' WHERE id='daemon-out-2'")
        with self.assertRaisesRegex(RuntimeError, 'Sender durable row'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
