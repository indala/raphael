"""
Tests for tools_meta/marketplace.py and tools_meta/remote_marketplace.py

Coverage:
- Dependency auto-detection from import statements
- Tool export/import with enhanced metadata
- Ratings and reviews system
- Local marketplace listing
- Remote marketplace discovery (mocked)
- Caching and offline support
"""

import json
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from tools_meta import marketplace
from tools_meta import remote_marketplace


# ── Test Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def tmp_storage():
    """Temporary directory for storage files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(autouse=True)
def clean_reviews(tmp_storage):
    """Clean up reviews before and after each test."""
    # Mock the reviews file location
    original_file = marketplace._REVIEWS_FILE
    marketplace._REVIEWS_FILE = tmp_storage / "reviews.json"
    yield
    marketplace._REVIEWS_FILE = original_file


# ── Tests: Dependency Detection ────────────────────────────────────────────

class TestDependencyDetection:
    """Test _extract_dependencies() for auto-detection."""

    def test_extract_simple_import(self):
        """Extract tool dependency from 'from tools.X import Y'."""
        code = """
from tools.http_tool import fetch
from tools.json_tool import parse

def my_function():
    result = fetch("https://example.com")
    data = parse(result)
    return data
"""
        deps = marketplace._extract_dependencies(code)
        assert "http_tool" in deps
        assert "json_tool" in deps

    def test_extract_import_statement(self):
        """Extract tool dependency from 'import tools.X'."""
        code = """
import tools.file_tool
import tools.datetime_tool as dt

def process():
    return tools.file_tool.read('data.txt')
"""
        deps = marketplace._extract_dependencies(code)
        assert "file_tool" in deps
        assert "datetime_tool" in deps

    def test_no_duplicate_dependencies(self):
        """Avoid duplicate dependencies."""
        code = """
from tools.http_tool import fetch
from tools.http_tool import post
import tools.http_tool
"""
        deps = marketplace._extract_dependencies(code)
        assert deps.count("http_tool") == 1

    def test_empty_code(self):
        """Handle empty code."""
        deps = marketplace._extract_dependencies("")
        assert deps == []

    def test_no_tool_imports(self):
        """Return empty list when no tool imports."""
        code = """
import json
from datetime import datetime
import requests
"""
        deps = marketplace._extract_dependencies(code)
        assert deps == []

    def test_mixed_imports(self):
        """Extract only tool imports from mixed code."""
        code = """
import json
from tools.http_tool import fetch
import requests
from tools.parser import parse_html
import os
"""
        deps = marketplace._extract_dependencies(code)
        assert len(deps) == 2
        assert "http_tool" in deps
        assert "parser" in deps


# ── Tests: Ratings & Reviews ───────────────────────────────────────────────

class TestRatingsSystem:
    """Test rate_skill() and get_skill_ratings()."""

    def test_rate_skill_valid(self):
        """Rate a skill with valid rating."""
        msg = marketplace.rate_skill("weather_tool", rating=5)
        assert "Rated" in msg
        assert "5/5" in msg

    def test_rate_skill_with_review_text(self):
        """Rate with optional review text."""
        msg = marketplace.rate_skill(
            "weather_tool",
            rating=4,
            review="Great tool, very reliable!"
        )
        assert "4/5" in msg

    def test_rate_skill_invalid_rating_low(self):
        """Reject rating below 1."""
        msg = marketplace.rate_skill("tool", rating=0)
        assert "must be between 1 and 5" in msg.lower()

    def test_rate_skill_invalid_rating_high(self):
        """Reject rating above 5."""
        msg = marketplace.rate_skill("tool", rating=6)
        assert "must be between 1 and 5" in msg.lower()

    def test_get_skill_ratings_not_found(self):
        """Return None for skill with no ratings."""
        result = marketplace.get_skill_ratings("nonexistent_tool")
        assert result is None

    def test_get_skill_ratings_after_rating(self):
        """Get ratings after rating a skill."""
        marketplace.rate_skill("test_tool", rating=5)
        marketplace.rate_skill("test_tool", rating=4)
        marketplace.rate_skill("test_tool", rating=5)
        
        ratings = marketplace.get_skill_ratings("test_tool")
        assert ratings is not None
        assert ratings["review_count"] == 3
        assert ratings["rating"] == pytest.approx(4.667, rel=0.01)  # (5+4+5)/3

    def test_rating_average_calculation(self):
        """Verify rating average is calculated correctly."""
        for rating in [1, 2, 3, 4, 5]:
            marketplace.rate_skill("avg_test", rating=rating)
        
        ratings = marketplace.get_skill_ratings("avg_test")
        assert ratings["rating"] == 3.0  # (1+2+3+4+5)/5
        assert ratings["review_count"] == 5

    def test_rating_persistence(self):
        """Ratings persist across calls."""
        marketplace.rate_skill("persist_test", rating=5)
        
        # Load reviews fresh
        reviews = marketplace._load_reviews()
        assert "persist_test" in reviews
        assert reviews["persist_test"]["review_count"] == 1


# ── Tests: Export/Import ───────────────────────────────────────────────────

class TestExportImport:
    """Test export_tool() and import_tool()."""

    @patch("tools_meta.marketplace._TOOLS_PROD")
    @patch("tools_meta.marketplace._TESTS_DIR")
    @patch("tools_meta.marketplace._registry_tools")
    def test_export_tool_not_found(self, mock_registry, mock_tests, mock_prod):
        """Reject export of non-existent tool."""
        nonexistent = MagicMock()
        nonexistent.exists.return_value = False
        mock_prod.__truediv__.return_value = nonexistent
        
        result = marketplace.export_tool("nonexistent")
        assert "not found" in result.lower()

    @patch("tools_meta.marketplace._extract_dependencies")
    @patch("tools_meta.marketplace._TOOLS_PROD")
    @patch("tools_meta.marketplace._TESTS_DIR")
    @patch("tools_meta.marketplace._registry_tools")
    def test_export_auto_detect_dependencies(
        self, mock_registry, mock_tests, mock_prod, mock_extract
    ):
        """Auto-detect dependencies during export."""
        mock_extract.return_value = ["dep1", "dep2"]
        
        # Mock tool file
        tool_file = MagicMock()
        tool_file.exists.return_value = True
        tool_file.read_text.return_value = "import tools.dep1"
        
        mock_prod.__truediv__.return_value = tool_file
        mock_tests.__truediv__.return_value = MagicMock(exists=lambda: False)
        
        mock_registry.return_value = {
            "test_tool": {
                "name": "test_tool",
                "version": "1.0.0",
                "description": "Test",
                "author": "test",
                "dependencies": [],
            }
        }
        
        with patch("zipfile.ZipFile"):
            result = marketplace.export_tool("test_tool", auto_deps=True)
        
        # Should have detected dependencies
        mock_extract.assert_called()

    def test_import_tool_invalid_file(self):
        """Reject import of non-existent file."""
        result = marketplace.import_tool("/nonexistent/file.cap")
        assert "File not found" in result or "not found" in result.lower()

    def test_import_tool_wrong_extension(self):
        """Reject import of file with wrong extension."""
        with tempfile.NamedTemporaryFile(suffix=".zip") as f:
            result = marketplace.import_tool(f.name)
            assert ".cap" in result.lower()

    @patch("zipfile.ZipFile")
    def test_import_tool_missing_metadata(self, mock_zip_class):
        """Reject .cap file missing metadata.json."""
        mock_zip = MagicMock()
        mock_zip.namelist.return_value = ["code.py"]  # Missing metadata
        mock_zip_class.return_value.__enter__.return_value = mock_zip
        
        with tempfile.NamedTemporaryFile(suffix=".cap") as f:
            result = marketplace.import_tool(f.name)
            assert "missing metadata.json" in result.lower()


# ── Tests: Local Marketplace Listing ───────────────────────────────────────

class TestListMarketplace:
    """Test list_marketplace()."""

    @patch("tools_meta.marketplace._MARKETPLACE_DIR")
    @patch("tools_meta.marketplace._load_reviews")
    def test_list_marketplace_empty(self, mock_reviews, mock_dir):
        """Handle empty marketplace."""
        mock_dir.glob.return_value = []
        mock_dir.mkdir.return_value = None
        mock_reviews.return_value = {}
        
        result = marketplace.list_marketplace()
        assert "No .cap files" in result

    @patch("tools_meta.marketplace._MARKETPLACE_DIR")
    @patch("tools_meta.marketplace._load_reviews")
    @patch("zipfile.ZipFile")
    def test_list_marketplace_with_ratings(self, mock_zip_class, mock_reviews, mock_dir):
        """List marketplace with ratings."""
        # Create mock .cap file
        mock_cap = MagicMock()
        mock_cap.stem = "test_skill"
        mock_dir.glob.return_value = [mock_cap]
        mock_dir.mkdir.return_value = None
        
        # Mock zip contents
        meta = {
            "name": "test_skill",
            "version": "1.0.0",
            "description": "A test skill",
            "tags": ["test", "demo"],
            "dependencies": [],
        }
        mock_zip = MagicMock()
        mock_zip.read.return_value = json.dumps(meta).encode("utf-8")
        mock_zip.namelist.return_value = ["code.py", "metadata.json"]
        mock_zip_class.return_value.__enter__.return_value = mock_zip
        
        # Mock ratings
        mock_reviews.return_value = {
            "test_skill": {
                "rating": 4.5,
                "review_count": 10,
            }
        }
        
        result = marketplace.list_marketplace(with_ratings=True)
        
        assert "test_skill" in result
        assert "1.0.0" in result
        assert "4.5/5" in result
        assert "10 reviews" in result


# ── Tests: Remote Marketplace ──────────────────────────────────────────────

class TestRemoteMarketplace:
    """Test remote_marketplace functions."""

    @patch("urllib.request.urlopen")
    def test_discover_remote_success(self, mock_urlopen):
        """Successfully discover remote skills."""
        skills_data = {
            "skills": [
                {"name": "skill1", "version": "1.0", "description": "Skill 1"},
                {"name": "skill2", "version": "2.0", "description": "Skill 2"},
            ]
        }
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(skills_data).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response
        
        with patch.dict("os.environ", {"MARKETPLACE_INDEX_URL": "http://localhost"}):
            result = remote_marketplace.discover_remote()
        
        assert len(result) == 2
        assert result[0]["name"] == "skill1"

    @patch("urllib.request.urlopen")
    def test_discover_remote_with_cache(self, mock_urlopen):
        """Use cache when available."""
        cache_data = {
            "skills": [{"name": "cached_skill"}],
            "cached_at": datetime.now().isoformat(),
        }
        
        with patch("tools_meta.remote_marketplace._load_index_cache") as mock_cache:
            mock_cache.return_value = cache_data
            result = remote_marketplace.discover_remote(use_cache=True)
        
        assert len(result) == 1
        assert result[0]["name"] == "cached_skill"
        # Should NOT call urlopen when using cache
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_discover_remote_offline(self, mock_urlopen):
        """Handle offline marketplace gracefully."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        
        with patch("tools_meta.remote_marketplace._load_index_cache") as mock_cache:
            mock_cache.return_value = None
            result = remote_marketplace.discover_remote(use_cache=True)
        
        assert result == []

    def test_search_remote_by_name(self):
        """Search remote skills by name."""
        skills = [
            {"name": "weather_tool", "description": "Weather API", "tags": []},
            {"name": "time_tool", "description": "Time utilities", "tags": []},
            {"name": "clock_widget", "description": "Display clock", "tags": ["weather"]},
        ]
        
        with patch("tools_meta.remote_marketplace.discover_remote") as mock_discover:
            mock_discover.return_value = skills
            result = remote_marketplace.search_remote("weather")
        
        assert len(result) == 2
        assert result[0]["name"] == "weather_tool"
        assert result[1]["name"] == "clock_widget"

    def test_search_remote_by_tag(self):
        """Search remote skills by tag."""
        skills = [
            {"name": "tool1", "description": "Desc", "tags": ["api", "http"]},
            {"name": "tool2", "description": "Desc", "tags": ["file", "io"]},
            {"name": "tool3", "description": "Desc", "tags": ["api", "rest"]},
        ]
        
        with patch("tools_meta.remote_marketplace.discover_remote") as mock_discover:
            mock_discover.return_value = skills
            result = remote_marketplace.search_remote("api")
        
        assert len(result) == 2
        assert result[0]["name"] == "tool1"
        assert result[1]["name"] == "tool3"

    @patch("urllib.request.urlopen")
    def test_download_skill_success(self, mock_urlopen):
        """Successfully download a skill."""
        cap_data = b"fake zip file contents"
        
        mock_response = MagicMock()
        mock_response.read.return_value = cap_data
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("tools_meta.remote_marketplace._CACHE_DIR", Path(tmpdir)):
                result = remote_marketplace.download_skill("test_skill")
        
        assert result is not None
        assert result.suffix == ".cap"

    @patch("urllib.request.urlopen")
    def test_download_skill_failure(self, mock_urlopen):
        """Handle download failure gracefully."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Not found")
        
        result = remote_marketplace.download_skill("nonexistent")
        assert result is None

    @patch("tools_meta.remote_marketplace.download_skill")
    @patch("tools_meta.marketplace.import_tool")
    def test_install_skill_success(self, mock_import, mock_download):
        """Successfully install skill from remote."""
        mock_cap_path = Path("/tmp/test.cap")
        mock_download.return_value = mock_cap_path
        mock_import.return_value = "Imported 'test_skill' v1.0.0"
        
        result = remote_marketplace.install_skill("test_skill")
        
        assert "Imported" in result
        mock_download.assert_called()
        mock_import.assert_called()

    @patch("tools_meta.remote_marketplace.download_skill")
    def test_install_skill_download_failure(self, mock_download):
        """Handle install failure when download fails."""
        mock_download.return_value = None
        
        result = remote_marketplace.install_skill("test_skill")
        
        assert "Failed" in result or "Download" in result

    def test_cache_management(self):
        """Test cache save and load."""
        cache_data = {
            "skills": [{"name": "skill1"}],
            "cached_at": datetime.now().isoformat(),
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "index.json"
            
            with patch("tools_meta.remote_marketplace._INDEX_CACHE_FILE", cache_file):
                remote_marketplace._save_index_cache(cache_data)
                loaded = remote_marketplace._load_index_cache()
        
        assert loaded is not None
        assert loaded["skills"][0]["name"] == "skill1"

    def test_cache_expiry(self):
        """Test cache expiry after max age."""
        old_time = (datetime.now() - timedelta(hours=25)).isoformat()
        cache_data = {
            "skills": [{"name": "skill1"}],
            "cached_at": old_time,
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "index.json"
            cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
            
            with patch("tools_meta.remote_marketplace._INDEX_CACHE_FILE", cache_file):
                loaded = remote_marketplace._load_index_cache()
        
        assert loaded is None  # Cache should be considered expired

    def test_clear_cache(self):
        """Clear marketplace cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            # Create some cache files
            (cache_dir / "skill1.cap").write_text("data")
            (cache_dir / "skill2.cap").write_text("data")
            (cache_dir / "index.json").write_text("{}")
            
            with patch("tools_meta.remote_marketplace._CACHE_DIR", cache_dir):
                count = remote_marketplace.clear_cache()
        
        assert count >= 2


# ── Integration Tests ──────────────────────────────────────────────────────

class TestMarketplaceIntegration:
    """Integration tests combining multiple marketplace components."""

    def test_rating_workflow(self):
        """Complete rating workflow: rate, retrieve, list."""
        # Rate multiple skills
        marketplace.rate_skill("skill_a", 5, "Excellent!")
        marketplace.rate_skill("skill_a", 4, "Good")
        marketplace.rate_skill("skill_b", 3, "Average")
        
        # Retrieve ratings
        ratings_a = marketplace.get_skill_ratings("skill_a")
        assert ratings_a["review_count"] == 2
        assert ratings_a["rating"] == 4.5
        
        ratings_b = marketplace.get_skill_ratings("skill_b")
        assert ratings_b["review_count"] == 1
        assert ratings_b["rating"] == 3.0

    def test_export_with_dependencies(self):
        """Export tool with auto-detected dependencies."""
        code_with_deps = """
from tools.http_tool import fetch
from tools.json_tool import loads

def get_weather():
    resp = fetch("https://api.weather.com")
    return loads(resp)
"""
        
        deps = marketplace._extract_dependencies(code_with_deps)
        assert "http_tool" in deps
        assert "json_tool" in deps
        assert len(deps) == 2

    @patch("tools_meta.remote_marketplace.discover_remote")
    @patch("tools_meta.remote_marketplace.search_remote")
    def test_remote_discovery_and_search(self, mock_search, mock_discover):
        """Combined remote discovery and search."""
        remote_skills = [
            {"name": "weather_api", "tags": ["weather", "api"]},
            {"name": "weather_display", "tags": ["weather", "ui"]},
            {"name": "http_client", "tags": ["http", "api"]},
        ]
        
        mock_discover.return_value = remote_skills
        mock_search.return_value = [remote_skills[0], remote_skills[1]]
        
        # Search for weather-related skills
        result = remote_marketplace.search_remote("weather")
        
        assert len(result) == 2
        assert "weather" in result[0]["tags"] or "weather" in result[1]["tags"]


# ── Edge Cases and Error Handling ──────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and error scenarios."""

    def test_rate_skill_corrupted_reviews_file(self):
        """Handle corrupted reviews.json gracefully."""
        marketplace._REVIEWS_FILE.write_text("{ invalid json }", encoding="utf-8")
        
        # Should load as empty and continue
        msg = marketplace.rate_skill("test", rating=5)
        assert "Rated" in msg or "5/5" in msg

    def test_unicode_in_ratings(self):
        """Handle unicode in rating reviews."""
        msg = marketplace.rate_skill("tool", 5, "Very good! 🌟 完璧です!")
        assert "5/5" in msg

    def test_very_long_review_text(self):
        """Handle very long review text."""
        long_review = "Great " * 1000
        marketplace.rate_skill("tool", 5, long_review)
        
        ratings = marketplace.get_skill_ratings("tool")
        assert ratings is not None
        assert ratings["review_count"] == 1

    def test_dependency_extraction_edge_cases(self):
        """Extract dependencies with various edge cases."""
        code = """
from tools.tool_123 import func  # Tool with numbers
from tools._private import hidden
import tools.camelCaseTools
# from tools.not_imported import skip
from tools . spaced_tool import func  # With spaces (won't match)
"""
        deps = marketplace._extract_dependencies(code)
        assert "tool_123" in deps
        assert "_private" in deps
        assert "camelCaseTools" in deps


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
