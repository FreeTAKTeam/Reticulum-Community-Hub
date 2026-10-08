"""Local-only bounded clients for the soak harness, not application transports."""
import http.client
import itertools
import json
from pathlib import Path
import socket
import struct
import time

import msgpack


class DeadlineSocket(socket.socket):
    """HTTP's SocketIO calls recv_into for each read; keep one whole-call deadline."""
    def __init__(self, family, deadline):
        super().__init__(family)
        self.deadline = deadline

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Local HTTP whole-response deadline')
        self.settimeout(remaining)

    def connect(self, address):
        self.remaining()
        return super().connect(address)

    def sendall(self, data, flags=0):
        self.remaining()
        return super().sendall(data, flags)

    def recv_into(self, buffer, nbytes=0, flags=0):
        self.remaining()
        return super().recv_into(buffer, nbytes, flags)


class Http:
    def __init__(self, port: int, api_key: str = '', timeout: float = 10):
        self.base = f'http://127.0.0.1:{port}'
        self.port = port
        self.api_key = api_key
        self.timeout = timeout

    def request(self, path: str, payload=None, *, deadline=None):
        headers = {'X-API-Key': self.api_key}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=self.timeout)
        try:
            connection.sock = DeadlineSocket(socket.AF_INET, min(time.monotonic() + self.timeout, deadline if deadline is not None else float('inf')))
            connection.sock.connect(('127.0.0.1', self.port))
            connection.request('POST' if payload is not None else 'GET', path, data, headers)
            response = connection.getresponse()
            limit = 64 * 1024 * 1024 if response.status == 200 else 65_536
            body = response.read(limit + 1)
            if len(body) > limit:
                raise RuntimeError(f'HTTP response exceeds {limit} bytes at {path}')
            if response.status != 200:
                raise RuntimeError(f'HTTP {response.status} at {path}: {body.decode("utf-8", errors="replace")}')
            return json.loads(body)
        finally:
            connection.close()


class LocalRpc:
    def __init__(self, path: Path, timeout: float = 10):
        self.path = path
        self.timeout = timeout
        self.sequence = itertools.count(1)

    def call(self, method: str, params=None, *, deadline=None):
        request_id = next(self.sequence)
        data = msgpack.packb({'id': request_id, 'method': method, 'params': params}, use_bin_type=True)
        connection = http.client.HTTPConnection('localhost', timeout=self.timeout)
        try:
            connection.sock = DeadlineSocket(socket.AF_UNIX, min(time.monotonic() + self.timeout, deadline if deadline is not None else float('inf')))
            connection.sock.connect(str(self.path))
            connection.request('POST', '/rpc', struct.pack('>I', len(data)) + data,
                               {'Content-Type': 'application/msgpack'})
            response = connection.getresponse()
            body = response.read(16 * 1024 * 1024 + 5)
            if response.status != 200:
                raise RuntimeError(f'{method}: HTTP {response.status}: {body[:200]!r}')
            if len(body) < 4:
                raise RuntimeError('Incomplete RPC response header')
            length = struct.unpack('>I', body[:4])[0]
            if length > 16 * 1024 * 1024 or len(body) != length + 4:
                raise RuntimeError('Incomplete or oversized RPC reply')
            value = msgpack.unpackb(body[4:], raw=False, strict_map_key=False)
        finally:
            connection.close()
        if isinstance(value, list):
            value = dict(zip(('id', 'result', 'error'), value))
        if value.get('id') != request_id:
            raise RuntimeError('RPC correlation mismatch')
        if value.get('error'):
            raise RuntimeError(f'{method}: {value["error"]}')
        return value['result']


def free_ports(count: int) -> list[int]:
    # Hold all reservations together so ports in the same run cannot repeat.
    sockets = []
    try:
        for _ in range(count):
            sock = socket.socket()
            sock.bind(('127.0.0.1', 0))
            sockets.append(sock)
        return [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()
