# Marketplace Update: Multi-Source Support

## What Changed?

The remote marketplace now supports **7 major AI skill marketplaces** instead of just one hardcoded URL.

### Files Updated

1. **tools_meta/remote_marketplace.py** - Complete refactor
   - Added `MarketplaceSource` enum for all supported sources
   - Added `MARKETPLACE_URLS` dictionary with API endpoints
   - Added `_normalize_skill_data()` to handle different marketplace formats
   - Updated all functions to use `source` parameter instead of `index_url`
   - Added `list_available_marketplaces()` function
   - Each marketplace has different API structure, all normalized to standard format

2. **config.py** - New settings
   - `MARKETPLACE_SOURCE` - Which marketplace to use (default: skillexchange)
   - `MARKETPLACE_REMOTE_ENABLED` - Enable/disable remote (default: false)
   - `MARKETPLACE_AUTO_UPDATE` - Auto-update on startup (default: false)

### Migration Guide

**Old code:**
```python
from tools_meta.remote_marketplace import discover_remote
skills = discover_remote(index_url="https://marketplace.raphael.ai/api")
```

**New code:**
```python
from tools_meta.remote_marketplace import discover_remote
skills = discover_remote(source="skillexchange")  # or smithery, agensi, etc.
```

All functions updated:
- `discover_remote(source=...)` - instead of `index_url`
- `download_skill(name, source=...)` - instead of `index_url`
- `install_skill(name, source=...)` - instead of `index_url`
- `search_remote(query, source=...)` - instead of `index_url`

### New Features

1. **Built-in Marketplace Support**
   - SkillExchange (enterprise-focused)
   - Smithery (MCP servers)
   - Agensi (curated, security-focused)
   - PromptSpace (community)
   - Skills.sh (CLI-style)
   - SkillsMP (massive catalog)
   - ClaudeSkills (Anthropic official)

2. **Marketplace Normalization**
   - Each marketplace has different field names/formats
   - `_normalize_skill_data()` converts to standard format
   - Transparent to the user

3. **Marketplace Discovery**
   - `list_available_marketplaces()` - Show all options
   - Each shows strengths, best use case, URL

### Configuration

**Environment variables:**
```bash
export MARKETPLACE_REMOTE_ENABLED=true
export MARKETPLACE_SOURCE=smithery
export MARKETPLACE_AUTO_UPDATE=true
```

**Settings file (~/.raphael/settings.toml):**
```toml
[marketplace]
remote_enabled = true
source = "agensi"
auto_update = false
```

### Backward Compatibility

❌ **Breaking change**: `index_url` parameter is now `source`

If you were using custom URLs, you have these options:

1. **Use a built-in marketplace** (recommended)
   ```python
   discover_remote(source="skillexchange")
   ```

2. **Disable remote, use local only**
   ```python
   # In config.py
   MARKETPLACE_REMOTE_ENABLED = False
   ```

3. **Host your own marketplace server** and modify `MARKETPLACE_URLS` in remote_marketplace.py

### Examples

**Discover from Smithery:**
```python
from tools_meta.remote_marketplace import discover_remote
skills = discover_remote(source="smithery")
```

**Search across Agensi:**
```python
from tools_meta.remote_marketplace import search_remote
results = search_remote("weather", source="agensi")
```

**Install from ClaudeSkills:**
```python
from tools_meta.remote_marketplace import install_skill
result = install_skill("sentiment_analyzer", source="claudeskills")
```

**Check marketplace status:**
```python
from tools_meta.remote_marketplace import get_marketplace_status
status = get_marketplace_status(source="skillexchange")
print(status)
```

### Documentation

See **MARKETPLACE_GUIDE.md** for complete examples and troubleshooting.

### Testing

All new marketplace adapters need testing. The test suite in `tests/test_marketplace.py` includes:
- Mock marketplace responses
- Normalization of different formats
- Error handling for offline marketplaces
- Cache expiry and fallback

### Future Enhancements

- [ ] Custom marketplace URL support (self-hosted)
- [ ] Marketplace comparison (search same query across all)
- [ ] Automatic fallback on error (try next marketplace)
- [ ] Skill rating sync across marketplaces
- [ ] Marketplace preferences UI

---

**TL;DR**: Instead of hardcoding one marketplace URL, Raphael now supports 7 major marketplaces. Use `source` parameter or config to choose which one. Falls back to local marketplace if remote is down.
