"""Tests for Phase 4: Request budget and context compression."""

import json
import time
import unittest
from orchestrator.context_compressor import compress_tool_result
from orchestrator.core import RequestBudget


class TestRequestBudgetAndCompressor(unittest.TestCase):
    def test_request_budget_time_exceeded(self):
        budget = RequestBudget(time_budget_seconds=0.05)
        time.sleep(0.06)
        self.assertTrue(budget.is_exceeded())

    def test_request_budget_tokens_exceeded(self):
        budget = RequestBudget(max_tokens=100)
        self.assertFalse(budget.is_exceeded(current_tokens=50))
        self.assertTrue(budget.is_exceeded(current_tokens=150))

    def test_compress_tool_result_json(self):
        large_json = {
            "status": "success",
            "long_text": "a" * 1000,
            "items": list(range(20)),
        }
        res_str = compress_tool_result(large_json, max_str_len=100, max_list_items=6)
        parsed = json.loads(res_str)

        self.assertEqual(parsed["status"], "success")
        self.assertIn("truncated", parsed["long_text"])
        self.assertEqual(len(parsed["items"]), 7)  # 3 head + 1 placeholder + 3 tail
        self.assertEqual(parsed["items"][0], 0)
        self.assertEqual(parsed["items"][-1], 19)

    def test_compress_tool_result_text(self):
        raw_text = "b" * 2000
        res = compress_tool_result(raw_text, max_str_len=200)
        self.assertIn("truncated", res)
        self.assertTrue(res.startswith("b" * 200))
        self.assertTrue(res.endswith("b" * 200))


if __name__ == "__main__":
    unittest.main()
