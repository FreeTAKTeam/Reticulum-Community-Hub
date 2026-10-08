import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from service_discovery import discover


class ServiceDiscoveryTests(unittest.TestCase):
    def test_dropped_first_announce_retries_both_owners_and_requires_learned_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            peer, http, rpc0, rpc1 = Mock(), Mock(), Mock(), Mock()
            http.request.return_value = {'status': 'announce sent'}
            rpc0.call.return_value = {'announces': [{'peer': 'peer'}]}
            rpc1.call.side_effect = [{'announces': []}, {'announces': [{'peer': 'rch'}]}]
            with patch('service_discovery.time.sleep'):
                result = discover(peer, http, [rpc0, rpc1], ['rch', 'peer'], root)
            self.assertTrue(result['passed'])
            self.assertEqual([a['learned'] for a in result['attempts']], [[True, False], [True, True]])
            self.assertEqual(http.request.call_count, 2)
            self.assertEqual(peer.call.call_count, 2)
            deadline = http.request.call_args.kwargs['deadline']
            self.assertEqual(rpc0.call.call_args.kwargs['deadline'], deadline)
            self.assertEqual(rpc1.call.call_args.kwargs['deadline'], deadline)

    def test_expired_discovery_never_reports_learned_or_sends(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            peer, http = Mock(), Mock()
            with patch('service_discovery.time.monotonic', side_effect=[100, 131]):
                with self.assertRaises(TimeoutError):
                    discover(peer, http, [], ['rch', 'peer'], root)
            peer.call.assert_not_called()
            http.request.assert_not_called()
            self.assertFalse(json.loads((root / 'discovery.json').read_text())['passed'])

    def test_submission_acknowledgements_alone_cannot_pass_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            peer, http, rpc = Mock(), Mock(), Mock()
            http.request.return_value = {'status': 'announce sent'}
            rpc.call.return_value = {'announces': []}
            with patch('service_discovery.time.sleep'):
                with self.assertRaisesRegex(RuntimeError, 'bounded setup attempts'):
                    discover(peer, http, [rpc, rpc], ['rch', 'peer'], root)
            result = json.loads((root / 'discovery.json').read_text())
            self.assertFalse(result['passed'])
            self.assertEqual(len(result['attempts']), 32)

    def test_learned_identities_after_deadline_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            peer, http, rpc0, rpc1 = Mock(), Mock(), Mock(), Mock()
            http.request.return_value = {'status': 'announce sent'}
            rpc0.call.return_value = {'announces': [{'peer': 'peer'}]}
            rpc1.call.return_value = {'announces': [{'peer': 'rch'}]}
            with patch('service_discovery.time.monotonic', side_effect=[100, 101, 102, 103, 131]):
                with self.assertRaisesRegex(TimeoutError, 'discovery deadline'):
                    discover(peer, http, [rpc0, rpc1], ['rch', 'peer'], root)
            result = json.loads((root / 'discovery.json').read_text())
            self.assertFalse(result['passed'])
            self.assertEqual(result['attempts'][0]['learned'], [True, True])


if __name__ == '__main__':
    unittest.main()
