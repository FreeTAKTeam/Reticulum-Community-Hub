from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from evidence_db import readonly
from fixtures import counts


class ProofDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'proof.sqlite3'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE proof(value INTEGER)')
            db.execute('INSERT INTO proof VALUES(1)')

    def test_expired_proof_never_opens_or_creates_a_database(self):
        with self.assertRaises(TimeoutError):
            with readonly(self.path, deadline=time.monotonic() - 1):
                self.fail('Expired proof opened')
        with self.assertRaises(TimeoutError):
            counts(self.path, deadline=time.monotonic() - 1)

    def test_expensive_sql_is_interrupted_during_execution(self):
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            with readonly(self.path, deadline=started + 0.03) as db:
                db.execute('WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<1000000000) SELECT sum(x) FROM n').fetchone()
        self.assertLess(time.monotonic() - started, 1)

    def test_exclusive_lock_wait_is_bounded_by_remaining_proof_time(self):
        with closing(sqlite3.connect(self.path)) as writer:
            writer.execute('BEGIN EXCLUSIVE')
            started = time.monotonic()
            with self.assertRaises((TimeoutError, sqlite3.OperationalError)):
                with readonly(self.path, deadline=started + 0.03) as reader:
                    reader.execute('SELECT * FROM proof').fetchone()
            self.assertLess(time.monotonic() - started, 1)
            writer.rollback()

    def test_expiration_between_small_queries_cannot_return_success(self):
        with self.assertRaises(TimeoutError):
            with readonly(self.path, deadline=time.monotonic() + 0.02) as db:
                db.execute('SELECT * FROM proof').fetchone()
                time.sleep(0.03)
                db.execute('SELECT * FROM proof').fetchone()


if __name__ == '__main__':
    unittest.main()
