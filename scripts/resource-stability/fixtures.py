"""Large valid history fixtures; never mutate a running service or existing history."""
from contextlib import closing
import json
import os
from pathlib import Path
import selectors
import sqlite3
import subprocess
import time

from linux_runtime import sha256, write_json


def generator_lines(process: subprocess.Popen, timeout: float):
    """Bound the whole stream, including silence and an unterminated partial line."""
    deadline = time.monotonic() + timeout
    pending = b''
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Fixture generator exceeded its whole-stream deadline')
            if not selector.select(remaining):
                continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                if pending:
                    yield pending.decode('utf-8')
                process.wait(timeout=max(0.001, deadline - time.monotonic()))
                return
            pending += chunk
            if len(pending) > 4 * 1048576:
                raise RuntimeError('Fixture generator line exceeds 4 MiB')
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                yield line.decode('utf-8')


def counts(path: Path) -> dict:
    with closing(sqlite3.connect(f'file:{path.resolve()}?mode=ro', uri=True)) as db:
        return {
            'payloads': db.execute('SELECT count(*) FROM propagation_entries').fetchone()[0],
            'payload_bytes': db.execute('SELECT coalesce(sum(size_bytes),0) FROM propagation_entries').fetchone()[0],
            'associations': db.execute('SELECT count(*) FROM propagation_peer_entries').fetchone()[0],
            'peers': db.execute('SELECT count(DISTINCT peer) FROM propagation_peer_entries').fetchone()[0],
            'states': dict(db.execute('SELECT state,count(*) FROM propagation_peer_entries GROUP BY state')),
        }


def seed_daemon(path: Path, generator: Path, payloads: int, peers: int, associations: int) -> dict:
    if not path.is_file():
        raise RuntimeError('Initialize an empty daemon database through reticulumd first')
    initial = counts(path)
    if initial['payloads'] or initial['associations']:
        raise RuntimeError('Refusing to overwrite an occupied propagation database')
    if not 1 <= peers <= associations or payloads < 1:
        raise ValueError('Invalid fixture cardinalities')
    now = int(time.time())
    ids = []
    stderr_path = path.with_suffix('.fixture-generator.log')
    with closing(sqlite3.connect(path)) as db, db, stderr_path.open('w') as stderr:
        generator_process = subprocess.Popen([str(generator.resolve()), str(payloads), '304'],
                                             stdout=subprocess.PIPE, stderr=stderr, text=True)
        try:
            for line in generator_lines(generator_process, timeout=600):
                row = json.loads(line)
                if row.get('signature_and_decryption_verified') is not True or row['stamp_cost'] != 0:
                    raise RuntimeError('Invalid wire generator provenance')
                ids.append(row['transient_id'])
                db.execute('INSERT INTO propagation_entries(transient_id,destination,payload_hex,received_at,size_bytes,stamp_value) VALUES (?,?,?,?,?,?)',
                           (row['transient_id'], row['destination'], row['payload_hex'], now,
                            row['size_bytes'], None, ))
            if generator_process.wait(timeout=30) != 0 or len(ids) != payloads:
                raise RuntimeError(f'Wire generator failed: {stderr_path}')
        finally:
            if generator_process.poll() is None:
                generator_process.kill()
                generator_process.wait(timeout=5)
            generator_process.stdout.close()
        # Completed history is intentionally skewed: one peer holds up to 27,542 IDs.
        completed = associations // 10
        first_completed = min(27_542, completed)
        remaining_completed = completed - first_completed
        pending = associations - completed
        for index in range(peers):
            peer = f'{index + 1:032x}'
            pending_count = pending // peers + int(index < pending % peers)
            completed_count = first_completed if index == 0 else (
                remaining_completed // max(1, peers - 1)
                + int(index - 1 < remaining_completed % max(1, peers - 1)))
            if peers == 1:
                completed_count = completed
            if pending_count > 1024 or pending_count + completed_count > payloads:
                raise RuntimeError('Fixture violates per-peer cap or available distinct payloads')
            for offset in range(pending_count + completed_count):
                transient_id = ids[(index * 1319 + offset) % payloads]
                state = 'received' if offset < completed_count else 'unhandled'
                db.execute('INSERT INTO propagation_peer_entries(peer,transient_id,state,updated_at) VALUES (?,?,?,?)',
                           (peer, transient_id, state, now))
        db.commit()
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    result = counts(path)
    if result['payloads'] != payloads or result['associations'] != associations or result['peers'] != peers:
        raise RuntimeError(f'Fixture cardinality mismatch: {result}')
    result.update(generator=str(generator.resolve()), generator_sha256=sha256(generator),
                  database_sha256=sha256(path), historical_stamp_cost=0,
                  limitation='History uses valid signed/encrypted LXMF at zero stamp cost; stamp mining CPU is not production-qualified.')
    write_json(path.with_suffix('.fixture.json'), result)
    return result
