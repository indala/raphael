"""Tests for Phase 3: Local intent fast path."""

import unittest
from orchestrator.local_intents import try_match_intent, INTENT_MATCHERS


class TestLocalIntents(unittest.TestCase):
    def test_intent_matches(self):
        test_cases = [
            ("stop", "stop"),
            ("cancel", "stop"),
            ("mute", "mute"),
            ("mute mic", "mute"),
            ("unmute", "unmute"),
            ("volume up", "volume"),
            ("volume down", "volume"),
            ("take screenshot", "screenshot"),
            ("screenshot", "screenshot"),
            ("open settings", "settings"),
            ("settings", "settings"),
            ("hide window", "hide"),
            ("hide", "hide"),
            ("play music", "play/pause"),
            ("pause music", "play/pause"),
            ("what time is it", "time"),
            ("current time", "time"),
            ("open calculator", "calculator"),
            ("calc", "calculator"),
            ("open browser", "browser"),
            ("battery level", "battery"),
            ("battery status", "battery"),
            ("wifi status", "wifi"),
            ("check wifi", "wifi"),
        ]

        for text, expected_intent in test_cases:
            with self.subTest(text=text):
                res = try_match_intent(text)
                self.assertIsNotNone(res, f"Expected match for '{text}'")
                intent_name, output_text = res
                self.assertEqual(intent_name, expected_intent)
                self.assertIsInstance(output_text, str)

    def test_intent_no_false_positives(self):
        false_positive_cases = [
            "stop the shutdown of the server",
            "cancel my appointment tomorrow at 3pm",
            "volume is a measure of 3D space",
            "settings in the database configuration",
            "what is the time complexity of quicksort",
            "battery charging technology paper",
        ]

        for text in false_positive_cases:
            with self.subTest(text=text):
                res = try_match_intent(text)
                self.assertIsNone(res, f"Should NOT have matched '{text}'")


if __name__ == "__main__":
    unittest.main()
