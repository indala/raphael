# Raphael Marketplace Integration Guide

Raphael supports 7+ major AI skill marketplaces. You can discover, download, and install skills from any of them.

---

## Available Marketplaces (2026)

| Marketplace | Strengths | Best For |
|---|---|---|
| **SkillExchange** | MCP + A2A protocol, 85% revenue share, enterprise compliance | Professionals & enterprises |
| **Smithery** | Large catalog of MCP servers, free to use | Developers exploring free tools |
| **Agensi** | Curated catalog, 8-point security scan, 80/20 payments | Teams needing vetted skills |
| **PromptSpace** | Wide coverage, easy install, community marketplace | Individuals & hobbyists |
| **Skills.sh** | CLI installer (npx), large catalog, community-driven | npm-style skill management |
| **SkillsMP** | 800,000+ skills indexed, massive discovery | Power users wanting breadth |
| **ClaudeSkills** | 650+ free skills, community-vetted, Anthropic official | Beginners & free-only users |

---

## Quick Start

### 1. Enable Remote Marketplace

```python
# In config.py or settings.toml
MARKETPLACE_REMOTE_ENABLED = True
MARKETPLACE_SOURCE = "skillexchange"  # or smithery, agensi, etc.
```

### 2. Discover Skills

```python
from tools_meta.remote_marketplace import discover_remote, list_remote_skills

# Discover all skills from SkillExchange
skills = discover_remote(source="skillexchange")
print(skills)

# Or get a nice listing
print(list_remote_skills(source="skillexchange"))
```

### 3. Search Skills

```python
from tools_meta.remote_marketplace import search_remote

# Search for weather-related skills
weather_skills = search_remote("weather", source="smithery")
for skill in weather_skills:
    print(f"{skill['name']} - {skill['description']}")
```

### 4. Install a Skill

```python
from tools_meta.remote_marketplace import install_skill

# Install from SkillExchange
result = install_skill("weather_tool", source="skillexchange")
print(result)

# Install from Smithery
result = install_skill("mcp_fetch", version="latest", source="smithery")
print(result)
```

---

## Configuration

### Environment Variables

```bash
# Enable remote marketplace
export MARKETPLACE_REMOTE_ENABLED=true

# Choose your marketplace
export MARKETPLACE_SOURCE=skillexchange
# Options: skillexchange, smithery, agensi, promptspace, skills_sh, skillsmp, claudeskills

# Auto-update skill index on startup
export MARKETPLACE_AUTO_UPDATE=true
```

### Settings File (~/.raphael/settings.toml)

```toml
[marketplace]
remote_enabled = true
source = "smithery"  # or your preferred marketplace
auto_update = false
```

---

## Usage Examples

### Example 1: Browse All Marketplaces

```python
from tools_meta.remote_marketplace import list_available_marketplaces
print(list_available_marketplaces())
```

Output:
```
**Available AI Skill Marketplaces (2026):**

**SKILLEXCHANGE** (https://skill-exchange.io)
  Strengths: MCP + A2A protocol, 85% revenue share, enterprise compliance
  Best for: Professionals & enterprises

**SMITHERY** (https://smithery.ai)
  Strengths: Large catalog of MCP servers, free to use
  Best for: Developers exploring free tools
  
...
```

### Example 2: Find and Install Skills

```python
from tools_meta.remote_marketplace import search_remote, install_skill

# Search for skills
results = search_remote("http", source="agensi")
if results:
    first_skill = results[0]
    print(f"Found: {first_skill['name']}")
    
    # Install it
    result = install_skill(first_skill['name'], source="agensi")
    print(result)
```

### Example 3: Compare Multiple Marketplaces

```python
from tools_meta.remote_marketplace import search_remote

# Search the same query across different marketplaces
for marketplace in ["skillexchange", "smithery", "agensi"]:
    skills = search_remote("api", source=marketplace)
    print(f"{marketplace}: {len(skills)} matching skills")
```

### Example 4: Marketplace Health Check

```python
from tools_meta.remote_marketplace import get_marketplace_status

status = get_marketplace_status(source="skillexchange")
if status['status'] == 'online':
    print("✓ SkillExchange is online")
    print(f"  Skills available: {status.get('skills_count', 'unknown')}")
else:
    print("✗ SkillExchange is offline")
```

### Example 5: Local + Remote Workflow

```python
from tools_meta.marketplace import list_marketplace, rate_skill
from tools_meta.remote_marketplace import install_skill

# 1. Rate your local skills
rate_skill("my_weather_tool", 5, "Works great!")

# 2. List what you have locally
print(list_marketplace(with_ratings=True))

# 3. Find and install new skills from remote
result = install_skill("advanced_weather", source="skillexchange")
print(result)

# 4. List again to see the new skill
print(list_marketplace())
```

---

## Advanced Usage

### Custom Marketplace URL

If you have a self-hosted marketplace:

```python
# You can modify the marketplace URL in remote_marketplace.py
# Or fork the project and add a new marketplace adapter

# For now, use the built-in sources or disable remote:
MARKETPLACE_REMOTE_ENABLED = False
```

### Offline Mode

```python
# Download skills once, then work offline
from tools_meta.remote_marketplace import discover_remote

# Download and cache
skills = discover_remote(source="claudeskills", use_cache=False)

# Now works offline with cached data
skills_cached = discover_remote(use_cache=True)

# Later, update cache when online
discover_remote(use_cache=False)
```

### Bulk Installation

```python
from tools_meta.remote_marketplace import search_remote, install_skill

# Install all weather-related skills
skills = search_remote("weather", source="skillexchange")
for skill in skills[:5]:  # Limit to first 5
    result = install_skill(skill['name'], source="skillexchange")
    print(f"Installed: {skill['name']}")
```

---

## Troubleshooting

### Marketplace Offline

```python
from tools_meta.remote_marketplace import get_marketplace_status

status = get_marketplace_status(source="smithery")
if status['status'] == 'offline':
    # Fall back to local marketplace
    from tools_meta.marketplace import list_marketplace
    print(list_marketplace())
```

### Clear Cache

```python
from tools_meta.remote_marketplace import clear_cache

# Clear cached skills
count = clear_cache()
print(f"Cleared {count} items from cache")
```

### No Skills Found

```python
# Try a different marketplace
from tools_meta.remote_marketplace import search_remote

for source in ["skillexchange", "smithery", "agensi"]:
    results = search_remote("your_query", source=source)
    if results:
        print(f"Found {len(results)} in {source}")
        break
```

---

## FAQ

**Q: Which marketplace should I use?**
A: 
- **Professionals**: Use SkillExchange (vetted, revenue share)
- **Free**: Use Smithery or ClaudeSkills
- **Large selection**: Use SkillsMP (800K+ skills)
- **Curated**: Use Agensi (8-point security scan)

**Q: Can I switch marketplaces?**
A: Yes! Just change `MARKETPLACE_SOURCE` or call functions with `source` parameter.

**Q: Do I need an API key?**
A: Most marketplaces are free. API keys only needed for publishing (enterprise features).

**Q: Is my data private?**
A: Yes. Raphael only downloads skills locally. No tracking of your usage.

**Q: What if a marketplace goes offline?**
A: Raphael falls back to cached data. Always works offline with previously downloaded skills.

**Q: Can I use multiple marketplaces?**
A: Yes! Search/install from different marketplaces in the same session.

---

## Integration with Your Workflow

### In Orchestrator

```python
# In orchestrator/core.py
if config.MARKETPLACE_REMOTE_ENABLED:
    from tools_meta.remote_marketplace import auto_update_index
    auto_update_index()  # Refreshes skill index on startup
```

### In CLI

```bash
# Discover skills
raphael marketplace discover --source skillexchange

# Install skill
raphael marketplace install weather_tool --source agensi

# Search
raphael marketplace search "api" --source smithery

# List available marketplaces
raphael marketplace list
```

---

## What's Next?

- [ ] Publish your own skills to marketplaces
- [ ] Create skill bundles (multiple related skills)
- [ ] Rate and review skills you've used
- [ ] Set up automated skill updates
- [ ] Join the Raphael community marketplace

Enjoy discovering and installing skills! 🚀
