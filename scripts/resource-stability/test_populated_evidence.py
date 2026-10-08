from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from delivery_preflight import finish_evidence, healthy_sample, main
from fixture_preservation import PopulatedFixture, verify_policy
from fixtures import counts
from linux_runtime import sha256
from maintenance_evidence import MaintenanceObserver


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'owned.log'
        self.path.write_text('')

    def line(self):
        return (datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                + ' propagation storage maintenance complete elapsed_ms=100 pruned_peer_entries=2\n')

    def test_stale_failed_and_partial_lines_cannot_pass(self):
        self.path.write_text(self.line())
        observer = MaintenanceObserver(self.path)
        self.assertEqual(observer.poll(), [])
        with self.path.open('a') as output:
            output.write('maintenance failed\n' + self.line().rstrip('\n'))
        self.assertEqual(observer.poll(), [])
        with self.assertRaisesRegex(RuntimeError, 'No successful'):
            observer.verify_post_cycle({}, {})
        with self.path.open('a') as output:
            output.write('\n')
        self.assertEqual(len(observer.poll()), 1)

    def test_requires_completion_before_cycle_and_fresh_admission_after_observation(self):
        observer = MaintenanceObserver(self.path)
        self.path.write_text(self.line())
        cycle = observer.poll()[0]
        before = cycle['began_monotonic_estimate_s'] - 1
        after = cycle['observed_monotonic_s'] + 1
        with self.assertRaisesRegex(RuntimeError, 'before maintenance'):
            observer.verify_post_cycle({'old': before}, {'old': after})
        with self.assertRaisesRegex(RuntimeError, 'after observing'):
            observer.verify_post_cycle({'old': before, 'late': before}, {'old': before, 'late': after})
        observer.verify_post_cycle({'old': before, 'late': after}, {'old': before, 'late': after + 1})

    def test_missing_timestamp_oversize_and_truncated_logs_fail(self):
        observer = MaintenanceObserver(self.path)
        self.path.write_text('propagation storage maintenance complete elapsed_ms=1 pruned_peer_entries=0\n')
        with self.assertRaisesRegex(RuntimeError, 'timestamp'):
            observer.poll()
        observer = MaintenanceObserver(self.path)
        self.path.write_text('')
        with self.assertRaisesRegex(RuntimeError, 'truncated'):
            observer.poll()
        observer = MaintenanceObserver(self.path)
        self.path.write_text('x' * 65_537)
        with self.assertRaisesRegex(RuntimeError, '64 KiB'):
            observer.poll()
        self.path.write_text('')
        observer = MaintenanceObserver(self.path)
        self.path.write_text('x' * 65_537 + '\n')
        with self.assertRaisesRegex(RuntimeError, '64 KiB'):
            observer.poll()

    def test_future_completion_timestamp_cannot_qualify_delivery_order(self):
        observer = MaintenanceObserver(self.path)
        self.path.write_text(self.line())
        with patch('maintenance_evidence.time.time', return_value=0):
            with self.assertRaisesRegex(RuntimeError, 'future'):
                observer.poll()

    def test_failed_cycle_or_worker_cannot_be_hidden_by_later_success(self):
        for failure in ['propagation storage maintenance failed: store unavailable',
                        'propagation storage maintenance worker failed: worker panic']:
            self.path.write_text('')
            observer = MaintenanceObserver(self.path)
            self.path.write_text(failure + '\n' + self.line())
            with self.assertRaisesRegex(RuntimeError, 'maintenance failed'):
                observer.poll()
            with self.assertRaisesRegex(RuntimeError, 'maintenance failed'):
                observer.poll()
            with self.assertRaisesRegex(RuntimeError, 'maintenance failed'):
                observer.verify_post_cycle({}, {})


class FinishEvidenceTests(unittest.TestCase):
    def test_cleanup_and_source_errors_invalidate_delivery_and_preserve_primary_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = []
            peer = Mock()
            peer.close.side_effect = lambda: events.append('peer')
            rch, daemon, fixture = Mock(), Mock(), Mock()
            def fail_shutdown():
                events.append('rch')
                raise RuntimeError('signal failed')
            def stop_daemon():
                events.append('daemon')
                return {'graceful': False}
            def changed_source():
                events.append('source')
                raise RuntimeError('changed original')
            rch.stop.side_effect = fail_shutdown
            daemon.stop.side_effect = stop_daemon
            fixture.recheck.side_effect = changed_source
            result = {'delivery_preflight_passed': True, 'passed_final_acceptance': False,
                      'shutdown': {}, 'errors': ['qualification deadline exceeded']}
            finish_evidence(root, result, peer, {'daemon': daemon, 'rch': rch}, fixture)
            self.assertEqual(events, ['peer', 'rch', 'daemon', 'source'])
            saved = json.loads((root / 'delivery-result.json').read_text())
            self.assertFalse(saved['delivery_preflight_passed'])
            self.assertEqual(saved['errors'], ['qualification deadline exceeded', 'rch shutdown: RuntimeError: signal failed',
                'daemon required forced shutdown', 'Source fixture changed: changed original'])

    def test_cleanup_failure_alone_invalidates_provisional_success(self):
        with tempfile.TemporaryDirectory() as directory:
            service = Mock()
            service.stop.side_effect = RuntimeError('cleanup-only failure')
            result = {'delivery_preflight_passed': True, 'shutdown': {}, 'errors': []}
            finish_evidence(Path(directory), result, None, {'owned': service}, None)
            self.assertFalse(result['delivery_preflight_passed'])
            self.assertEqual(result['errors'], ['owned shutdown: RuntimeError: cleanup-only failure'])

    def test_clean_shutdown_cannot_create_missing_delivery_success(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Mock()
            result = {'shutdown': {}, 'errors': []}
            finish_evidence(Path(directory), result, None, {}, fixture)
            self.assertFalse(result['delivery_preflight_passed'])
            self.assertTrue(result['immutable_source_verified_after_cleanup'])

    def test_interrupt_in_each_cleanup_owner_still_cleans_later_owners(self):
        with tempfile.TemporaryDirectory() as directory:
            peer, service, fixture = Mock(), Mock(), Mock()
            peer.close.side_effect = KeyboardInterrupt()
            service.stop.side_effect = SystemExit(2)
            result = {'delivery_preflight_passed': True, 'shutdown': {}, 'errors': []}
            finish_evidence(Path(directory), result, peer, {'owned': service}, fixture)
            service.stop.assert_called_once()
            fixture.recheck.assert_called_once()
            self.assertFalse(result['delivery_preflight_passed'])
            self.assertEqual(result['errors'], ['SDK shutdown: KeyboardInterrupt: ', 'owned shutdown: SystemExit: 2'])

    def test_nested_primary_and_forced_cleanup_reasons_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            peer = Mock()
            peer.close.side_effect = BaseExceptionGroup('shutdown', [KeyboardInterrupt('cancelled'), RuntimeError('reap failed')])
            result = {'delivery_preflight_passed': True, 'shutdown': {}, 'errors': []}
            finish_evidence(Path(directory), result, peer, {}, None)
            self.assertFalse(result['delivery_preflight_passed'])
            self.assertIn('cancelled', result['errors'][0])
            self.assertIn('reap failed', result['errors'][0])

    def test_oom_or_changed_process_identity_cannot_pass_sampling(self):
        service = Mock(start_ticks=123, pid=42)
        row = {'process_start_ticks': 123, 'cgroup': {'memory_events': {'oom': 0, 'oom_kill': 0}}}
        with patch('delivery_preflight.sample', return_value=row):
            healthy_sample(service)
            for key in ['oom', 'oom_kill', 'oom_group_kill']:
                row['cgroup']['memory_events'][key] = 1
                with self.assertRaisesRegex(RuntimeError, 'OOM'):
                    healthy_sample(service)
                row['cgroup']['memory_events'][key] = 0
            row['process_start_ticks'] = 999
            with self.assertRaisesRegex(RuntimeError, 'identity changed'):
                healthy_sample(service)


class PolicyTests(unittest.TestCase):
    def test_both_daemon_launches_use_the_manifest_cadence_without_disabling_ingress(self):
        with tempfile.TemporaryDirectory(prefix='rch-cadence-') as directory:
            output = Path(directory) / 'run'
            binary = Path(__file__).resolve()
            launches = []
            def service(role, executable, arguments, owned_directory, *remaining):
                if role == 'rch':
                    raise RuntimeError('test stops before RCH launch')
                launches.append(arguments)
                return Mock(manifest={'role': role}, stop=Mock(return_value={'graceful': True}))
            rpc = Mock()
            rpc.call.return_value = {'delivery_destination_hash': 'a' * 32}
            argv = ['delivery_preflight.py', '--server', str(binary), '--daemon', str(binary),
                    '--sdk-peer', str(binary), '--output', str(output)]
            with patch('sys.argv', argv), patch('delivery_preflight.Service', side_effect=service), \
                 patch('delivery_preflight.LocalRpc', return_value=rpc), \
                 patch('delivery_preflight.wait_ready'), \
                 patch('delivery_preflight.free_ports', return_value=list(range(7000, 7007))):
                self.assertEqual(main(), 1)
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['periodic_announce_interval_s'], 10)
            self.assertEqual(len(launches), 2)
            for index, arguments in enumerate(launches):
                interval = arguments[arguments.index('--announce-interval-secs') + 1]
                self.assertEqual(int(interval), manifest['periodic_announce_interval_s'])
                config = (output / f'node{index}' / 'reticulum.toml').read_text()
                self.assertNotIn('ingress_control', config)
            self.assertFalse(json.loads((output / 'delivery-result.json').read_text())['delivery_preflight_passed'])

    def test_wrong_effective_policy_or_static_peers_cannot_pass(self):
        peers = [f'{i:032x}' for i in range(512)]
        policy = {'enabled': True, 'propagation_node_enabled': True, 'target_cost': 0,
                  'message_storage_limit_mb': 256, 'peer_entry_limit': 1_000_000,
                  'peer_entry_limit_per_peer': 1024, 'peer_entry_ttl_secs': 604_800,
                  'completed_peer_entry_ttl_secs': 2_592_000, 'max_propagation_peers': 512,
                  'storage_maintenance_interval_secs': 300, 'static_peers': peers}
        verify_policy({'propagation': policy}, peers)
        for key in policy:
            wrong = {**policy, key: ['wrong'] * 512 if key == 'static_peers' else None}
            with self.assertRaises(RuntimeError):
                verify_policy({'propagation': wrong}, peers)


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'fixture').mkdir()
        self.daemon = self.root / 'fixture/daemon.sqlite3'
        self.rch = self.root / 'fixture/rch.sqlite3'
        with closing(sqlite3.connect(self.daemon)) as db, db:
            db.executescript('''CREATE TABLE propagation_entries(transient_id TEXT PRIMARY KEY,
                destination TEXT,payload_hex TEXT,size_bytes INTEGER,received_at INTEGER);
                CREATE TABLE propagation_peer_entries(peer TEXT,transient_id TEXT,state TEXT,updated_at INTEGER,
                PRIMARY KEY(peer,transient_id));''')
            for i in range(10):
                db.execute('INSERT INTO propagation_entries VALUES (?,?,?,?,?)', [str(i), 'dest', 'abcd', 2, int(time.time())])
                db.execute('INSERT INTO propagation_peer_entries VALUES (?,?,?,?)',
                           [str(i % 2), str(i), 'received' if i < 2 else 'unhandled', int(time.time())])
        with closing(sqlite3.connect(self.rch)) as db, db:
            db.executescript('''CREATE TABLE rch_messages(id INTEGER PRIMARY KEY,message_id TEXT,payload BLOB,created_ts_ms INTEGER);
                CREATE TABLE rch_identity_announces(destination_hash TEXT PRIMARY KEY,payload BLOB);''')
            db.execute("INSERT INTO rch_messages VALUES (1,'original',X'1234',100)")
            db.execute("INSERT INTO rch_identity_announces VALUES ('original',X'5678')")
        self.current_daemon = self.root / 'current-daemon.sqlite3'
        self.current_rch = self.root / 'current-rch.sqlite3'
        shutil.copy2(self.daemon, self.current_daemon)
        shutil.copy2(self.rch, self.current_rch)
        self.fixture = PopulatedFixture.__new__(PopulatedFixture)
        self.fixture.paths = {'daemon': self.daemon, 'rch': self.rch}
        self.fixture.hashes = {role: sha256(path) for role, path in self.fixture.paths.items()}
        self.fixture.before = counts(self.daemon)

    def mutate(self, path, sql):
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript(sql)

    def verify(self, pruned=0):
        return self.fixture.qualify(self.current_daemon, self.current_rch, pruned)

    def test_original_rows_and_logged_pending_prune_are_preserved(self):
        self.mutate(self.current_daemon, "DELETE FROM propagation_peer_entries WHERE transient_id='9'")
        with self.assertRaisesRegex(RuntimeError, 'reconcile'):
            self.verify()
        result = self.verify(1)
        self.assertEqual(result['original_associations_retained'], 9)
        self.assertEqual(result['original_pending_removed'], 1)
        self.assertTrue(result['original_payload_and_rch_rows_unchanged'])

    def test_expired_deadline_applies_to_original_fixture_proof(self):
        with self.assertRaises(TimeoutError):
            self.fixture.qualify(self.current_daemon, self.current_rch, 0, deadline=time.monotonic() - 1)

    def test_freshness_is_rechecked_after_setup_consumes_ttl_margin(self):
        fixture = self.fixture
        fixture.timestamp_ranges = {'peer_updated_at_s': {'unhandled': [0, 0], 'received': [0, 0]}}
        with patch('fixture_preservation.time.time', return_value=604_800 - 480 - 120 - 1):
            fixture.require_fresh(480)
        with patch('fixture_preservation.time.time', return_value=604_800 - 480 - 120):
            with self.assertRaisesRegex(RuntimeError, 'unhandled'):
                fixture.require_fresh(480)

    def test_new_payload_does_not_mask_lost_original(self):
        self.mutate(self.current_daemon, "DELETE FROM propagation_entries WHERE transient_id='1'; INSERT INTO propagation_entries VALUES ('new','dest','abcd',2,0)")
        with self.assertRaisesRegex(RuntimeError, 'original propagation_entries'):
            self.verify()

    def test_new_completed_mark_cannot_mask_original_loss(self):
        self.mutate(self.current_daemon, "DELETE FROM propagation_peer_entries WHERE transient_id='0'; INSERT INTO propagation_peer_entries VALUES ('new','new','received',0)")
        with self.assertRaisesRegex(RuntimeError, 'completed-mark'):
            self.verify(1)

    def test_surviving_pending_state_or_timestamp_cannot_change_silently(self):
        for sql in ["UPDATE propagation_peer_entries SET state='received' WHERE transient_id='9'",
                    "UPDATE propagation_peer_entries SET state='handled' WHERE transient_id='9'",
                    "UPDATE propagation_peer_entries SET updated_at=0 WHERE transient_id='9'"]:
            shutil.copy2(self.daemon, self.current_daemon)
            self.mutate(self.current_daemon, sql)
            with self.assertRaisesRegex(RuntimeError, 'surviving peer-history marks'):
                self.verify()

    def test_rch_payload_indexed_column_and_duplicate_corruption_fail(self):
        for sql in ["DELETE FROM rch_messages; INSERT INTO rch_messages VALUES (2,'new',X'1234',100)",
                    'UPDATE rch_messages SET created_ts_ms=999',
                    "UPDATE rch_identity_announces SET payload=X'ffff'",
                    "INSERT INTO rch_messages VALUES (2,'original',X'1234',100)"]:
            shutil.copy2(self.rch, self.current_rch)
            self.mutate(self.current_rch, sql)
            with self.assertRaises(RuntimeError):
                self.verify()

    def test_source_hash_wal_and_manifest_cardinality_fail_closed(self):
        self.fixture.recheck()
        wal = self.daemon.with_name(self.daemon.name + '-wal')
        wal.write_bytes(b'uncheckpointed')
        with self.assertRaisesRegex(RuntimeError, 'WAL'):
            self.fixture.recheck()
        wal.unlink()
        self.fixture.hashes['daemon'] = 'wrong'
        with self.assertRaisesRegex(RuntimeError, 'hash differs'):
            self.fixture.recheck()
        manifest = {'fixture': {**self.fixture.before, 'payloads': 999,
                                'database_sha256': sha256(self.daemon)},
                    'rch_fixture': {'database_sha256': sha256(self.rch)}}
        (self.root / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(RuntimeError, 'cardinality'):
            PopulatedFixture(self.root, 480)


if __name__ == '__main__':
    unittest.main()
