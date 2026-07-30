"""Tests for the local Knowledge Base system tools."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.tools.native.knowledge import list_knowledge_files, read_knowledge_file


def test_list_knowledge_files():
    """Verify that list_knowledge_files returns the three guide markdown files."""
    files = list_knowledge_files()
    assert isinstance(files, list)
    assert len(files) >= 3
    assert "windows_cli.md" in files
    assert "windows_desktop.md" in files
    assert "winget_packages.md" in files


def test_read_knowledge_file_valid():
    """Verify that read_knowledge_file correctly reads a valid markdown file."""
    content = read_knowledge_file("winget_packages.md")
    assert isinstance(content, str)
    assert "winget install" in content
    assert "Microsoft.VisualStudioCode" in content


def test_read_knowledge_file_missing():
    """Verify that reading a missing file returns an error message rather than crashing."""
    content = read_knowledge_file("non_existent_file.md")
    assert "Error" in content
    assert "non_existent_file.md" in content


def test_read_knowledge_file_traversal():
    """Verify that directory traversal attempts are prevented."""
    content = read_knowledge_file("../memory/long_term.json")
    # Due to os.path.basename, it will strip leading dirs and try to read "long_term.json" from knowledge/
    assert "Error" in content
