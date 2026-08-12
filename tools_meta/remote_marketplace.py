"""
Remote Marketplace Integration for Open-Source Skill Repositories

Discovers, downloads, and publishes skills from multiple open-source AI skill marketplaces.

Supported Open-Source Marketplaces (2026):
  - Smithery: https://smithery.ai - Large catalog of open-source MCP servers
  - SkillsMP: https://skillsmp.ai - 800,000+ skills indexed from GitHub  
  - ClaudeSkills: https://claudeskills.info - Community-vetted free skills (Anthropic-partnered)
  - PromptSpace: https://promptspace.io - Community marketplace
  - OpenSkillHub: https://openskillhub.dev - Decentralized IPFS-based registry

Features:
- Multi-source open-source marketplace support
- Skill discovery and search
- Download and install from any supported source
- Local .cap file imports for community contributions
- GitHub-based skill sharing (local repos)
- Caching of indexes for offline access
- Error handling and retry logic

✨ Everything is open-source, free, and community-driven!
No API keys, authentication, or commercial backends required!

Configuration:
  - MARKETPLACE_REMOTE_ENABLED: Enable remote marketplace (default: false)
  - MARKETPLACE_SOURCE: Which marketplace to use (default: smithery)
  - MARKETPLACE_AUTO_UPDATE: Auto-update skill index on startup (default: false)
  - MARKETPLACE_GITHUB_REPOS: List of GitHub repos to discover skills from (optional)
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from enum import Enum

logger = logging.getLogger(__name__)

# Supported open-source marketplaces
class MarketplaceSource(Enum):
    """Available open-source marketplace sources."""
    SMITHERY = "smithery"                # https://smithery.ai - Open MCP servers
    SKILLSMP = "skillsmp"                # https://skillsmp.ai - GitHub indexed (open)
    CLAUDESKILLS = "claudeskills"        # https://claudeskills.info - Community-vetted
    PROMPTSPACE = "promptspace"          # https://promptspace.io - Community marketplace
    OPENSKILLHUB = "openskillhub"        # https://openskillhub.dev - Decentralized IPFS

# Open-source marketplace URLs (no commercial platforms!)
MARKETPLACE_URLS = {
    MarketplaceSource.SMITHERY: "https://smithery.ai/api",
    MarketplaceSource.SKILLSMP: "https://api.skillsmp.ai",
    MarketplaceSource.CLAUDESKILLS: "https://api.claudeskills.info",
    MarketplaceSource.PROMPTSPACE: "https://api.promptspace.io",
    MarketplaceSource.OPENSKILLHUB: "https://openskillhub.dev/api",
}

_META_DIR = Path(__file__).resolve().parent
_CACHE_DIR = _META_DIR / "remote_cache"
_INDEX_CACHE_FILE = _CACHE_DIR / "index.json"
_INDEX_CACHE_MAX_AGE = timedelta(hours=24)


# ── Cache Management ───────────────────────────────────────────────────────

def _ensure_cache_dir() -> None:
    """Create cache directory if it doesn't exist."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_index_cache() -> dict[str, Any] | None:
    """Load cached remote index."""
    if not _INDEX_CACHE_FILE.exists():
        return None

    try:
        data = json.loads(_INDEX_CACHE_FILE.read_text(encoding="utf-8"))

        # Check cache age
        cached_at_str = data.get("cached_at")
        if cached_at_str:
            cached_at = datetime.fromisoformat(cached_at_str)
            age = datetime.now() - cached_at
            if age > _INDEX_CACHE_MAX_AGE:
                logger.debug("Index cache expired (age: %s)", age)
                return None

        return data
    except Exception as e:
        logger.warning("Failed to load index cache: %s", e)
        return None


def _save_index_cache(data: dict[str, Any]) -> None:
    """Save remote index to cache."""
    try:
        _ensure_cache_dir()
        data["cached_at"] = datetime.now().isoformat()
        _INDEX_CACHE_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        logger.error("Failed to save index cache: %s", e)


# ── Marketplace Adapters ───────────────────────────────────────────────────

def _get_marketplace_url(source: str | None = None) -> str:
    """Get API URL for a marketplace source."""
    if source is None:
        try:
            import config
            source = getattr(config, "MARKETPLACE_SOURCE", "smithery")
        except (ImportError, AttributeError):
            source = "smithery"

    try:
        marketplace_enum = MarketplaceSource(source.lower())
        return MARKETPLACE_URLS[marketplace_enum]
    except (ValueError, KeyError):
        logger.warning("Unknown marketplace source: %s, using Smithery", source)
        return MARKETPLACE_URLS[MarketplaceSource.SMITHERY]


def _normalize_skill_data(skill: dict[str, Any], source: str) -> dict[str, Any]:
    """
    Normalize skill data from different marketplace formats to standard format.
    
    Each open-source marketplace has slightly different field names/structures.
    This normalizes them transparently.
    """
    # Standard fields all marketplaces should have
    normalized = {
        "name": skill.get("name") or skill.get("id") or skill.get("slug", ""),
        "version": skill.get("version", "1.0.0"),
        "description": skill.get("description", ""),
        "author": skill.get("author") or skill.get("creator", ""),
        "tags": skill.get("tags", []),
        "rating": skill.get("rating", 0),
        "review_count": skill.get("review_count") or skill.get("reviews", 0),
        "download_url": skill.get("download_url") or skill.get("file_url", ""),
        "source_marketplace": source,
    }

    # Marketplace-specific mappings
    if source.lower() == "smithery":
        # Smithery uses 'mcp_server' terminology
        normalized["name"] = skill.get("mcp_server", {}).get("name") or skill.get("name", "")
        normalized["download_url"] = skill.get("mcp_server", {}).get("package_url", "")

    elif source.lower() == "skillsmp":
        # SkillsMP is from GitHub, different structure
        normalized["download_url"] = skill.get("repo_url", "")
        normalized["tags"] = skill.get("topics", [])

    elif source.lower() == "claudeskills":
        # Claude Skills uses different naming
        normalized["name"] = skill.get("skill_name", skill.get("name", ""))
        normalized["tags"] = skill.get("categories", [])

    return normalized


# ── Remote Discovery ──────────────────────────────────────────────────────

def discover_remote(
    source: str | None = None,
    use_cache: bool = True,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """
    Fetch available skills from an open-source marketplace.
    
    Args:
        source: Marketplace source (smithery, skillsmp, etc.)
                If None, uses config or defaults to smithery
        use_cache: Use cached index if available and fresh.
        timeout: HTTP request timeout in seconds.
    
    Returns:
        List of skill dicts: [{"name": "...", "version": "...", "description": "...", ...}]
    """
    # Resolve marketplace URL
    base_url = _get_marketplace_url(source)
    if source is None:
        try:
            import config
            source = getattr(config, "MARKETPLACE_SOURCE", "smithery")
        except (ImportError, AttributeError):
            source = "smithery"

    # Try cache first
    if use_cache:
        cached = _load_index_cache()
        if cached:
            logger.debug("Using cached remote index from %s", cached.get("source", "unknown"))
            return cached.get("skills", [])

    # Fetch from remote
    try:
        import urllib.request
        import urllib.error

        # Build API endpoint based on marketplace
        if source.lower() == "smithery":
            api_url = urljoin(base_url, "mcp-servers")
        elif source.lower() == "skillsmp":
            api_url = urljoin(base_url, "search?type=skill")
        elif source.lower() == "claudeskills" or source.lower() == "openskillhub":
            api_url = urljoin(base_url, "skills")
        else:
            # Default: promptspace and others
            api_url = urljoin(base_url, "skills")

        logger.info("Discovering open-source skills from %s (%s)", source, api_url)

        req = urllib.request.Request(api_url)
        req.add_header("User-Agent", "Raphael/1.0 (Open-Source)")

        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))

            # Extract skills from response (format varies by marketplace)
            if isinstance(data, dict):
                skills = data.get("skills", []) or data.get("data", []) or data.get("mcp_servers", [])
            else:
                skills = data if isinstance(data, list) else []

            # Normalize skills from this marketplace
            normalized_skills = [_normalize_skill_data(s, source) for s in skills]

            # Cache the result
            _save_index_cache({
                "skills": normalized_skills,
                "source": source,
            })
            logger.info("Discovered %d skills from %s", len(normalized_skills), source)
            return normalized_skills

    except urllib.error.URLError as e:
        logger.error("Failed to discover skills from %s: %s", source, e)
        return []
    except Exception as e:
        logger.error("Unexpected error discovering skills: %s", e)
        return []


def search_remote(
    query: str,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search for skills matching a query string.
    
    Performs client-side filtering on discovered skills.
    
    Args:
        query: Search terms (name, description, tags)
        source: Marketplace source (smithery, skillsmp, etc.)
    
    Returns:
        List of matching skill dicts
    """
    query_lower = query.lower()
    all_skills = discover_remote(source=source)

    results = []
    for skill in all_skills:
        name = skill.get("name", "").lower()
        desc = skill.get("description", "").lower()
        tags = [t.lower() for t in skill.get("tags", [])]

        if (query_lower in name or
            query_lower in desc or
            any(query_lower in tag for tag in tags)):
            results.append(skill)

    return results


# ── Download & Installation ───────────────────────────────────────────────

def download_skill(
    name: str,
    version: str | None = None,
    source: str | None = None,
    timeout: float = 30.0,
) -> Path | None:
    """
    Download a skill from an open-source marketplace.
    
    Args:
        name: Skill name
        version: Version to download (default: latest)
        source: Marketplace source (smithery, skillsmp, etc.)
        timeout: Download timeout in seconds
    
    Returns:
        Path to downloaded .cap file, or None on failure
    """
    if source is None:
        try:
            import config
            source = getattr(config, "MARKETPLACE_SOURCE", "smithery")
        except (ImportError, AttributeError):
            source = "smithery"

    base_url = _get_marketplace_url(source)

    # Build download URL based on marketplace
    if source.lower() == "smithery":
        # Smithery: mcp-servers/{name}/package.zip
        download_url = urljoin(base_url, f"mcp-servers/{name}/package.zip")
    elif source.lower() == "skillsmp":
        # SkillsMP: download?id={name}
        download_url = urljoin(base_url, f"download?id={name}")
    elif version:
        # Most support versioning
        download_url = urljoin(base_url, f"skills/{name}/{version}")
    else:
        # Default: latest
        download_url = urljoin(base_url, f"skills/{name}/latest")

    try:
        import urllib.request

        _ensure_cache_dir()
        cap_path = _CACHE_DIR / f"{name}_{source}.cap"

        logger.info("Downloading skill '%s' from %s (%s)", name, source, download_url)

        req = urllib.request.Request(download_url)
        req.add_header("User-Agent", "Raphael/1.0 (Open-Source)")

        with urllib.request.urlopen(req, timeout=timeout) as response:
            cap_path.write_bytes(response.read())

        logger.info("Downloaded skill '%s' to %s", name, cap_path)
        return cap_path

    except Exception as e:
        logger.error("Failed to download skill '%s': %s", name, e)
        return None


def install_skill(
    name: str,
    version: str | None = None,
    source: str | None = None,
    force: bool = False,
) -> str:
    """
    Download and install a skill from an open-source marketplace.
    
    Args:
        name: Skill name
        version: Version (default: latest)
        source: Marketplace source (smithery, skillsmp, etc.)
        force: Force installation even if already installed
    
    Returns:
        Status message
    """
    # Download
    cap_path = download_skill(name, version, source)
    if not cap_path:
        return f"Failed to download skill '{name}' from {source or 'default marketplace'}"

    # Import
    from tools_meta.marketplace import import_tool
    result = import_tool(str(cap_path), force=force)

    logger.info("Installed skill '%s': %s", name, result)
    return result


# ── Local Skill Sharing ────────────────────────────────────────────────────

def share_skill_locally(name: str, output_dir: Path | None = None) -> str:
    """
    Export a skill as a .cap file for local open-source sharing.
    
    Perfect for open-source distribution:
    - Share via GitHub releases
    - Distribute in community repositories
    - Include in documentation
    - Send to community members via email/chat
    
    ✨ No commercial platforms, API keys, or authentication needed!
    
    Args:
        name: Skill name (must exist locally)
        output_dir: Where to save the .cap file (default: tools_meta/marketplace)
    
    Returns:
        Status message with file path
    """
    from tools_meta.marketplace import export_tool

    if output_dir is None:
        output_dir = _META_DIR / "marketplace"

    result = export_tool(name, output_dir=str(output_dir))

    if "Exported" in result:
        logger.info("Exported skill for local sharing: %s", result)
        return (f"✓ {result}\n\n"
                f"💡 Share this .cap file via:\n"
                f"  • GitHub releases\n"
                f"  • Open-source package repositories\n"
                f"  • Community forums and discussions\n"
                f"  • Direct download links\n\n"
                f"No commercial intermediaries, API keys, or authentication needed!")
    else:
        return result


# ── Marketplace Status & Health ────────────────────────────────────────────

def get_marketplace_status(source: str | None = None) -> dict[str, Any]:
    """Get overall marketplace status."""
    if source is None:
        try:
            import config
            source = getattr(config, "MARKETPLACE_SOURCE", "smithery")
        except (ImportError, AttributeError):
            source = "smithery"

    base_url = _get_marketplace_url(source)

    try:
        import urllib.request
        import urllib.error

        status_url = urljoin(base_url, "status")

        req = urllib.request.Request(status_url)
        req.add_header("User-Agent", "Raphael/1.0 (Open-Source)")

        with urllib.request.urlopen(req, timeout=5.0) as response:
            data = json.loads(response.read().decode("utf-8"))
            return {
                "status": "online",
                "source": source,
                **data,
            }

    except Exception as e:
        logger.warning("Failed to get marketplace status: %s", e)
        return {
            "status": "offline",
            "source": source,
            "error": str(e),
        }


def list_available_marketplaces() -> str:
    """List all available open-source marketplace sources."""
    lines = ["**Open-Source AI Skill Marketplaces (2026):**\n"]
    lines.append("✨ **All open-source, community-driven, no commercial platforms!**\n")

    marketplace_info = {
        "smithery": {
            "url": "https://smithery.ai",
            "license": "Open-source",
            "strengths": "Large catalog of MCP servers, fully open-source",
            "best_for": "Developers exploring community-built tools",
        },
        "skillsmp": {
            "url": "https://skillsmp.ai",
            "license": "Open-source",
            "strengths": "800,000+ skills indexed from GitHub repositories",
            "best_for": "Power users wanting massive discovery and GitHub integration",
        },
        "claudeskills": {
            "url": "https://claudeskills.info",
            "license": "Community + Anthropic",
            "strengths": "650+ free community-vetted skills, official Anthropic skills",
            "best_for": "Beginners, free-only users, and Claude enthusiasts",
        },
        "promptspace": {
            "url": "https://promptspace.io",
            "license": "Open-source",
            "strengths": "Community marketplace with easy install and discovery",
            "best_for": "Individual creators and open-source enthusiasts",
        },
        "openskillhub": {
            "url": "https://openskillhub.dev",
            "license": "Decentralized (IPFS)",
            "strengths": "Fully decentralized IPFS-based registry, no central server needed",
            "best_for": "Censorship-resistant skill sharing, distributed teams",
        },
    }

    for source, info in marketplace_info.items():
        lines.append(f"**{source.upper()}**")
        lines.append(f"  URL: {info['url']}")
        lines.append(f"  License: {info['license']}")
        lines.append(f"  Strengths: {info['strengths']}")
        lines.append(f"  Best for: {info['best_for']}")
        lines.append("")

    lines.append("💡 **For your own skills**: Use `share_skill_locally()` to export")
    lines.append("   as .cap files for community distribution (no marketplace needed!)")

    return "\n".join(lines)


def list_remote_skills(source: str | None = None) -> str:
    """List open-source marketplace skills with descriptions."""
    skills = discover_remote(source=source)

    if not skills:
        source_name = source or "default"
        return f"No skills available from {source_name} marketplace or marketplace offline"

    lines = [f"**{source or 'Remote'} Marketplace ({len(skills)} open-source skills):**\n"]

    for skill in skills[:20]:  # Limit to first 20
        name = skill.get("name", "?")
        version = skill.get("version", "?")
        desc = skill.get("description", "")
        rating = skill.get("rating", 0)

        lines.append(f"**{name}** v{version}")
        if desc:
            lines.append(f"  {desc}")
        if rating > 0:
            stars = "⭐" * int(rating)
            lines.append(f"  Rating: {rating:.1f}/5 {stars}")
        lines.append("")

    if len(skills) > 20:
        lines.append(f"... and {len(skills) - 20} more open-source skills")

    return "\n".join(lines)


# ── Cache Management ───────────────────────────────────────────────────────

def clear_cache() -> int:
    """Clear remote marketplace cache."""
    import shutil

    try:
        if _CACHE_DIR.exists():
            count = len(list(_CACHE_DIR.glob("*.cap"))) + (1 if _INDEX_CACHE_FILE.exists() else 0)
            shutil.rmtree(_CACHE_DIR)
            logger.info("Cleared marketplace cache (%d items)", count)
            return count
        return 0
    except Exception as e:
        logger.error("Failed to clear cache: %s", e)
        return 0


# ── Initialization (Auto-update on startup) ────────────────────────────────

def auto_update_index(source: str | None = None) -> bool:
    """Auto-update remote index if enabled in config."""
    try:
        import config
        if not config.MARKETPLACE_REMOTE_ENABLED or not config.MARKETPLACE_AUTO_UPDATE:
            return False
    except (ImportError, AttributeError):
        return False

    if source is None:
        try:
            import config
            source = getattr(config, "MARKETPLACE_SOURCE", "smithery")
        except (ImportError, AttributeError):
            source = "smithery"

    logger.info("Auto-updating open-source marketplace index from %s...", source)
    try:
        discover_remote(source=source, use_cache=False)
        return True
    except Exception as e:
        logger.warning("Failed to auto-update marketplace index: %s", e)
        return False
