"""Read-only SQLite evidence with one caller-owned proof deadline."""
from contextlib import contextmanager
import sqlite3
import time


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError('SQLite evidence qualification deadline exceeded')
    return seconds


class ProofConnection(sqlite3.Connection):
    deadline = None

    def execute(self, sql, parameters=()):
        if self.deadline is not None:
            # Each statement gets only the remaining whole-proof budget.
            milliseconds = int(min(5, remaining(self.deadline)) * 1000)
            super().execute(f'PRAGMA busy_timeout={milliseconds}')
        return super().execute(sql, parameters)


@contextmanager
def readonly(path, *, deadline=None):
    if deadline is not None:
        remaining(deadline)
    if not path.is_file():
        raise RuntimeError(f'Missing evidence database: {path}')
    connection = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True,
                                 timeout=5 if deadline is None else min(5, remaining(deadline)),
                                 factory=ProofConnection)
    try:
        connection.deadline = deadline
        if deadline is not None:
            connection.set_progress_handler(lambda: time.monotonic() >= deadline, 1000)
        yield connection
        if deadline is not None:
            remaining(deadline)
    except sqlite3.OperationalError as error:
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError('SQLite evidence qualification deadline exceeded') from error
        raise
    finally:
        connection.close()
