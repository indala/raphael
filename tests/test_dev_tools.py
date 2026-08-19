"""Tests for the Developer Tool Suite (grep_search, find_files, git_status, git_diff, run_tests, run_linter)."""

from orchestrator.tools.native import dev_tools


def test_grep_search():
    res = dev_tools.grep_search("def test_grep_search", path="tests", file_pattern="*.py")
    assert "test_dev_tools.py" in res
    assert "def test_grep_search" in res

    no_match_query = "nonexistent_" + "token_99887766"
    no_match = dev_tools.grep_search(no_match_query, path="tests")
    assert "No matches found" in no_match


def test_find_files():
    res = dev_tools.find_files("test_smoke.py", directory="tests")
    assert "test_smoke.py" in res

    no_match = dev_tools.find_files("nonexistent_file_xyz123.abc", directory="tests")
    assert "No files found" in no_match


def test_git_status():
    res = dev_tools.git_status()
    assert "Git branch:" in res


def test_git_diff():
    res = dev_tools.git_diff()
    assert isinstance(res, str)


def test_run_tests():
    res = dev_tools.run_tests("tests/test_smoke.py::test_parse_semver", framework="pytest", timeout_s=15)
    assert "PASSED" in res
    assert "test_parse_semver" in res


def test_run_linter():
    res = dev_tools.run_linter("orchestrator/tools/native/dev_tools.py", linter="ruff")
    assert "Linter [" in res


def test_get_code_outline():
    res = dev_tools.get_code_outline("agents/coding_agent.py")
    assert "Code Outline for coding_agent.py" in res
    assert "class CodingAgent" in res
    assert "run(" in res


def test_read_file_range():
    res = dev_tools.read_file_range("agents/coding_agent.py", start_line=1, end_line=15)
    assert "coding_agent.py lines 1-15" in res
    assert "CodingAgent" in res or "coding" in res or "import" in res

