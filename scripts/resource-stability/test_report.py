"""Regression tests ensure a failed or inert workload cannot qualify as stable."""
import copy
import unittest

from report import evaluate


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        limit = {'max_slope_mib_per_minute': 0.1, 'max_growth_mib': 8,
                 'max_rss_plus_swap_mib': 512, 'max_fd_growth': 2, 'max_thread_growth': 1}
        self.criteria = {'duration_s': 360, 'warmup_s': 30, 'sample_interval_s': 30, 'traffic_window_s': 120, 'rch': limit, 'daemon': limit}
        self.samples = []
        for i in range(13):
            proc = {'rss_plus_swap_bytes': 100 * 1048576,
                    'private_plus_swap_bytes': 50 * 1048576, 'anonymous_plus_swap_bytes': 60 * 1048576, 'process_start_ticks': 1,
                    'fds': 10, 'status_kib': {'Threads': 2},
                    'cgroup': {'memory_events': {'oom': 0, 'oom_kill': 0, 'oom_group_kill': 0}}}
            self.samples.append({'elapsed_s': i * 30, 'rch': copy.deepcopy(proc),
                                 'daemon': copy.deepcopy(proc)})
        self.traffic = {'fixture_qualified': True, 'expected_messages': 10,
                        'verified_messages': 10, 'poll_progress': 50,
                        'poll_errors': 0, 'http_errors': 0,
                        'windows': [{'start_s': i*120, 'end_s': (i+1)*120,
                            'expected_messages': n, 'verified_messages': n,
                            'poll_progress': polls, 'poll_errors': 0, 'http_errors': 0}
                            for i, (n, polls) in enumerate([(3,15),(3,15),(4,20)])]}
        self.shutdown = {'rch': {'graceful': True}, 'daemon': {'graceful': True}}

    def result(self):
        return evaluate(self.samples, self.criteria, self.traffic, self.shutdown)

    def test_stable_active_complete_run(self):
        self.assertTrue(self.result()['passed'])

    def test_growing_swap_fails_even_if_rss_would_be_capped(self):
        for index, row in enumerate(self.samples):
            row['daemon']['rss_plus_swap_bytes'] += index * 4 * 1048576
        result = self.result()
        self.assertFalse(result['passed'])
        self.assertIn('daemon: growing memory-plus-swap trend', result['failures'])

    def test_each_operational_failure_rejects_plateau(self):
        for key, value in [('fixture_qualified', False), ('expected_messages', 0),
                           ('verified_messages', 9), ('poll_progress', 0),
                           ('poll_errors', 1), ('http_errors', 1)]:
            with self.subTest(key=key):
                previous = self.traffic[key]
                self.traffic[key] = value
                self.assertFalse(self.result()['passed'])
                self.traffic[key] = previous

    def test_restarts_oom_and_forced_shutdown_fail(self):
        for mutation in ('restart', 'oom', 'shutdown'):
            with self.subTest(mutation=mutation):
                samples, shutdown = copy.deepcopy(self.samples), copy.deepcopy(self.shutdown)
                if mutation == 'restart':
                    self.samples[-1]['daemon']['process_start_ticks'] += 1
                elif mutation == 'oom':
                    self.samples[-1]['daemon']['cgroup']['memory_events']['oom_kill'] = 1
                else:
                    self.shutdown['daemon']['graceful'] = False
                self.assertFalse(self.result()['passed'])
                self.samples, self.shutdown = samples, shutdown

    def test_incomplete_fields_and_missing_role_fail(self):
        for field in ('poll_errors', 'http_errors', 'windows'):
            with self.subTest(field=field):
                value = self.traffic.pop(field)
                self.assertFalse(self.result()['passed'])
                self.traffic[field] = value
        del self.shutdown['daemon']
        self.assertFalse(self.result()['passed'])

    def test_sampling_gap_and_warmup_restart_or_oom_fail(self):
        original = copy.deepcopy(self.samples)
        self.samples = self.samples[:2] + self.samples[8:]
        self.assertFalse(self.result()['passed'])
        self.samples = copy.deepcopy(original)
        self.samples[0]['daemon']['process_start_ticks'] += 1
        self.assertFalse(self.result()['passed'])
        self.samples = copy.deepcopy(original)
        self.samples[0]['daemon']['cgroup']['memory_events']['oom'] = 1
        self.assertFalse(self.result()['passed'])

    def test_private_growth_cannot_hide_behind_falling_file_residency(self):
        for index, row in enumerate(self.samples):
            row['daemon']['private_plus_swap_bytes'] += index * 1048576
        self.assertFalse(self.result()['passed'])

    def test_nonfinite_or_idle_intervals_fail(self):
        self.samples[4]['elapsed_s'] = float('nan')
        self.assertFalse(self.result()['passed'])
        self.samples[4]['elapsed_s'] = 120
        self.traffic['windows'][1]['poll_progress'] = 0
        self.assertFalse(self.result()['passed'])

    def test_short_or_empty_measurement_cannot_pass(self):
        self.samples.pop()
        self.assertFalse(self.result()['passed'])
        self.samples.clear()
        self.assertFalse(self.result()['passed'])


if __name__ == '__main__':
    unittest.main()
