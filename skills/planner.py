"""
Planner Skill — decomposes complex requests into structured step-by-step plans.

Uses an LLM call (no tools) to analyze a request and produce
a numbered plan. The executor agent then executes each step.
"""

import json
import logging
from skills import register
from skills.base_skill import Skill

logger = logging.getLogger(__name__)

_PLANNER_PROMPT = """You are a task planner. Analyze the user's request and break it down into
a sequence of concrete, actionable steps. Each step should be a single tool operation.

Respond ONLY with a JSON array of steps. Each step is an object with:
- "action": a brief description of what to do
- "tool": the tool name
- "args": a dict of tool arguments
- "depends_on": list of step indices this step depends on (0-based), or null

Example:
User: "find latest AI news and save to file"
Response:
[
  {"action": "Search for latest AI news", "tool": "web_search", "args": {"query": "latest AI news 2026"}, "depends_on": null},
  {"action": "Fetch top result", "tool": "web_fetch", "args": {"url": "<result-of-step-0>"}, "depends_on": [0]},
  {"action": "Save results to file", "tool": "write_file", "args": {"path": "outputs/ai_news.md", "content": "<result-of-step-1>"}, "depends_on": [1]}
]

Keep plans minimal — 2-5 steps. If the request is simple (1 tool), just return a single step.
"""


@register
class PlannerSkill(Skill):
    name = "planner"
    description = "Break down a complex request into a step-by-step plan"
    required_tools = []

    def execute(self, llm, executor, query: str = "", **kwargs) -> str:
        """Decompose a query into structured steps."""
        messages = [
            {"role": "system", "content": _PLANNER_PROMPT},
            {"role": "user", "content": query},
        ]

        response = llm.chat(messages, reason="planner")
        if not response or not response.content:
            return json.dumps([{"action": f"Process: {query}", "tool": None, "args": {}, "depends_on": None}])

        content = response.content.strip()
        # Extract JSON array from response
        if "[" in content:
            json_start = content.index("[")
            json_end = content.rindex("]") + 1
            content = content[json_start:json_end]

        try:
            steps = json.loads(content)
            if isinstance(steps, list) and len(steps) > 0:
                return content  # type: ignore[no-any-return]
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: wrap entire response as single step
        return json.dumps([{"action": content, "tool": None, "args": {}, "depends_on": None}])
