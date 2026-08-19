"""Tests for advanced agent developer tools (view_file, replace_file_content, cloc, tree, jq, scan_secrets)."""

import json
from pathlib import Path

from orchestrator.tools.native import dev_tools, files


def test_view_file_text_and_slicing(tmp_path: Path):
    test_file = tmp_path / "sample.py"
    lines = [f"print('Line {i}')" for i in range(1, 31)]
    test_file.write_text("\n".join(lines), encoding="utf-8")

    res = files.view_file(str(test_file), start_line=5, end_line=10)
    assert "File: sample.py" in res
    assert "Lines: 5-10 of 30" in res
    assert "   5: print('Line 5')" in res
    assert "  10: print('Line 10')" in res
    assert "print('Line 11')" not in res


def test_view_file_binary_guard(tmp_path: Path):
    pdf_file = tmp_path / "document.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy binary content")

    res = files.view_file(str(pdf_file))
    assert "Cannot view 'document.pdf' as plain text" in res
    assert "process_file" in res


def test_replace_file_content(tmp_path: Path):
    test_file = tmp_path / "code.py"
    test_file.write_text("def hello():\n    return 'old'\n", encoding="utf-8")

    # Read first to satisfy read-before-edit
    files.view_file(str(test_file))

    res = files.replace_file_content(
        str(test_file),
        target_content="return 'old'",
        replacement_content="return 'new'",
    )
    assert "Successfully updated" in res
    assert test_file.read_text(encoding="utf-8") == "def hello():\n    return 'new'\n"


def test_count_lines_of_code(tmp_path: Path):
    py_file = tmp_path / "main.py"
    py_file.write_text("# This is a comment\n\ndef add(a, b):\n    return a + b\n", encoding="utf-8")

    res = dev_tools.count_lines_of_code(str(tmp_path))
    assert "Code Metrics for" in res
    assert "Python" in res
    assert "SUM:" in res


def test_tree_directory(tmp_path: Path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("hello", encoding="utf-8")

    res = dev_tools.tree_directory(str(tmp_path), max_depth=2)
    assert "subdir/" in res
    assert "nested.txt" in res


def test_query_json(tmp_path: Path):
    json_file = tmp_path / "config.json"
    data = {
        "name": "raphael-app",
        "version": "2.4.0",
        "dependencies": {
            "react": "^19.0.0",
            "next": "^15.0.0"
        },
        "servers": [{"url": "https://api.dev.com"}, {"url": "https://api.prod.com"}]
    }
    json_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    res = dev_tools.query_json(str(json_file), "dependencies.react")
    assert "19.0.0" in res

    res2 = dev_tools.query_json(str(json_file), "servers[0].url")
    assert "https://api.dev.com" in res2


def test_scan_secrets(tmp_path: Path):
    clean_file = tmp_path / "clean.py"
    clean_file.write_text("x = 42\n", encoding="utf-8")
    res_clean = dev_tools.scan_secrets(str(tmp_path))
    assert "Security Audit Clean" in res_clean

    secret_file = tmp_path / "secrets.py"
    # Dynamically format dummy test key to prevent git push protection false positive
    fake_key = "".join(["s", "k", "-", "proj-", "abcdefghijklmnopqrstuvwxyz1234567890"])
    secret_file.write_text(f"OPENAI_KEY = '{fake_key}'\n", encoding="utf-8")
    res_secret = dev_tools.scan_secrets(str(tmp_path))
    assert "potential secret(s)" in res_secret
    assert "OpenAI API Key" in res_secret
