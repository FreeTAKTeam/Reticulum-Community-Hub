"""The generator deadline includes silent, partial-line and post-output stalls."""
import subprocess
import sys
import unittest

from fixtures import generator_lines


class GeneratorTests(unittest.TestCase):
    def run_generator(self, source, timeout):
        with subprocess.Popen([sys.executable, '-u', '-c', source], stdout=subprocess.PIPE) as process:
            try:
                return list(generator_lines(process, timeout))
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)

    def test_silent_generator_times_out(self):
        with self.assertRaisesRegex(TimeoutError, 'whole-stream'):
            self.run_generator('import time; time.sleep(60)', 0.1)

    def test_partial_line_times_out(self):
        with self.assertRaisesRegex(TimeoutError, 'whole-stream'):
            self.run_generator('import sys,time; sys.stdout.write("partial"); sys.stdout.flush(); time.sleep(60)', 0.1)

    def test_complete_line_followed_by_stall_times_out(self):
        with self.assertRaisesRegex(TimeoutError, 'whole-stream'):
            self.run_generator('import time; print("complete"); time.sleep(60)', 0.1)

    def test_lines_and_final_partial_are_preserved(self):
        self.assertEqual(self.run_generator('import sys; sys.stdout.write("first\\nsecond")', 3),
                         ['first', 'second'])


if __name__ == '__main__':
    unittest.main()
