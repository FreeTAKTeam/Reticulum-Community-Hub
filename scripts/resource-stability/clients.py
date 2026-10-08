"""Local-only bounded clients for the soak harness, not application transports."""
import http.client
import itertools
import json
from pathlib import Path
import socket
import struct
import urllib.request

import msgpack


class Http:
    def __init__(self, port: int, api_key: str = ''):
        self.base = f'http://127.0.0.1:{port}'
        self.api_key = api_key
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, path: str, payload=None):
        headers = {'X-API-Key': self.api_key}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        with self.opener.open(request, timeout=10) as response:
            return json.load(response)


class LocalRpc:
    def __init__(self, path: Path, timeout: float = 10):
        self.path = path
        self.timeout = timeout
        self.sequence = itertools.count(1)

    def call(self, method: str, params=None):
        request_id = next(self.sequence)
        data = msgpack.packb({'id': request_id, 'method': method, 'params': params}, use_bin_type=True)
        connection = http.client.HTTPConnection('localhost', timeout=self.timeout)
        try:
            connection.sock = socket.socket(socket.AF_UNIX)
            connection.sock.settimeout(self.timeout)
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
