"""
Task Executor Skill — executes multi-step plans using available tools.

Takes a JSON plan from the Planner skill and executes each step
with DAG-based parallelism: independent steps run concurrently
while respecting dependency ordering.
"""

import json
import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import ClassVar

from skills import register
from skills.base_skill import Skill

logger = logging.getLogger(__name__)


def _topological_sort(steps: list[dict]) -> list[list[int]]:
    """Group step indices into dependency layers (topological order).

    Returns a list of layers, where each layer is a list of step indices
    that can be executed in parallel (all dependencies satisfied from
    earlier layers).
    """
    n = len(steps)
    in_degree = [0] * n
    deps_of: list[set[int]] = [set() for _ in range(n)]

    # Build dependency graph
    for i, step in enumerate(steps):
        depends = step.get("depends_on")
        if depends:
            for d in depends:
                d_int = int(d)
                if 0 <= d_int < n:
                    deps_of[d_int].add(i)
                    in_degree[i] += 1

    # Kahn's algorithm: group by layer
    queue = deque(i for i in range(n) if in_degree[i] == 0)
    layers = []
    while queue:
        layer = list(queue)
        layers.append(layer)
        for _ in range(len(queue)):
            node = queue.popleft()
            for dep in deps_of[node]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

    # If any nodes remain, they have a cycle or unreachable deps — append them
    remaining = [i for i in range(n) if in_degree[i] > 0]
    if remaining:
        layers.append(remaining)

    return layers


@register
class TaskExecutorSkill(Skill):
    name = "task_executor"
    description = "Execute a step-by-step plan using available tools"
    required_tools: ClassVar[list[str]] = []  # Dynamic — depends on the plan

    def execute(self, llm, executor, plan_json: str = "", **kwargs) -> str:  # noqa: ARG002
        """Execute a JSON plan with DAG-based parallel execution."""
        try:
            steps = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
        except (json.JSONDecodeError, TypeError):
            return f"Invalid plan: {plan_json}"

        if not isinstance(steps, list):
            steps = [steps]

        if not steps:
            return "Empty plan."

        layers = _topological_sort(steps)
        results: dict[str, str] = {}
        output_lines: list[str] = []
        step_index = 0  # monotonic counter for display

        for layer in layers:
            # Resolve dependencies and execute each step in this layer
            def run_step(i: int) -> tuple[int, str]:
                step = steps[i]
                action = step.get("action", f"Step {i}")
                tool_name = step.get("tool")
                args = dict(step.get("args", {}) or {})
                depends_on = step.get("depends_on")

                # Substitute previous results into args
                if depends_on:
                    for dep_idx in depends_on:
                        dep_result = results.get(str(dep_idx), "")
                        for key, val in args.items():
                            if isinstance(val, str):
                                placeholder = f"<result-of-step-{dep_idx}>"
                                if placeholder in val:
                                    args[key] = val.replace(placeholder, dep_result[:2000])

                if tool_name and tool_name != "null":
                    logger.info("Executor step %d: %s(%s)", i, tool_name, args)
                    result = executor.execute(tool_name, args)
                    # Truncate for display
                    preview = result[:300] + "..." if len(result) > 300 else result
                    return i, f"Step {step_index + 1}: {action} → {preview}"
                else:
                    return i, f"Step {step_index + 1}: {action}"

            # Parallel execution within the layer
            with ThreadPoolExecutor(max_workers=min(len(layer), 5)) as pool:
                futures = {pool.submit(run_step, i): i for i in layer}
                for future in as_completed(futures):
                    i, line = future.result()
                    results[str(i)] = line
                    output_lines.append(line)
                    step_index += 1

        return "\n".join(output_lines) if output_lines else "Plan executed."
