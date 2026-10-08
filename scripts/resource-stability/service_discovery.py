"""Retry real service announces in both directions under one setup deadline."""
import time
import uuid

from linux_runtime import write_json


def discover(peer, http, rpcs, destinations, root):
    started = time.monotonic()
    deadline = started + 30
    report = {'passed': False, 'deadline_s': 30, 'attempts': []}
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Whole real-announce discovery deadline exceeded')
            # A local submission can precede connectivity. Reannounce through
            # the real public owners; only a learned signed identity qualifies.
            announced = http.request('/Control/Announce', {}, deadline=deadline)
            if announced.get('status') != 'announce sent':
                raise RuntimeError('RCH did not acknowledge its service announce')
            peer.call('announce', uuid.uuid4().hex, timeout=min(10, deadline - time.monotonic()))
            learned = [any(record['peer'] == destinations[1 - index]
                           for record in rpc.call('list_announces', {'limit': 100}, deadline=deadline)['announces'])
                       for index, rpc in enumerate(rpcs)]
            if len(report['attempts']) >= 32:
                raise RuntimeError('Discovery evidence exceeds bounded setup attempts')
            report['attempts'].append({'elapsed_s': time.monotonic() - started, 'learned': learned})
            if time.monotonic() >= deadline:
                raise TimeoutError('Whole real-announce discovery deadline exceeded')
            if all(learned):
                report['passed'] = True
                return report
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    finally:
        write_json(root / 'discovery.json', report)
