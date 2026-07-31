"""
ToolAudit — boot-time integrity checks for the Raphael tool system.

Runs cheap, read-only checks at startup and logs warnings so the system
prompt can never drift from the actual tool registry:

1. Phantom references — tool names mentioned in the domain maps, core
   fallback set, or the system prompt that are NOT registered. The model
   would try to call a non-existent tool.
2. Unreachable tools — registered tools never exposed in any domain map,
   core fallback set, or the prompt tool guide. The model can never learn
   about them.
3. Weak descriptions — registered tools whose description is too short for
   the model to understand what the tool does and when to use it.

`audit_tool_registry()` never raises: a broken tool module is reported as a
warning so it can't crash startup.
"""

import logging
import re

from orchestrator.prompt_builder import SystemPromptBuilder
from orchestrator.tools import get_tool_map, get_tool_schemas
from orchestrator.tool_orchestrator import CORE_FALLBACK_TOOLS, DOMAIN_TOOL_MAP

logger = logging.getLogger(__name__)

# Minimum description length before we warn that a tool is hard to understand.
MIN_DESCRIPTION_LENGTH = 60

# Prose identifiers in the system prompt that look like snake_case tool names
# but are not tools (e.g. parameter names). Keep this list explicit so the
# prompt-reference check never produces noise.
_PROMPT_NON_TOOL_IDENTIFIERS = frozenset({"task_id"})

_SNAKE_CASE_RE = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b")


def _prompt_referenced_tools() -> set[str]:
    """Extract snake_case identifiers from the rendered system prompt.

    These are the tool names the model actually sees, minus known
    non-tool prose identifiers. Rendering the real prompt (rather than
    parsing source) keeps this honest when sections are added or removed.
    """
    prompt = SystemPromptBuilder.build(
        date_str="1970-01-01",
        time_str="00:00:00",
        spk_ok=True,
        tts_ok=True,
        mic_ok=True,
        memory_context="",
        raphael_context="",
        screenshot_dir="outputs",
    )
    return set(_SNAKE_CASE_RE.findall(prompt)) - _PROMPT_NON_TOOL_IDENTIFIERS


def audit_tool_registry() -> list[str]:
    """Return a list of tool-system integrity warnings.

    An empty list means the registry is healthy. Every warning is a
    human-actionable message, e.g. "PHANTOM TOOL: ..." or
    "UNREACHABLE TOOL: ...".
    """
    warnings: list[str] = []

    try:
        registered = set(get_tool_map())
    except Exception as e:  # pragma: no cover - defensive boot path
        return [f"Tool registry unreachable: {e}"]

    all_schemas = get_tool_schemas()
    schema_names = {s["function"]["name"] for s in all_schemas}
    # get_tool_map() can include names without a schema; the model only ever
    # sees schema-backed tools, so those count as unregistered.
    registered = {n for n in registered if n in schema_names}

    # 1. Phantom names in domain maps / core fallback
    for domain, names in DOMAIN_TOOL_MAP.items():
        for name in names:
            if name not in registered:
                warnings.append(
                    f"PHANTOM TOOL: '{name}' is listed in domain "
                    f"'{domain.value}' but is not registered. Remove it or "
                    "register a tool with that name."
                )
    for name in CORE_FALLBACK_TOOLS:
        if name not in registered:
            warnings.append(
                f"PHANTOM TOOL: '{name}' is in CORE_FALLBACK_TOOLS but is "
                "not registered. Remove it or register a tool with that name."
            )

    # 2. Unreachable tools
    exposed = set()
    for names in DOMAIN_TOOL_MAP.values():
        exposed.update(names)
    exposed.update(CORE_FALLBACK_TOOLS)
    exposed.update(_prompt_referenced_tools())
    for name in sorted(registered - exposed):
        warnings.append(
            f"UNREACHABLE TOOL: '{name}' is registered but never exposed in "
            "any domain map, core fallback, or the prompt tool guide. The "
            "model can never call it."
        )

    # 3. Prompt-referenced but unregistered
    for name in sorted(_prompt_referenced_tools() - registered):
        warnings.append(
            f"PROMPT REFERENCES UNREGISTERED TOOL: '{name}' appears in the "
            "system prompt but is not registered. Fix the reference or "
            "register the tool."
        )

    # 4. Weak descriptions
    for s in all_schemas:
        name = s["function"]["name"]
        desc = s["function"].get("description", "")
        if len(desc) < MIN_DESCRIPTION_LENGTH:
            warnings.append(
                f"WEAK DESCRIPTION: '{name}' description is only "
                f"{len(desc)} chars (< {MIN_DESCRIPTION_LENGTH}). Add a "
                "clear description of what it does and when to use it."
            )

    return warnings


def run_boot_audit() -> None:
    """Log all registry integrity warnings at startup."""
    warnings = audit_tool_registry()
    if not warnings:
        logger.info("Tool audit: registry healthy (%d tools)", len(get_tool_map()))
        return
    logger.warning("Tool audit: %d issue(s) found", len(warnings))
    for warning in warnings:
        logger.warning("Tool audit: %s", warning)
