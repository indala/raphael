"""
Tool Metadata Manager — tracks lifecycle state, versions, and history of every tool.

Each tool progresses through these states:
    DESIGNED → GENERATED → VALIDATED → TESTED → BENCHMARKED → REVIEWED → REGISTERED → ACTIVE
                                                                                       ↓
                                                                                  ARCHIVED

Health monitoring: ACTIVE tools can transition to DEGRADED (poor performance/errors)
or BROKEN (non-functional). The Tool Manager auto-triggers optimization for DEGRADED
tools and notifies for BROKEN tools.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_META_DIR = Path(__file__).resolve().parent
_REGISTRY_PATH = _META_DIR / "registry.json"
_SANDBOX_DIR = _META_DIR / "sandbox"

# ── Lifecycle States ───────────────────────────────────────────────────

STATE_DESIGNED = "designed"
STATE_GENERATED = "generated"
STATE_VALIDATED = "validated"
STATE_TESTED = "tested"
STATE_BENCHMARKED = "benchmarked"
STATE_REVIEWED = "reviewed"
STATE_REGISTERED = "registered"
STATE_ACTIVE = "active"
STATE_DEGRADED = "degraded"
STATE_BROKEN = "broken"
STATE_ARCHIVED = "archived"

VALID_TRANSITIONS = {
    None:               [STATE_DESIGNED],
    STATE_DESIGNED:     [STATE_GENERATED],
    STATE_GENERATED:    [STATE_VALIDATED],
    STATE_VALIDATED:    [STATE_TESTED, STATE_GENERATED],  # fail → redesign
    STATE_TESTED:       [STATE_BENCHMARKED, STATE_GENERATED],
    STATE_BENCHMARKED:  [STATE_REVIEWED, STATE_GENERATED],
    STATE_REVIEWED:     [STATE_REGISTERED, STATE_GENERATED],
    STATE_REGISTERED:   [STATE_ACTIVE],
    STATE_ACTIVE:       [STATE_DEGRADED, STATE_ARCHIVED, STATE_DESIGNED],
    STATE_DEGRADED:     [STATE_DESIGNED, STATE_BROKEN, STATE_ACTIVE],
    STATE_BROKEN:       [STATE_DESIGNED, STATE_ARCHIVED],
    STATE_ARCHIVED:     [STATE_DESIGNED],                   # unarchive
}


def _load() -> dict:
    """Load the tool registry from disk."""
    if not _REGISTRY_PATH.exists():
        return {"tools": {}}
    try:
        return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Failed to load tool registry: %s", e)
        return {"tools": {}}


def _save(data: dict):
    """Atomically save the tool registry."""
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_tool_meta(name: str) -> dict | None:
    """Get metadata for a specific tool."""
    registry = _load()
    return registry.get("tools", {}).get(name)  # type: ignore[no-any-return]


def list_tools(status: str | None = None) -> list[dict]:
    """List all tools, optionally filtered by status."""
    registry = _load()
    tools = list(registry.get("tools", {}).values())
    if status:
        tools = [t for t in tools if t.get("status") == status]
    return sorted(tools, key=lambda t: t.get("name", ""))


def set_state(name: str, new_state: str) -> str:
    """Transition a tool to a new lifecycle state. Returns error msg or empty string."""
    registry = _load()
    tools = registry.setdefault("tools", {})
    meta = tools.get(name)

    current = meta.get("status") if meta else None
    allowed = VALID_TRANSITIONS.get(current, [])

    if new_state not in allowed:
        return (
            f"Cannot transition '{name}' from '{current}' to '{new_state}'. "
            f"Allowed transitions from '{current}': {', '.join(allowed)}"
        )

    if meta is None:
        # Creating a new entry
        meta = {
            "name": name,
            "version": "0.1.0",
            "status": new_state,
            "description": "",
            "author": "tool_manager",
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
            "tests": [],
            "benchmarks": [],
            "file": "",
            "changelog": [],
        }
        tools[name] = meta
    else:
        meta["status"] = new_state
        meta["updated"] = datetime.now().isoformat()

    _save(registry)
    return ""


def init_tool(
    name: str,
    description: str,
    author: str = "tool_manager",
    dependencies: list[str] | None = None,
) -> str:
    """Initialize a new tool entry in DESIGNED state. Returns error msg or empty string."""
    registry = _load()
    tools = registry.setdefault("tools", {})

    if name in tools:
        existing = tools[name]
        if existing.get("status") != STATE_ARCHIVED:
            return f"Tool '{name}' already exists (status: {existing.get('status')}). Use update_tool or choose a different name."

    # Build dependency list
    deps = list(dependencies or [])
    # Auto-populate depended_by on dependency targets
    for dep_name in deps:
        dep_meta = tools.get(dep_name)
        if dep_meta:
            dep_meta.setdefault("depended_by", [])
            if name not in dep_meta["depended_by"]:
                dep_meta["depended_by"].append(name)

    tools[name] = {
        "name": name,
        "version": "0.1.0",
        "status": STATE_DESIGNED,
        "description": description,
        "author": author,
        "dependencies": deps,
        "depended_by": [],
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
        "tests": [],
        "benchmarks": [],
        "file": "",
        "changelog": [
            {"version": "0.1.0", "date": datetime.now().isoformat(), "change": "Initial design"},
        ],
    }
    _save(registry)
    return ""


def update_meta(name: str, **updates) -> str:
    """Update specific metadata fields. Returns error msg or empty string."""
    registry = _load()
    tools = registry.setdefault("tools", {})
    meta = tools.get(name)

    if not meta:
        return f"Tool '{name}' not found in registry."

    for key, value in updates.items():
        if key in ("name", "created", "changelog"):
            continue  # immutable fields
        meta[key] = value

    meta["updated"] = datetime.now().isoformat()
    _save(registry)
    return ""


def bump_version(name: str, bump: str = "patch") -> str:
    """Bump the version (patch/minor/major). Returns new version or error."""
    registry = _load()
    tools = registry.setdefault("tools", {})
    meta = tools.get(name)

    if not meta:
        return f"Tool '{name}' not found."

    parts = meta["version"].split(".")
    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        return f"Cannot parse version: {meta['version']}"

    if bump == "major":
        major += 1; minor = 0; patch = 0
    elif bump == "minor":
        minor += 1; patch = 0
    else:  # patch
        patch += 1

    new_version = f"{major}.{minor}.{patch}"
    meta["version"] = new_version
    meta["updated"] = datetime.now().isoformat()
    meta.setdefault("changelog", []).append({
        "version": new_version,
        "date": datetime.now().isoformat(),
        "change": f"{bump} bump",
    })
    _save(registry)
    return new_version


def add_changelog(name: str, change: str):
    """Append a changelog entry for the current version."""
    registry = _load()
    meta = registry.get("tools", {}).get(name)
    if not meta:
        return
    meta.setdefault("changelog", []).append({
        "version": meta["version"],
        "date": datetime.now().isoformat(),
        "change": change,
    })
    meta["updated"] = datetime.now().isoformat()
    _save(registry)


def record_test_result(name: str, test_name: str, passed: bool, detail: str = ""):
    """Record a test result for a tool."""
    registry = _load()
    meta = registry.get("tools", {}).get(name)
    if not meta:
        return
    meta.setdefault("tests", []).append({
        "name": test_name,
        "passed": passed,
        "detail": detail[:200],
        "run_at": datetime.now().isoformat(),
    })
    _save(registry)


def record_benchmark(name: str, bench_name: str, result_ms: float):
    """Record a benchmark result for a tool."""
    registry = _load()
    meta = registry.get("tools", {}).get(name)
    if not meta:
        return
    meta.setdefault("benchmarks", []).append({
        "name": bench_name,
        "result_ms": round(result_ms, 2),
        "run_at": datetime.now().isoformat(),
    })
    _save(registry)


def delete_tool(name: str) -> str:
    """Remove a tool from the registry entirely. Returns error msg or empty string."""
    registry = _load()
    tools = registry.get("tools", {})
    if name not in tools:
        return f"Tool '{name}' not found in registry."
    del tools[name]
    _save(registry)
    return ""


def propagate_dependency_changes(name: str) -> list[str]:
    """When a tool is archived/broken, flag all tools that depend on it.

    Args:
        name: Tool name that changed state.

    Returns:
        List of affected dependent tools.
    """
    registry = _load()
    tools = registry.get("tools", {})
    meta = tools.get(name)
    if not meta:
        return []

    affected = []
    for dep_name in meta.get("depended_by", []):
        dep_meta = tools.get(dep_name)
        if dep_meta and dep_meta.get("status") in (STATE_ACTIVE, STATE_DEGRADED):
            from tools_meta.manager import set_state
            set_state(dep_name, STATE_DEGRADED)
            affected.append(dep_name)
    return affected


def rollback_tool(name: str, target_version: str) -> str:
    """Rollback a tool to a previous version (changelog trace only — code restore not managed here).

    Args:
        name: Tool name.
        target_version: Version string to rollback to (e.g. "0.1.0").

    Returns:
        Status message.
    """
    registry = _load()
    tools = registry.get("tools", {})
    meta = tools.get(name)

    if not meta:
        return f"Tool '{name}' not found."

    changelog = meta.get("changelog", [])
    version_found = None
    for entry in changelog:
        if entry.get("version") == target_version:
            version_found = entry
            break

    if not version_found:
        return f"Version '{target_version}' not found in '{name}' changelog. Available: {', '.join(e['version'] for e in changelog)}"

    # Record rollback in changelog
    current = meta["version"]
    meta["version"] = target_version
    meta["updated"] = datetime.now().isoformat()
    meta.setdefault("changelog", []).append({
        "version": target_version,
        "date": datetime.now().isoformat(),
        "change": f"Rolled back from {current} to {target_version}",
    })
    _save(registry)

    # Propagate to dependents
    affected = propagate_dependency_changes(name)
    msg = f"Rolled back '{name}' from {current} to {target_version}."
    if affected:
        msg += f" Marked dependents as degraded: {', '.join(affected)}"
    return msg


def get_summary() -> str:
    """Return a human-readable summary of all tools and their states."""
    registry = _load()
    tools = registry.get("tools", {})
    if not tools:
        return "No tools in registry."

    lines = ["**Tool Registry Summary:**"]
    by_status: dict[str, list[Any]] = {}  # type: ignore[name-defined]
    for name, meta in tools.items():
        status = meta.get("status", "unknown")
        by_status.setdefault(status, []).append(name)

    for status in [STATE_ACTIVE, STATE_REGISTERED, STATE_REVIEWED, STATE_TESTED,
                   STATE_VALIDATED, STATE_GENERATED, STATE_DESIGNED, STATE_ARCHIVED]:
        names = by_status.pop(status, [])
        if names:
            lines.append(f"  **{status.upper()}:** {', '.join(sorted(names))}")

    # Remaining statuses
    for status, names in sorted(by_status.items()):
        lines.append(f"  **{status.upper()}:** {', '.join(sorted(names))}")

    lines.append(f"\nTotal: {len(tools)} tools")
    return "\n".join(lines)
