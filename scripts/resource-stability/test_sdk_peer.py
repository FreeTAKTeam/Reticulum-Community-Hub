"""Failure-oriented checks for the owned SDK driver's pipe protocol."""
import json
import os
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from sdk_peer import SdkPeer


class DriverProtocolTests(unittest.TestCase):
    def setUp(self):
        output_read, output_write = os.pipe()
        input_read, input_write = os.pipe()
        self.files = [os.fdopen(fd, mode, buffering=0) for fd, mode in
                      [(output_read, 'rb'), (output_write, 'wb'),
                       (input_read, 'rb'), (input_write, 'wb')]]
        os.set_blocking(input_write, False)
        self.peer = SdkPeer.__new__(SdkPeer)
        self.peer.pending = bytearray()
        self.peer.process = SimpleNamespace(stdout=self.files[0], stdin=self.files[3], poll=lambda: 0)

    def tearDown(self):
        for stream in self.files:
            stream.close()

    def test_silent_and_partial_line_share_deadline(self):
        for partial in [b'', b'{"token":']:
            if partial:
                self.files[1].write(partial)
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                self.peer.read(0.03)
            self.assertLess(time.monotonic() - started, 1)

    def test_multiple_response_lines_are_preserved(self):
        self.files[1].write(b'{"a":1}\n{"a":2}\n')
        self.assertEqual(self.peer.read(0.1), {'a': 1})
        self.assertEqual(self.peer.read(0.1), {'a': 2})

    def test_wrong_correlation_fails(self):
        self.files[1].write(json.dumps({'token': 'wrong'}).encode() + b'\n')
        with self.assertRaisesRegex(RuntimeError, 'correlation mismatch'):
            self.peer.call('poll', 'expected', timeout=0.1)

    def test_eof_is_not_an_empty_success(self):
        self.files[1].close()
        with self.assertRaisesRegex(RuntimeError, 'driver exited'):
            self.peer.read(0.1)

    def test_oversize_input_is_rejected_before_writing(self):
        with self.assertRaisesRegex(ValueError, 'input exceeds'):
            self.peer.call('send', 'token', content='x' * (4 * 1024 * 1024))

    def test_oversize_partial_output_is_bounded(self):
        with tempfile.TemporaryFile() as stream:
            stream.write(b'x' * (4 * 1024 * 1024 + 1))
            stream.seek(0)
            self.peer.process.stdout = stream
            with self.assertRaisesRegex(RuntimeError, 'output exceeds'):
                self.peer.read(1)

    def test_stalled_input_cannot_block_indefinitely(self):
        started = time.monotonic()
        with self.assertRaisesRegex(TimeoutError, 'input deadline'):
            self.peer.call('send', 'token', timeout=0.03, content='x' * 100_000)
        self.assertLess(time.monotonic() - started, 1)

    def test_post_spawn_setup_failure_closes_and_reaps_child(self):
        with tempfile.TemporaryDirectory(prefix='rch-sdk-failure-') as directory:
            child = SimpleNamespace(stdin=self.files[3], stdout=self.files[0], wait=Mock(return_value=0))
            with patch('sdk_peer.subprocess.Popen', return_value=child) as spawn, patch('sdk_peer.os.set_blocking', side_effect=OSError('setup failed')):
                with self.assertRaisesRegex(OSError, 'setup failed'):
                    SdkPeer(Path('/unused'), 'tcp://127.0.0.1:1', 'tcp://127.0.0.1:2', Path(directory), [0, 1])
            self.assertTrue(child.stdin.closed)
            self.assertTrue(child.stdout.closed)
            child.wait.assert_called_once_with(timeout=10)
            self.assertTrue(spawn.call_args.kwargs['stderr'].closed)

    def test_interrupted_shutdown_kills_and_reaps_the_owned_child(self):
        peer = SdkPeer.__new__(SdkPeer)
        peer.process = Mock(pid=123)
        peer.process.poll.return_value = None
        peer.process.wait.side_effect = [KeyboardInterrupt(), 0]
        peer.errors = Mock()
        with patch('sdk_peer.os.killpg') as kill:
            with self.assertRaises(KeyboardInterrupt):
                peer.close()
        kill.assert_called_once_with(123, 9)
        self.assertEqual(peer.process.wait.call_count, 2)
        peer.process.stdout.close.assert_called_once()
        peer.errors.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
