"""Ownership regression tests inject failures without launching any service."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from linux_runtime import Service


class CleanupTests(unittest.TestCase):
    def test_unknown_creation_outcome_still_cleans_exact_owned_unit(self):
        with patch('linux_runtime.command', side_effect=subprocess.TimeoutExpired('systemd-run', 20)), \
                patch.object(Service, 'force_stop') as cleanup:
            with self.assertRaises(subprocess.TimeoutExpired):
                Service('test', Path(sys.executable), [], Path('/tmp'), 512, 768, 1024, [0, 1], {})
            cleanup.assert_called_once()

    def test_failed_shutdown_signal_still_forces_cleanup(self):
        service = Service.__new__(Service)
        service.name = 'rch-resource-test-owned.service'
        service.running = lambda: True
        with patch('linux_runtime.command', side_effect=RuntimeError('injected signal failure')), \
                patch.object(service, 'force_stop') as cleanup:
            with self.assertRaisesRegex(RuntimeError, 'injected signal failure'):
                service.stop()
            cleanup.assert_called_once()

    def test_primary_and_cleanup_errors_are_both_retained(self):
        with patch('linux_runtime.command', side_effect=RuntimeError('creation failed')), \
                patch.object(Service, 'force_stop', side_effect=RuntimeError('cleanup failed')):
            with self.assertRaises(BaseExceptionGroup) as raised:
                Service('test', Path(sys.executable), [], Path('/tmp'), 512, 768, 1024, [0, 1], {})
            self.assertEqual([str(error) for error in raised.exception.exceptions],
                             ['creation failed', 'cleanup failed'])

    def test_clean_main_exit_with_stuck_child_is_forced(self):
        service = Service.__new__(Service)
        service.name = 'rch-resource-test-owned.service'
        with patch.object(service, 'running', side_effect=[True, False, False]), \
                patch.object(service, 'populated', return_value=True), \
                patch('linux_runtime.command', return_value='Result=success\nExecMainStatus=0\nExecMainCode=1'), \
                patch.object(service, 'force_stop') as cleanup:
            result = service.stop(timeout=0)
            self.assertFalse(result['graceful'])
            self.assertTrue(result['forced'])
            cleanup.assert_called_once()

    def test_populated_cgroup_is_not_reported_clean(self):
        service = Service.__new__(Service)
        service.name = 'rch-resource-test-owned.service'
        service.group = Path('/owned/group')
        with patch('linux_runtime.subprocess.run') as run, \
                patch.object(Path, 'exists', return_value=True), \
                patch('linux_runtime.numeric_fields', return_value={'populated': 1}), \
                patch('linux_runtime.time.monotonic', side_effect=[0, 6]):
            run.return_value.returncode = 0
            with self.assertRaisesRegex(RuntimeError, 'still populated'):
                service.force_stop()


if __name__ == '__main__':
    unittest.main()
