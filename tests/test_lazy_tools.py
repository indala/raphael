"""Tests for Phase 2: Lazy tool imports + schema caching."""

import os
import unittest
from unittest.mock import patch

from orchestrator.tools import (
    get_filtered_schemas,
    get_tool_map,
    invalidate_tool_cache,
)


class TestLazyToolsAndSchemaCache(unittest.TestCase):
    def setUp(self):
        invalidate_tool_cache()

    def tearDown(self):
        invalidate_tool_cache()

    def test_lazy_tool_map_matches_eager(self):
        """Verify lazy path returns exact same tool keys as eager path."""
        # 1. Fetch lazy tool map
        lazy_map = get_tool_map()
        lazy_keys = set(lazy_map.keys())

        # 2. Reset and fetch with RAPHAEL_EAGER_TOOLS=1
        invalidate_tool_cache()
        with patch.dict(os.environ, {"RAPHAEL_EAGER_TOOLS": "1"}):
            eager_map = get_tool_map()
            eager_keys = set(eager_map.keys())

        self.assertEqual(lazy_keys, eager_keys)

    def test_get_filtered_schemas_caching(self):
        """Test cache hits and misses for get_filtered_schemas."""
        tool_names = ["web_search", "read_file"]

        # Initial call computes and caches
        schemas1 = get_filtered_schemas(tool_names)
        self.assertIsInstance(schemas1, list)

        # Second call with same names (different order) should hit cache
        schemas2 = get_filtered_schemas(["read_file", "web_search"])
        self.assertEqual(schemas1, schemas2)

        # Invalidate clears cache
        invalidate_tool_cache()
        from orchestrator.tools import _filtered_schema_cache
        self.assertEqual(len(_filtered_schema_cache), 0)

    def test_invalidate_tool_cache(self):
        """Verify invalidate_tool_cache resets state."""
        get_tool_map()
        from orchestrator.tools import _TOOL_MAP, _tools_initialized
        self.assertTrue(_tools_initialized)
        self.assertGreater(len(_TOOL_MAP), 0)

        invalidate_tool_cache()
        from orchestrator.tools import _TOOL_MAP as tm, _tools_initialized as ti
        self.assertFalse(ti)
        self.assertEqual(len(tm), 0)


if __name__ == "__main__":
    unittest.main()
