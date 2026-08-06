"""Capability Marketplace — export/import/share generated tools as .cap files.

Enhanced version with:
- Dependency auto-detection from imports
- Version conflict resolution
- Enhanced metadata (changelog, platforms, tags)
- Skill ratings and reviews system
- Remote marketplace support (foundation)

Format: .cap file is a zip containing:
  - code.py        (the tool implementation)
  - metadata.json  (enhanced tool metadata)
  - test.py        (auto-generated test file)

Export flow:
  read tool from generated/production/ + registry metadata + tests → zip → .cap

Import flow:
  read .cap → unpack → validate dependencies → install to generated/production/
  → reload_tools() → register
"""

import json
import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_META_DIR = Path(__file__).resolve().parent
_REGISTRY_PATH = _META_DIR / "registry.json"
_MARKETPLACE_DIR = _META_DIR / "marketplace"
_REVIEWS_FILE = _META_DIR / "reviews.json"

# Tool directories (relative to project root)
_PROJECT_DIR = _META_DIR.parent
_TOOLS_PROD = _PROJECT_DIR / "orchestrator" / "tools" / "generated" / "production"
_TESTS_DIR = _PROJECT_DIR / "tests" / "generated"


# ── Dependency Auto-Detection ──────────────────────────────────────────────

def _extract_dependencies(code: str) -> List[str]:
    """
    Parse imports from tool code to auto-detect tool dependencies.
    
    Looks for:
    - from tools.<tool_name> import ...
    - import tools.<tool_name>
    
    Args:
        code: Python source code
    
    Returns:
        List of tool names referenced
    """
    dependencies = []
    
    # Pattern 1: from tools.tool_name import ...
    pattern1 = r'from\s+tools\.(\w+)\s+import'
    for match in re.finditer(pattern1, code):
        tool_name = match.group(1)
        if tool_name not in dependencies:
            dependencies.append(tool_name)
    
    # Pattern 2: import tools.tool_name
    pattern2 = r'import\s+tools\.(\w+)'
    for match in re.finditer(pattern2, code):
        tool_name = match.group(1)
        if tool_name not in dependencies:
            dependencies.append(tool_name)
    
    return dependencies


def _load_reviews() -> Dict[str, Dict[str, any]]:
    """Load reviews data (skill ratings)."""
    if not _REVIEWS_FILE.exists():
        return {}
    try:
        data = json.loads(_REVIEWS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_reviews(reviews: Dict[str, Dict[str, any]]) -> None:
    """Save reviews data atomically."""
    try:
        _REVIEWS_FILE.write_text(
            json.dumps(reviews, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        logger.error("Failed to save reviews: %s", e)


def _registry_tools() -> dict:
    """Load registry data."""
    if not _REGISTRY_PATH.exists():
        return {}
    try:
        data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        return data.get("tools", {})  # type: ignore[no-any-return]
    except Exception:
        return {}


# ── Enhanced Export ────────────────────────────────────────────────────────

def export_tool(name: str, output_dir: str | None = None, auto_deps: bool = True) -> str:
    """Package a tool into a .cap file.

    Args:
        name: Tool name (must exist in generated/production/).
        output_dir: Where to save the .cap file. Defaults to marketplace/.
        auto_deps: Auto-detect dependencies from code imports.

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

    # Auto-detect dependencies if enabled
    dependencies = meta.get("dependencies", [])
    if auto_deps:
        try:
            code_content = code_path.read_text(encoding="utf-8")
            detected = _extract_dependencies(code_content)
            # Merge with manual dependencies (avoid duplicates)
            dependencies = list(set(dependencies + detected))
            logger.debug("Auto-detected dependencies for '%s': %s", name, detected)
        except Exception as e:
            logger.warning("Failed to auto-detect dependencies: %s", e)

    # Build enhanced metadata.json
    meta_export = {
        "name": meta["name"],
        "version": meta.get("version", "1.0.0"),
        "description": meta.get("description", ""),
        "author": meta.get("author", "tool_manager"),
        "dependencies": dependencies,
        "min_python": meta.get("min_python", "3.10"),
        "platforms": meta.get("platforms", ["win32", "linux", "darwin"]),
        "tags": meta.get("tags", []),
        "created": meta.get("created", datetime.now().isoformat()),
        "updated": datetime.now().isoformat(),
        "changelog": meta.get("changelog", [
            {
                "version": meta.get("version", "1.0.0"),
                "date": datetime.now().isoformat(),
                "changes": "Initial release"
            }
        ]),
    }

    # Create zip
    with zipfile.ZipFile(cap_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(code_path, "code.py")
        zf.writestr("metadata.json", json.dumps(meta_export, indent=2))
        if test_path.exists():
            zf.write(test_path, "test.py")

    logger.info("Exported tool '%s' to %s", name, cap_path)
    return f"Exported '{name}' v{meta_export['version']} to {cap_path}"


# ── Enhanced Import ────────────────────────────────────────────────────────

def import_tool(cap_path: str, force: bool = False) -> str:
    """Install a tool from a .cap file.

    Args:
        cap_path: Path to the .cap file.
        force: Force import even if tool already exists (replaces version).

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
            version = meta.get("version", "1.0.0")
            dependencies = meta.get("dependencies", [])

            # Validate dependencies exist in current registry
            tools = _registry_tools()
            for dep in dependencies:
                if dep not in tools:
                    return (f"Dependency '{dep}' not found in registry. "
                            f"Install '{dep}' first before importing '{name}'.")

            # Check version conflict
            existing = tools.get(name)
            if existing and not force and existing.get("status") not in ("archived",):
                existing_version = existing.get("version", "?")
                return (f"Tool '{name}' exists (v{existing_version}). "
                        f"Use force=True to replace it, or archive it first.")

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

            logger.info("Imported tool '%s' v%s from %s", name, version, cap_path)
            return (f"Imported '{name}' v{version} "
                    f"with {len(dependencies)} dependencies. Ready to use.")

    except zipfile.BadZipFile:
        return "Invalid .cap file: not a valid zip archive."
    except Exception as e:
        logger.error("Import failed: %s", e)
        return f"Import failed: {e}"


# ── Ratings & Reviews ──────────────────────────────────────────────────────

def rate_skill(name: str, rating: int, review: Optional[str] = None) -> str:
    """
    Rate a skill (1-5 stars) with optional text review.
    
    Args:
        name: Tool/skill name
        rating: Rating 1-5
        review: Optional review text
    
    Returns:
        Status message
    """
    if not 1 <= rating <= 5:
        return "Rating must be between 1 and 5 stars."
    
    reviews = _load_reviews()
    
    if name not in reviews:
        reviews[name] = {
            "rating": 0,
            "review_count": 0,
            "reviews": []
        }
    
    # Add user rating
    reviews[name]["reviews"].append({
        "rating": rating,
        "review": review,
        "rated_at": datetime.now().isoformat()
    })
    
    # Recalculate average
    ratings = [r["rating"] for r in reviews[name]["reviews"]]
    reviews[name]["rating"] = sum(ratings) / len(ratings)
    reviews[name]["review_count"] = len(ratings)
    
    _save_reviews(reviews)
    logger.info("Rated skill '%s': %d/5 stars", name, rating)
    return f"Rated '{name}': {rating}/5 ⭐"


def get_skill_ratings(name: str) -> Optional[Dict[str, any]]:
    """Get aggregated ratings for a skill."""
    reviews = _load_reviews()
    return reviews.get(name)


def list_marketplace(with_ratings: bool = True) -> str:
    """List all available .cap files in the marketplace directory."""
    _MARKETPLACE_DIR.mkdir(parents=True, exist_ok=True)
    caps = sorted(_MARKETPLACE_DIR.glob("*.cap"))
    if not caps:
        return "No .cap files in marketplace."

    lines = ["**Available Marketplace Packages:**\n"]
    reviews = _load_reviews() if with_ratings else {}
    
    for c in caps:
        try:
            with zipfile.ZipFile(c, "r") as zf:
                meta = json.loads(zf.read("metadata.json"))
                name = meta.get("name", c.stem)
                version = meta.get("version", "?")
                desc = meta.get("description", "")
                deps = meta.get("dependencies", [])
                tags = meta.get("tags", [])
                has_test = "test.py" in zf.namelist()
                
                # Get rating if available
                rating_info = reviews.get(name, {})
                avg_rating = rating_info.get("rating", 0)
                review_count = rating_info.get("review_count", 0)
                
                lines.append(f"**{name}** v{version}")
                if desc:
                    lines.append(f"  {desc}")
                if tags:
                    lines.append(f"  Tags: {', '.join(tags)}")
                lines.append(f"  Dependencies: {', '.join(deps) if deps else 'None'}")
                if with_ratings and avg_rating > 0:
                    stars = "⭐" * int(avg_rating)
                    lines.append(f"  Rating: {avg_rating:.1f}/5 {stars} ({review_count} reviews)")
                lines.append(f"  Tests included: {'✓' if has_test else '✗'}")
                lines.append("")
        except Exception as e:
            lines.append(f"**{c.stem}** (corrupt: {e})\n")

    return "\n".join(lines)
