"""Tests for the Capability Marketplace."""

import json
import zipfile
from pathlib import Path
from tools_meta.manager import init_tool, set_state, delete_tool, STATE_ACTIVE


def setup_function():
    for name in ("mkt_tool", "mkt_dep"):
        delete_tool(name)
    # Clean up test .cap files
    mkt_dir = Path(__file__).resolve().parent.parent / "tools_meta" / "marketplace"
    mkt_dir.mkdir(parents=True, exist_ok=True)
    for f in mkt_dir.glob("*.cap"):
        f.unlink()


def _create_dummy_tool(name, version="0.1.0", deps=None):
    """Create a minimal tool entry in registry."""
    err = init_tool(name, f"Test {name}", dependencies=deps or [])
    if err and "already exists" not in err:
        raise RuntimeError(f"init_tool failed: {err}")
    # Walk to ACTIVE
    for s in ["generated", "validated", "tested", "benchmarked", "reviewed", "registered", STATE_ACTIVE]:
        set_state(name, s)

    # Create a dummy code file
    prod_dir = Path(__file__).resolve().parent.parent / "orchestrator" / "tools" / "generated" / "production"
    prod_dir.mkdir(parents=True, exist_ok=True)
    code_path = prod_dir / f"{name}.py"
    if not code_path.exists():
        code_path.write_text(f"# Dummy tool: {name}\ndef get_schemas():\n    return []\n", encoding="utf-8")


def test_export_tool():
    """Exporting a tool should produce a .cap file."""
    _create_dummy_tool("mkt_tool")
    from tools_meta.marketplace import export_tool
    result = export_tool("mkt_tool")
    assert "Exported" in result
    assert ".cap" in result


def test_export_nonexistent():
    """Exporting a nonexistent tool should return an error."""
    from tools_meta.marketplace import export_tool
    result = export_tool("nonexistent_tool")
    assert "not found" in result.lower()


def test_export_creates_valid_zip():
    """Exported .cap should contain code.py and metadata.json."""
    _create_dummy_tool("mkt_tool")
    from tools_meta.marketplace import export_tool
    export_tool("mkt_tool")

    mkt_dir = Path(__file__).resolve().parent.parent / "tools_meta" / "marketplace"
    cap_path = mkt_dir / "mkt_tool.cap"
    assert cap_path.exists()

    with zipfile.ZipFile(cap_path, "r") as zf:
        assert "code.py" in zf.namelist()
        assert "metadata.json" in zf.namelist()
        meta = json.loads(zf.read("metadata.json"))
        assert meta["name"] == "mkt_tool"


def test_list_marketplace():
    """list_marketplace should show exported packages."""
    _create_dummy_tool("mkt_tool")
    from tools_meta.marketplace import export_tool, list_marketplace
    export_tool("mkt_tool")
    result = list_marketplace()
    assert "mkt_tool" in result


def test_import_tool():
    """Importing a tool should register it."""
    _create_dummy_tool("mkt_tool")
    from tools_meta.marketplace import export_tool, import_tool
    path = export_tool("mkt_tool")
    cap_path = path.split("to ")[-1]
    result = import_tool(cap_path)
    assert "Imported" in result or "already exists" in result


def test_import_invalid_cap():
    """Importing an invalid file should return an error."""
    from tools_meta.marketplace import import_tool
    # Create an invalid .cap
    bad_path = Path(__file__).resolve().parent.parent / "tools_meta" / "marketplace" / "bad.cap"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("not a zip", encoding="utf-8")
    result = import_tool(str(bad_path))
    assert "Invalid" in result or "not a valid" in result
