"""Read-only, indexed comparison of original fixture rows; never load row sets."""
import json
import math
from pathlib import Path
import time

from fixtures import counts
from linux_runtime import sha256
from evidence_db import readonly


def verify_policy(response, peers):
    policy = response['propagation']
    expected = {'enabled': True, 'propagation_node_enabled': True, 'target_cost': 0,
                'message_storage_limit_mb': 256, 'peer_entry_limit': 1_000_000,
                'peer_entry_limit_per_peer': 1024, 'peer_entry_ttl_secs': 604_800,
                'completed_peer_entry_ttl_secs': 2_592_000, 'max_propagation_peers': 512,
                'storage_maintenance_interval_secs': 300}
    for key, value in expected.items():
        if policy.get(key) != value:
            raise RuntimeError(f'Effective propagation policy differs: {key}: {policy.get(key)} != {value}')
    if len(policy.get('static_peers', [])) != 512 or set(policy['static_peers']) != set(peers):
        raise RuntimeError('Effective static peers differ from the 512 frozen fixture keys')


def ident(name):
    return '"' + name.replace('"', '""') + '"'


def unchanged_rows(connection, table, key):
    columns = [row[1] for row in connection.execute(f'PRAGMA original.table_info({ident(table)})')]
    actual = [row[1] for row in connection.execute(f'PRAGMA main.table_info({ident(table)})')]
    if not columns or columns != actual:
        raise RuntimeError(f'Fixture schema differs: {table}')
    equal_key = ' AND '.join(f'f.{ident(k)}=m.{ident(k)}' for k in key)
    changed = ' OR '.join(f'f.{ident(c)} IS NOT m.{ident(c)}' for c in columns)
    missing = connection.execute(f'SELECT COUNT(*) FROM original.{ident(table)} f '
                                 f'LEFT JOIN main.{ident(table)} m ON {equal_key} '
                                 f'WHERE m.{ident(key[0])} IS NULL OR {changed}').fetchone()[0]
    if missing:
        raise RuntimeError(f'{missing} original {table} rows missing or changed')


class PopulatedFixture:
    def __init__(self, root: Path, horizon_s):
        self.root = root.resolve()
        manifest = json.loads((self.root / 'manifest.json').read_text())
        self.paths = {role: self.root / 'fixture' / name for role, name in
                      [('daemon', 'daemon.sqlite3'), ('rch', 'rch.sqlite3')]}
        self.hashes = {'daemon': manifest['fixture']['database_sha256'],
                       'rch': manifest['rch_fixture']['database_sha256']}
        self.recheck()
        self.before = counts(self.paths['daemon'])
        for key in ['payloads', 'payload_bytes', 'associations', 'peers', 'states']:
            if self.before[key] != manifest['fixture'][key]:
                raise RuntimeError(f'Fixture cardinality does not match manifest: {key}')
        if (self.before['payloads'] < 135_893 or self.before['associations'] < 1_000_000
                or self.before['peers'] < 940 or self.before['states'].get('received', 0) < 100_000):
            raise RuntimeError('Populated fixture is smaller than the frozen large workload')
        with readonly(self.paths['daemon']) as db:
            self.peers = [row[0] for row in db.execute(
                'SELECT DISTINCT peer FROM propagation_peer_entries ORDER BY peer LIMIT 512')]
            ranges = {state: db.execute('SELECT MIN(updated_at),MAX(updated_at) FROM propagation_peer_entries WHERE state=?',
                                        [state]).fetchone() for state in ['unhandled', 'received']}
            self.timestamp_ranges = {'peer_updated_at_s': ranges,
                                     'payload_received_at_s': db.execute('SELECT MIN(received_at),MAX(received_at) FROM propagation_entries').fetchone()}
        self.require_fresh(horizon_s)
        with readonly(self.paths['rch']) as db:
            self.rch_counts = {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                               for table in ['rch_messages', 'rch_identity_announces']}
            self.timestamp_ranges['rch_created_ts_ms'] = db.execute('SELECT MIN(created_ts_ms),MAX(created_ts_ms) FROM rch_messages').fetchone()
        if (self.rch_counts['rch_messages'] != manifest['rch_fixture']['messages']
                or self.rch_counts['rch_identity_announces'] != manifest['rch_fixture']['announces']
                or self.rch_counts['rch_messages'] < 25_000 or self.rch_counts['rch_identity_announces'] < 100_000):
            raise RuntimeError('RCH fixture cardinality is wrong or below the frozen workload')
        self.metadata = {'source': str(self.root), 'manifest_sha256': sha256(self.root / 'manifest.json'),
                         'database_sha256': self.hashes, 'daemon': self.before,
                         'rch': self.rch_counts, 'timestamp_ranges': self.timestamp_ranges}

    def recheck(self):
        for role, path in self.paths.items():
            wal = path.with_name(path.name + '-wal')
            if wal.exists() and wal.stat().st_size:
                raise RuntimeError(f'Uncheckpointed source fixture WAL: {wal}')
            if sha256(path) != self.hashes[role]:
                raise RuntimeError(f'Immutable source fixture hash differs: {role}')

    def require_fresh(self, horizon_s):
        now = time.time()
        ranges = self.timestamp_ranges['peer_updated_at_s']
        for state, ttl in [('unhandled', 604_800), ('received', 2_592_000)]:
            if ranges[state][0] is None or ranges[state][0] + ttl <= now + horizon_s + 120:
                raise RuntimeError(f'Stale workload: {state} fixture TTL expires during this lane')

    def qualify(self, daemon_path, rch_path, pruned, *, deadline=None):
        with readonly(daemon_path, deadline=deadline) as db:
            db.execute('ATTACH DATABASE ? AS original', [f'{self.paths["daemon"].as_uri()}?mode=ro'])
            unchanged_rows(db, 'propagation_entries', ['transient_id'])
            join = 'f.peer=m.peer AND f.transient_id=m.transient_id'
            retained, histories = db.execute('SELECT COUNT(*),COUNT(DISTINCT f.peer) '
                f'FROM original.propagation_peer_entries f JOIN main.propagation_peer_entries m ON {join}').fetchone()
            changed_marks = db.execute('SELECT COUNT(*) FROM original.propagation_peer_entries f '
                f'JOIN main.propagation_peer_entries m ON {join} '
                'WHERE f.state IS NOT m.state OR f.updated_at IS NOT m.updated_at').fetchone()[0]
            lost_completed = db.execute('SELECT COUNT(*) FROM original.propagation_peer_entries f '
                f'LEFT JOIN main.propagation_peer_entries m ON {join} '
                "WHERE f.state='received' AND (m.state IS NULL OR m.state<>'received')").fetchone()[0]
            removed_pending = db.execute('SELECT COUNT(*) FROM original.propagation_peer_entries f '
                f'LEFT JOIN main.propagation_peer_entries m ON {join} '
                "WHERE f.state='unhandled' AND m.peer IS NULL").fetchone()[0]
        if changed_marks:
            raise RuntimeError('Original surviving peer-history marks changed')
        if lost_completed or retained < math.ceil(self.before['associations'] * 0.9) or histories < self.before['peers']:
            raise RuntimeError('Original association, completed-mark or peer-history retention failed')
        if removed_pending > pruned or retained + removed_pending != self.before['associations']:
            raise RuntimeError('Original association removals do not reconcile with observed pruning')
        with readonly(rch_path, deadline=deadline) as db:
            db.execute('ATTACH DATABASE ? AS original', [f'{self.paths["rch"].as_uri()}?mode=ro'])
            for table, key in [('rch_messages', ['id']), ('rch_identity_announces', ['destination_hash'])]:
                unchanged_rows(db, table, key)
            duplicates = db.execute('SELECT COUNT(*) FROM main.rch_messages m '
                'JOIN original.rch_messages f ON m.message_id=f.message_id WHERE m.id<>f.id').fetchone()[0]
            if duplicates:
                raise RuntimeError('New rows duplicate original RCH message IDs')
        after = counts(daemon_path, deadline=deadline)
        return {'after': after, 'original_associations_retained': retained,
                'original_histories_retained': histories, 'original_completed_marks_lost': lost_completed,
                'original_surviving_marks_changed': changed_marks,
                'original_pending_removed': removed_pending, 'observed_pruned': pruned,
                'added_associations_still_present': after['associations'] - retained,
                'original_payload_and_rch_rows_unchanged': True}
