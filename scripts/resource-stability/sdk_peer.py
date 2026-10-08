"""Owned public-SDK driver process; bounded lines, deadlines and exact correlation."""
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import time


class SdkPeer:
    def __init__(self, executable: Path, endpoint: str, response_endpoint: str, directory: Path, cpus: list[int]):
        self.pending = bytearray()
        self.errors = (directory / 'sdk-peer.log').open('wb')
        try:
            self.process = subprocess.Popen(['taskset', '-c', ','.join(map(str, cpus)), str(executable.resolve()), endpoint, response_endpoint],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors,
                                            start_new_session=True)
        except BaseException:
            self.errors.close()
            raise
        try:
            os.set_blocking(self.process.stdin.fileno(), False)
            ready = self.read(15)
            if ready.get('ready') is not True:
                raise RuntimeError(f'SDK peer did not become ready: {ready}')
            self.runtime_id = ready['runtime_id']
            self.destination = ready['destination']
        except BaseException as primary:
            try:
                self.close()
            except BaseException as cleanup:
                raise BaseExceptionGroup('SDK start and cleanup failed', [primary, cleanup])
            raise

    def read(self, timeout=10):
        deadline = time.monotonic() + timeout
        while b'\n' not in self.pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise TimeoutError('SDK driver response deadline, including partial lines')
            data = os.read(self.process.stdout.fileno(), 4096)
            if not data:
                raise RuntimeError(f'SDK driver exited: {self.process.poll()}; inspect sdk-peer.log')
            self.pending.extend(data)
            if len(self.pending) > 4 * 1024 * 1024:
                raise RuntimeError('SDK driver output exceeds 4 MiB')
        line, _, rest = self.pending.partition(b'\n')
        self.pending = bytearray(rest)
        return json.loads(line)

    def call(self, operation, token, *, timeout=10, **payload):
        data = json.dumps({'op': operation, 'token': token, **payload}).encode() + b'\n'
        if len(data) > 4 * 1024 * 1024:
            raise ValueError('SDK driver input exceeds 4 MiB')
        deadline = time.monotonic() + timeout
        pending = memoryview(data)
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [self.process.stdin], [], remaining)[1]:
                raise TimeoutError('SDK driver input deadline')
            count = os.write(self.process.stdin.fileno(), pending)
            if count == 0:
                raise RuntimeError('SDK driver input closed during write')
            pending = pending[count:]
        result = self.read(max(0, deadline - time.monotonic()))
        if result.get('token') != token:
            raise RuntimeError('SDK driver correlation mismatch')
        return result

    def close(self):
        forced = False
        try:
            self.process.stdin.close()
            try:
                code = self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                forced = True
                os.killpg(self.process.pid, signal.SIGKILL)
                code = self.process.wait(timeout=5)
            if forced or code != 0:
                raise RuntimeError(f'SDK driver failed shutdown: forced={forced}, exit={code}')
        except BaseException as primary:
            try:
                if self.process.poll() is None:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=5)
            except BaseException as cleanup:
                raise BaseExceptionGroup('SDK shutdown and forced cleanup failed', [primary, cleanup]) from None
            raise
        finally:
            self.process.stdout.close()
            self.errors.close()
