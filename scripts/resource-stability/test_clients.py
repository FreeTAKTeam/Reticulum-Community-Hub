"""Local TCP/Unix servers that trickle valid HTTP responses past inactivity limits."""
from contextlib import contextmanager
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from clients import Http, LocalRpc


@contextmanager
def response_server(chunks, *, unix=False):
    with tempfile.TemporaryDirectory(prefix='rch-client-') as directory:
        address = str(Path(directory) / 'rpc.sock') if unix else ('127.0.0.1', 0)
        listener = socket.socket(socket.AF_UNIX if unix else socket.AF_INET)
        listener.bind(address)
        listener.listen(1)
        listener.settimeout(1)
        stopped = threading.Event()
        errors = []

        def serve():
            try:
                with listener.accept()[0] as connection:
                    connection.settimeout(1)
                    request = bytearray()
                    while b'\r\n\r\n' not in request:
                        data = connection.recv(4096)
                        if not data or len(request) > 65_536:
                            raise RuntimeError('Invalid test request')
                        request.extend(data)
                    for chunk, delay in chunks:
                        if stopped.wait(delay):
                            break
                        connection.sendall(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Client deadline deliberately closes the owned connection.
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=serve)
        thread.start()
        try:
            yield Path(address) if unix else listener.getsockname()[1]
        finally:
            stopped.set()
            thread.join(2)
            listener.close()
            if thread.is_alive() or errors:
                raise RuntimeError(f'Test server did not exit cleanly: {errors}')


class ClientDeadlineTests(unittest.TestCase):
    def test_trickling_headers_have_whole_deadline(self):
        response = b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}'
        with response_server([(bytes([byte]), 0.01) for byte in response]) as port:
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                Http(port, timeout=0.06).request('/slow')
            self.assertLess(time.monotonic() - started, 1)

    def test_trickling_tcp_and_unix_bodies_have_whole_deadline(self):
        chunks = [(b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n', 0)]
        chunks += [(b'x', 0.01)] * 100
        for unix in [False, True]:
            with self.subTest(unix=unix), response_server(chunks, unix=unix) as endpoint:
                client = LocalRpc(endpoint, timeout=0.06) if unix else Http(endpoint, timeout=0.06)
                started = time.monotonic()
                with self.assertRaises(TimeoutError):
                    client.call('status') if unix else client.request('/slow')
                self.assertLess(time.monotonic() - started, 1)

    def test_caller_deadline_caps_client_timeout(self):
        chunks = [(b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n', 0), (b'{}', 1)]
        with response_server(chunks) as port:
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                Http(port, timeout=10).request('/slow', deadline=started + 0.05)
            self.assertLess(time.monotonic() - started, 1)

    def test_http_error_includes_bounded_server_detail(self):
        response = b'HTTP/1.1 422 Invalid\r\nContent-Length: 13\r\n\r\n{"bad": true}'
        with response_server([(response, 0)]) as port:
            with self.assertRaisesRegex(RuntimeError, 'HTTP 422.*bad'):
                Http(port).request('/invalid', {})


if __name__ == '__main__':
    unittest.main()
