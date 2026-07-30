"""Capability Marketplace — export/import/share generated tools as .cap files.

Format: .cap file is a zip containing:
  - code.py        (the tool implementation)
  - metadata.json  (tool metadata from registry)
  - test.py        (auto-generated test file)

Export flow:
  read tool from generated/production/ + registry metadata + tests → zip → .cap

Import flow:
  read .cap → unpack → validate dependencies → install to generated/production/
  → reload_tools() → register
"""

import json
import logging
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_META_DIR = Path(__file__).resolve().parent
_REGISTRY_PATH = _META_DIR / "registry.json"
_MARKETPLACE_DIR = _META_DIR / "marketplace"

# Tool directories (relative to project root)
_PROJECT_DIR = _META_DIR.parent
_TOOLS_PROD = _PROJECT_DIR / "orchestrator" / "tools" / "generated" / "production"
_TESTS_DIR = _PROJECT_DIR / "tests" / "generated"


def _registry_tools() -> dict:
    """Load registry data."""
    if not _REGISTRY_PATH.exists():
        return {}
    try:
        data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        return data.get("tools", {})  # type: ignore[no-any-return]
    except Exception:
        return {}


def export_tool(name: str, output_dir: str | None = None) -> str:
    """Package a tool into a .cap file.

    Args:
        name: Tool name (must exist in generated/production/).
        output_dir: Where to save the .cap file. Defaults to marketplace/.

    Returns:
        Path to the created .cap file, or error message.
    """
    # Check tool code exists
    code_path = _TOOLS_PROD / f"{name}.py"
    if not code_path.exists():
        return f"Tool '{name}' not found in generated/production/. Only generated tools can be exported."

    # Check test exists
    test_path = _TESTS_DIR / f"test_{name}.py"
    # Metadata from registry
    tools = _registry_tools()
    meta = tools.get(name, {})
    if not meta:
        return f"Tool '{name}' not found in registry. Register it first."

    # Create marketplace dir
    out_dir = Path(output_dir) if output_dir else _MARKETPLACE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cap_path = out_dir / f"{name}.cap"

    # Build metadata.json
    meta_export = {
        "name": meta["name"],
        "version": meta["version"],
        "description": meta["description"],
        "author": meta.get("author", "tool_manager"),
        "dependencies": meta.get("dependencies", []),
        "created": meta.get("created", ""),
        "updated": datetime.now().isoformat(),
        "changelog": meta.get("changelog", []),
    }

    # Create zip
    with zipfile.ZipFile(cap_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(code_path, "code.py")
        zf.writestr("metadata.json", json.dumps(meta_export, indent=2))
        if test_path.exists():
            zf.write(test_path, "test.py")

    logger.info("Exported tool '%s' to %s", name, cap_path)
    return f"Exported '{name}' v{meta['version']} to {cap_path}"


def import_tool(cap_path: str) -> str:
    """Install a tool from a .cap file.

    Args:
        cap_path: Path to the .cap file.

    Returns:
        Status message.
    """
    cap = Path(cap_path)
    if not cap.exists():
        return f"File not found: {cap_path}"
    if cap.suffix != ".cap":
        return "Invalid file: must have .cap extension."

    # Extract
    try:
        with zipfile.ZipFile(cap, "r") as zf:
            # Validate required files
            required = ["code.py", "metadata.json"]
            for f in required:
                if f not in zf.namelist():
                    return f"Invalid .cap file: missing {f}"

            meta = json.loads(zf.read("metadata.json"))
            name = meta["name"]
            dependencies = meta.get("dependencies", [])

            # Validate dependencies exist in current registry
            tools = _registry_tools()
            for dep in dependencies:
                if dep not in tools:
                    return (f"Dependency '{dep}' not found in registry. "
                            f"Install '{dep}' first before importing '{name}'.")

            # Check version conflict
            existing = tools.get(name)
            if existing and existing.get("status") not in ("archived",):
                return (f"Tool '{name}' already exists (status: {existing.get('status')}). "
                        f"Use 'archive_tool' first if you want to replace it.")

            # Extract files
            _TOOLS_PROD.mkdir(parents=True, exist_ok=True)
            code_content = zf.read("code.py")
            (_TOOLS_PROD / f"{name}.py").write_bytes(code_content)

            if "test.py" in zf.namelist():
                _TESTS_DIR.mkdir(parents=True, exist_ok=True)
                test_content = zf.read("test.py")
                (_TESTS_DIR / f"test_{name}.py").write_bytes(test_content)

            # Update registry
            from tools_meta.manager import init_tool, set_state
            err = init_tool(name, meta.get("description", ""),
                           author=meta.get("author", "tool_manager"),
                           dependencies=dependencies)
            if err and "already exists" not in err:
                return f"Registry update failed: {err}"

            # Walk to ACTIVE
            from tools_meta.manager import STATE_ACTIVE
            for s in ["generated", "validated", "tested", "benchmarked",
                      "reviewed", "registered", STATE_ACTIVE]:
                set_state(name, s)

            # Reload tools
            try:
                from orchestrator.tools import reload_tools
                reload_tools()
            except Exception:
                pass

            logger.info("Imported tool '%s' from %s", name, cap_path)
            return (f"Imported '{name}' v{meta.get('version', '?')} "
                    f"with {len(dependencies)} dependencies. Ready to use.")

    except zipfile.BadZipFile:
        return "Invalid .cap file: not a valid zip archive."
    except Exception as e:
        logger.error("Import failed: %s", e)
        return f"Import failed: {e}"


def list_marketplace() -> str:
    """List all available .cap files in the marketplace directory."""
    _MARKETPLACE_DIR.mkdir(parents=True, exist_ok=True)
    caps = sorted(_MARKETPLACE_DIR.glob("*.cap"))
    if not caps:
        return "No .cap files in marketplace."

    lines = ["**Available Marketplace Packages:**\n"]
    for c in caps:
        try:
            with zipfile.ZipFile(c, "r") as zf:
                meta = json.loads(zf.read("metadata.json"))
                name = meta.get("name", c.stem)
                version = meta.get("version", "?")
                desc = meta.get("description", "")
                deps = meta.get("dependencies", [])
                has_test = "test.py" in zf.namelist()
                lines.append(f"**{name}** v{version}")
                if desc:
                    lines.append(f"  {desc}")
                lines.append(f"  Dependencies: {', '.join(deps) if deps else 'None'}")
                lines.append(f"  Tests included: {'✓' if has_test else '✗'}")
                lines.append("")
        except Exception as e:
            lines.append(f"**{c.stem}** (corrupt: {e})\n")

    return "\n".join(lines)
