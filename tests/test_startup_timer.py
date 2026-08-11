"""Tests for Phase 5: Startup Profiler."""

import time
import unittest
from orchestrator.startup_timer import StartupTimer


class TestStartupTimer(unittest.TestCase):
    def test_startup_timer_marks_and_report(self):
        timer = StartupTimer(start_now=True)
        time.sleep(0.01)
        timer.mark("config_load")
        time.sleep(0.01)
        timer.mark("ui_init")

        durations = timer.get_durations()
        self.assertEqual(len(durations), 2)
        self.assertEqual(durations[0][0], "config_load")
        self.assertEqual(durations[1][0], "ui_init")

        report = timer.report()
        self.assertIn("RAPHAEL STARTUP PROFILING", report)
        self.assertIn("config_load", report)
        self.assertIn("ui_init", report)
        self.assertIn("TOTAL STARTUP TIME", report)


if __name__ == "__main__":
    unittest.main()
