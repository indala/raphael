"""
Tool Manager Skill — full lifecycle pipeline for tool creation and management.

Pipeline stages (each a discrete gate):
    DESIGN → GENERATE → VALIDATE → SANDBOX TEST → SELF REVIEW → REGISTER → ACTIVE

Lifecycle operations: Create, Update, Version, Archive, Delete, Merge, Benchmark, Reload, Metadata
"""

import ast
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from skills import register
from skills.base_skill import Skill
import contextlib

logger = logging.getLogger(__name__)

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "orchestrator" / "tools" / "generated" / "production"
_ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "orchestrator" / "tools" / "generated" / "archived"
_DRAFT_DIR = Path(__file__).resolve().parent.parent / "orchestrator" / "tools" / "generated" / "draft"
_SANDBOX_DIR = Path(__file__).resolve().parent.parent / "tools_meta" / "sandbox"
_TESTS_DIR = Path(__file__).resolve().parent.parent / "tests" / "generated"


# ── Design Prompts ─────────────────────────────────────────────────────

_DESIGN_PROMPT = """You are a Tool Architect. Given a user request for a new tool, design its interface.

Output ONLY valid JSON with this structure:
{
  "name": "tool_function_name",
  "description": "Short description of what the tool does",
  "parameters": [
    {"name": "param1", "type": "string", "description": "What this param does", "required": true}
  ],
  "implementation_notes": "How the tool should work internally",
  "dependencies": ["list", "of", "python", "packages"] or []
}

Rules:
- Tool name must be snake_case, descriptive, and NOT start with a number
- Parameters must be strings (tool function receives strings, casts as needed)
- Dependencies must be pip-installable package names or empty
- Keep the design focused on a single responsibility
- No hardcoded API keys — read from os.getenv() or config module
"""

_GENERATION_TEMPLATE = """You are a Tool Generator. Given a tool design, write the complete Python module.

The module MUST follow this exact structure:

```python
\"\"\"
{tool_description}
\"\"\"

import logging

logger = logging.getLogger(__name__)


def {function_name}({params}) -> str:
    \"\"\"{param_docstring}

    Returns:
        Result string.
    \"\"\"
    {implementation}
    return result


def get_schemas() -> list[dict]:
    \"\"\"Return OpenAI function-calling schemas for this tool.\"\"\"
    return [
        {{
            "type": "function",
            "function": {{
                "name": "{function_name}",
                "description": "{description}",
                "parameters": {{
                    "type": "object",
                    "properties": {{
                        {parameters_schema}
                    }},
                    "required": [{required_params}],
                }},
            }},
        }},
    ]
```

RULES:
1. The function MUST return a string (never None, never a complex object)
2. Use ONLY Python standard library + specified dependencies (import them inside the function if optional)
3. The get_schemas() function MUST be present at module level
4. Parameter types MUST be "string" (not "number", "boolean", etc.)
5. Always use try/except and return descriptive error messages as strings
6. API keys must be read from os.getenv() or config module
7. Keep implementation under 80 lines
8. Use f-strings for string formatting
9. No file I/O unless the design explicitly requires it

Generate ONLY the Python code, no explanation.
"""

_REVIEW_PROMPT = """You are a Code Reviewer. Review the following tool implementation for issues.

Check for:
1. **Security**: Does it read config safely? Any injection risks? Hardcoded secrets?
2. **Correctness**: Does the logic match the design? Any edge cases unhandled?
3. **Error handling**: Are all exceptions caught? Do error messages help debugging?
4. **Style**: Does it follow the template? Is get_schemas() present?
5. **Performance**: Any obvious inefficiencies?

Tool Design: {design}
Tool Code: {code}

Output a JSON object:
{{
  "passed": true/false,
  "issues": ["issue1", "issue2"] or [],
  "suggestions": ["suggestion1"] or [],
  "verdict": "PASS" or "MINOR_ISSUES" or "FAIL"
}}

Be strict but fair. Minor style issues = MINOR_ISSUES (still pass).
Logic bugs, security issues, or missing get_schemas() = FAIL.
"""


@register
class ToolManagerSkill(Skill):
    """Full lifecycle pipeline for tool creation and management."""

    name = "tool_manager"
    description = "Design, generate, validate, test, review, and register new tools. Also update, version, archive, delete, merge, benchmark, and manage tool metadata."

    required_tools = [
        "run_system_command", "process_file", "web_search", "web_fetch",
    ]

    # ── Pipeline Stages ──────────────────────────────────────────────────

    def design_tool(self, query: str, llm) -> dict | str:
        """Stage 1: Design tool interface from natural language. Returns design dict or error string."""
        logger.info("ToolManager: designing tool from: %s", query[:80])
        messages = [
            {"role": "system", "content": _DESIGN_PROMPT},
            {"role": "user", "content": query},
        ]
        resp = llm.chat(messages, reason="tool_design")
        if not resp or not resp.content:
            return "Failed to generate tool design."

        text = resp.content.strip()
        # Strip markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            design = json.loads(text)
            # Validate required fields
            for key in ("name", "description", "parameters"):
                if key not in design:
                    return f"Design missing required field: '{key}'"
            return design  # type: ignore[no-any-return]
        except json.JSONDecodeError as e:
            logger.error("ToolManager: failed to parse design JSON: %s", e)
            return f"Failed to parse tool design: {e}"

    def generate_code(self, design: dict, llm) -> str | None:
        """Stage 2: Generate Python code from a design dict. Returns code string or None."""
        logger.info("ToolManager: generating code for '%s'", design["name"])

        func_name = design["name"]
        description = design.get("description", "")
        params = design.get("parameters", [])

        # Build param lists
        param_list = []
        param_docstrings = []
        schema_properties = []
        required_params = []

        for p in params:
            pname = p.get("name", "")
            pdesc = p.get("description", "")
            param_list.append(f"{pname}: str")
            param_docstrings.append(f"    {pname}: {pdesc}")
            schema_properties.append(
                f'"{pname}": {{"type": "string", "description": "{pdesc}"}}'
            )
            if p.get("required", True):
                required_params.append(f'"{pname}"')

        param_str = ", ".join(param_list)
        param_doc = "\n".join(param_docstrings)
        props_str = ",\n                        ".join(schema_properties)
        req_str = ", ".join(required_params)
        deps = design.get("dependencies", [])
        impl_notes = design.get("implementation_notes", "")

        # Build implementation hint
        impl_hint = f"# Implementation: {impl_notes}\n    "
        if deps:
            impl_hint += f"# Dependencies: {', '.join(deps)}\n    "

        # Construct the prompt
        prompt = _GENERATION_TEMPLATE.format(
            tool_description=description,
            function_name=func_name,
            params=param_str,
            param_docstring=param_doc,
            description=description,
            parameters_schema=props_str,
            required_params=req_str,
            implementation=impl_hint + "pass  # TODO: implement",
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Generate the tool '{func_name}' that {description}."},
        ]
        resp = llm.chat(messages, reason="tool_generation")
        if not resp or not resp.content:
            return None
        code = resp.content.strip()
        # Strip markdown fences
        if code.startswith("```"):
            code = code.split("\n", 1)[1]
            if code.endswith("```"):
                code = code[:-3]
            code = code.strip()

        return code  # type: ignore[no-any-return]

    def validate_code(self, name: str, code: str) -> list[str]:
        """Stage 3: Static validation. Returns list of errors (empty = valid)."""
        errors = []

        # 1. Syntax check
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            errors.append(f"Syntax error: {e}")
            return errors  # Can't continue if syntax is broken

        # 2. Check for required function
        has_get_schemas = False
        has_func = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name == "get_schemas":
                    has_get_schemas = True
                elif node.name == name:
                    has_func = True

        if not has_get_schemas:
            errors.append("Missing required 'get_schemas()' function")
        if not has_func:
            errors.append(f"Missing main function '{name}()'")

        # 3. Check for disallowed patterns
        disallowed = ["__import__", "eval(", "exec(", "compile("]
        for pattern in disallowed:
            if pattern in code:
                errors.append(f"Security warning: contains '{pattern}'")

        # 4. Check return-style statements exist in main function body
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
                if not returns:
                    errors.append(f"Function '{name}' has no return statement")

        return errors

    def sandbox_test(self, name: str, code: str, design: dict) -> list[dict]:
        """Stage 4: Run tests in an isolated subprocess. Returns list of test results."""
        results = []

        # Generate test cases from design
        params = design.get("parameters", [])
        test_cases = self._generate_test_cases(name, params)

        # Write code to sandbox
        _SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
        sandbox_file = _SANDBOX_DIR / f"{name}.py"
        try:
            sandbox_file.write_text(code, encoding="utf-8")
        except OSError as e:
            return [{"name": "setup", "passed": False, "detail": f"Failed to write sandbox file: {e}"}]

        # For each test case, run in subprocess
        for tc in test_cases:
            test_name = tc["name"]
            args = tc.get("args", {})
            tc.get("expect", "")

            test_script = f"""
import sys
sys.path.insert(0, r"{_SANDBOX_DIR}")
sys.path.insert(0, r"{_TOOLS_DIR.parent.parent}")
try:
    from {name} import {name} as _test_fn, get_schemas
    # Verify schema exists
    _schemas = get_schemas()
    _schema_ok = len(_schemas) > 0 and _schemas[0]["function"]["name"] == "{name}"
    if not _schema_ok:
        print("SCHEMA_FAIL: get_schemas() did not return valid schema")
    else:
        _result = _test_fn({self._format_args_for_test(args)})
        if _result is None:
            print("RESULT_FAIL: function returned None, expected string")
        else:
            print(f"RESULT_OK: {{_result}}")
except Exception as e:
    import traceback
    print(f"TEST_FAIL: {{e}}")
    traceback.print_exc()
"""
            try:
                proc = subprocess.run(
                    [sys.executable, "-c", test_script],
                    capture_output=True, text=True, timeout=15,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )

                stdout = proc.stdout.strip()
                stderr = proc.stderr.strip()

                if "RESULT_OK" in stdout:
                    detail = stdout.split("RESULT_OK:", 1)[1].strip()[:200]
                    results.append({"name": test_name, "passed": True, "detail": detail})
                elif "SCHEMA_FAIL" in stdout:
                    results.append({"name": test_name, "passed": False, "detail": "Schema validation failed"})
                else:
                    detail = (stdout + " | " + stderr).strip()[:200]
                    results.append({"name": test_name, "passed": False, "detail": detail})

            except subprocess.TimeoutExpired:
                results.append({"name": test_name, "passed": False, "detail": "Test timed out (15s)"})
            except Exception as e:
                results.append({"name": test_name, "passed": False, "detail": str(e)[:200]})

        # Clean up sandbox file
        with contextlib.suppress(OSError):
            sandbox_file.unlink()

        return results

    def review_code(self, design: dict, code: str, llm) -> dict:
        """Stage 5: LLM self-review of generated code. Returns review dict."""
        logger.info("ToolManager: reviewing code for '%s'", design["name"])

        prompt = _REVIEW_PROMPT.format(
            design=json.dumps(design, indent=2),
            code=code,
        )
        messages = [{"role": "system", "content": prompt}]
        resp = llm.chat(messages, reason="tool_review")

        text = resp.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            return json.loads(text)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return {"passed": False, "issues": [f"Review returned unparseable JSON: {text[:200]}"], "verdict": "FAIL"}

    def register_tool(self, name: str, code: str, llm=None, test_code: str = "") -> str:
        """Stage 7: Save tool to production/, write tests, reload registry.

        Args:
            name: Tool name.
            code: Full Python module source.
            llm: Unused, kept for API compatibility.
            test_code: Optional generated test code saved to tests/generated/.

        Returns:
            Status message.
        """
        tools_dir = _TOOLS_DIR
        tools_dir.mkdir(parents=True, exist_ok=True)
        filepath = tools_dir / f"{name}.py"

        # Safety check
        if filepath.exists():
            return f"Tool file '{name}.py' already exists at {filepath}. Use update_tool instead."

        try:
            filepath.write_text(code, encoding="utf-8")
        except OSError as e:
            return f"Failed to write tool file: {e}"

        # Save generated test alongside
        if test_code:
            _TESTS_DIR.mkdir(parents=True, exist_ok=True)
            test_path = _TESTS_DIR / f"test_{name}.py"
            try:
                test_path.write_text(test_code, encoding="utf-8")
            except OSError as e:
                logger.warning("Test file not saved: %s", e)

        # Reload registry
        try:
            from orchestrator.tools import reload_tools
            from orchestrator.event_bus import EventBus, TOOL_CREATED
            reload_tools()
        except Exception as e:
            logger.warning("Tool saved but registry reload failed: %s", e)
            return (
                f"Tool '{name}' saved to {filepath}, but registry reload failed: {e}. "
                f"Restart Raphael to use it."
            )

        # Verify it loaded
        from orchestrator.tools import get_tool_schemas
        schemas = get_tool_schemas()
        found = any(s["function"]["name"] == name for s in schemas)
        if found:
            EventBus().publish(TOOL_CREATED, name=name, file=str(filepath))
            return f"Tool '{name}' created and registered successfully at {filepath}."
        else:
            return f"Tool '{name}' saved to {filepath} but schema not found in registry. Check the file."

    def archive_tool(self, name: str) -> str:
        """Move a generated tool from production/ to archived/."""
        from tools_meta.manager import set_state, STATE_ARCHIVED
        from orchestrator.event_bus import EventBus, TOOL_ARCHIVED

        src = _TOOLS_DIR / f"{name}.py"
        if not src.exists():
            # Check if already archived
            archived = _ARCHIVE_DIR / f"{name}.py"
            if archived.exists():
                return f"Tool '{name}' is already archived."
            return f"Tool '{name}' not found in production or archive."

        _ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        dst = _ARCHIVE_DIR / f"{name}.py"
        src.rename(dst)
        set_state(name, STATE_ARCHIVED)
        EventBus().publish(TOOL_ARCHIVED, name=name)
        return f"Tool '{name}' archived from production to archived/."

    def promote_tool(self, name: str) -> str:
        """Move a tool from draft/ or archived/ to production/ and register it."""
        from tools_meta.manager import set_state, STATE_ACTIVE

        for source_dir in (_DRAFT_DIR, _ARCHIVE_DIR):
            src = source_dir / f"{name}.py"
            if src.exists():
                code = src.read_text(encoding="utf-8")
                result = self.register_tool(name, code)
                if "successfully" in result:
                    set_state(name, STATE_ACTIVE)
                    src.unlink()
                return result
        return f"Tool '{name}' not found in draft/ or archived/."

    def optimize_tool(self, name: str, llm) -> str:
        """OBSERVE → OPTIMIZE: Check execution stats, regenerate if slow.

        Looks at ToolExecutor.needs_optimization() for the tool.
        If flagged, reads the current code, sends it to LLM for optimization,
        benchmarks the new version, and replaces if faster.
        """
        from orchestrator.core import ToolExecutor
        from tools_meta.manager import set_state, STATE_DEGRADED, STATE_ACTIVE
        from orchestrator.event_bus import EventBus, TOOL_OPTIMIZED

        stats = ToolExecutor.tool_stats(name)
        if not stats:
            return f"Tool '{name}' has no execution stats yet."

        if not ToolExecutor.needs_optimization(name):
            return (f"Tool '{name}' is performing well "
                    f"(avg {stats['avg_ms']}ms, {stats['calls']} calls). No optimization needed.")

        # Tool is slow — flag as degraded and regenerate
        set_state(name, STATE_DEGRADED)

        src = _TOOLS_DIR / f"{name}.py"
        if not src.exists():
            return f"Tool '{name}' source not found."

        current_code = src.read_text(encoding="utf-8")
        opt_prompt = (
            f"The following tool is performing poorly (avg {stats['avg_ms']}ms over "
            f"{stats['calls']} calls). Optimize it for speed while keeping the same interface.\n\n"
            f"```python\n{current_code}\n```\n\n"
            "Return ONLY the optimized Python code. Keep function names and schemas identical."
        )

        messages = [{"role": "user", "content": opt_prompt}]
        resp = llm.chat(messages, reason="tool_optimization")

        opt_code = resp.content.strip()
        if opt_code.startswith("```"):
            opt_code = opt_code.split("\n", 1)[1]
            if opt_code.endswith("```"):
                opt_code = opt_code[:-3]
            opt_code = opt_code.strip()

        # Benchmark old vs new
        old_result = self.benchmark_tool(name, current_code, iterations=5)
        new_result = self.benchmark_tool(f"_opt_{name}", opt_code, iterations=5)

        # Extract AVG values
        import re
        old_avg = re.search(r"AVG:([\d.]+)", old_result)
        new_avg = re.search(r"AVG:([\d.]+)", new_result)
        old_ms = float(old_avg.group(1)) if old_avg else 999
        new_ms = float(new_avg.group(1)) if new_avg else 999

        # Clean up benchmark file
        (_SANDBOX_DIR / f"_opt_{name}.py").unlink(missing_ok=True)

        if new_ms < old_ms:
            src.write_text(opt_code, encoding="utf-8")
            from orchestrator.tools import reload_tools
            reload_tools()
            set_state(name, STATE_ACTIVE)

            # Record optimization in capability memory
            from memory.memory_manager import save_capability
            save_capability(
                name=name,
                reason_created=f"Optimized v2: {old_ms:.0f}ms → {new_ms:.0f}ms ({((old_ms-new_ms)/old_ms*100):.0f}% faster)",
                created_by="tool_manager",
                created_from="observation",
            )

            EventBus().publish(TOOL_OPTIMIZED, name=name, old_ms=old_ms, new_ms=new_ms)

            return (f"Optimized '{name}': {old_ms:.0f}ms → {new_ms:.0f}ms "
                    f"({((old_ms-new_ms)/old_ms*100):.0f}% faster). Updated.")
        else:
            set_state(name, STATE_ACTIVE)
            return (f"Optimization attempted but new version ({new_ms:.0f}ms) "
                    f"not faster than current ({old_ms:.0f}ms). Keeping original.")

    # ── Lifecycle Operations ─────────────────────────────────────────────

    def run_pipeline(self, query: str, llm, executor) -> str:
        """
        Run the full tool creation pipeline:
            DESIGN → GENERATE → VALIDATE → SANDBOX TEST → BENCHMARK → SELF REVIEW → REGISTER
        Returns a detailed report of each stage.
        """
        from tools_meta.manager import (
            init_tool, set_state, update_meta, record_test_result,
            record_benchmark,
            add_changelog, bump_version, STATE_GENERATED,
            STATE_VALIDATED, STATE_TESTED, STATE_BENCHMARKED, STATE_REVIEWED,
            STATE_ACTIVE,
        )

        report_lines = ["## Tool Creation Pipeline Report\n"]

        # ── Stage 1: Design ──
        report_lines.append("### Stage 1: DESIGN")
        design = self.design_tool(query, llm)
        if isinstance(design, str):
            report_lines.append(f"❌ Failed: {design}")
            return "\n".join(report_lines)

        tool_name = design["name"]
        init_tool(
            tool_name,
            design.get("description", ""),
            dependencies=design.get("dependencies", []),
        )
        report_lines.append(f"✅ Tool name: `{tool_name}`")
        report_lines.append(f"   Description: {design.get('description', 'N/A')}")
        params_desc = ", ".join(p.get("name", "?") for p in design.get("parameters", []))
        report_lines.append(f"   Parameters: {params_desc or 'None'}")
        report_lines.append("")

        # ── Stage 2: Generate ──
        report_lines.append("### Stage 2: GENERATE")
        code = self.generate_code(design, llm)
        if not code:
            report_lines.append("❌ Failed: LLM returned no code")
            return "\n".join(report_lines)

        set_state(tool_name, STATE_GENERATED)
        line_count = len(code.strip().split("\n"))
        report_lines.append(f"✅ Generated {line_count} lines of Python code")
        report_lines.append("")

        # ── Stage 3: Validate ──
        report_lines.append("### Stage 3: VALIDATE")
        validation_errors = self.validate_code(tool_name, code)
        if validation_errors:
            for err in validation_errors:
                report_lines.append(f"❌ {err}")
            # Don't stop — continue to test to show all issues
        else:
            set_state(tool_name, STATE_VALIDATED)
            report_lines.append("✅ Static validation passed (syntax, structure, security)")
        report_lines.append("")

        # ── Stage 4: Sandbox Test ──
        report_lines.append("### Stage 4: SANDBOX TEST")
        test_results = self.sandbox_test(tool_name, code, design)
        passed_tests = sum(1 for r in test_results if r["passed"])
        failed_tests = sum(1 for r in test_results if not r["passed"])

        for tr in test_results:
            status = "✅" if tr["passed"] else "❌"
            report_lines.append(f"   {status} {tr['name']}: {tr.get('detail', '')[:100]}")
            record_test_result(tool_name, tr["name"], tr["passed"], tr.get("detail", ""))

        if failed_tests == 0 and test_results:
            set_state(tool_name, STATE_TESTED)
            report_lines.append(f"   ✅ All {passed_tests} tests passed")
        else:
            report_lines.append(f"   ⚠️ {failed_tests}/{len(test_results)} tests failed — review needed")
        report_lines.append("")

        # ── Stage 5: Benchmark ──
        report_lines.append("### Stage 5: BENCHMARK")
        bench_result = self.benchmark_tool(tool_name, code, iterations=3)
        report_lines.append(f"   {bench_result.replace(chr(10), chr(10) + '   ')}")
        # Extract avg ms from bench result and record
        import re as _re
        _avg_match = _re.search(r"AVG:([\d.]+)", bench_result)
        if _avg_match:
            _avg_ms = float(_avg_match.group(1))
            record_benchmark(tool_name, "pipeline_benchmark", _avg_ms)

        # Benchmark is informational-only — always passes the gate
        set_state(tool_name, STATE_BENCHMARKED)
        report_lines.append("")
        report_lines.append("")

        # ── Stage 6: Self Review ──
        report_lines.append("### Stage 6: SELF REVIEW")
        review = self.review_code(design, code, llm)
        verdict = review.get("verdict", "FAIL")

        if verdict == "PASS":
            set_state(tool_name, STATE_REVIEWED)
            report_lines.append("✅ Review passed")
        elif verdict == "MINOR_ISSUES":
            set_state(tool_name, STATE_REVIEWED)
            report_lines.append("⚠️ Review passed with minor issues:")
            for issue in review.get("issues", []):
                report_lines.append(f"   • {issue}")
        else:
            report_lines.append("❌ Review failed:")
            for issue in review.get("issues", []):
                report_lines.append(f"   • {issue}")

        suggestions = review.get("suggestions", [])
        for s in suggestions:
            report_lines.append(f"   💡 {s}")
        report_lines.append("")
        report_lines.append("")

        # ── Stage 7: Register ──
        report_lines.append("### Stage 7: REGISTER")
        if validation_errors or (verdict == "FAIL" and not suggestions):
            report_lines.append("❌ Pipeline halted: validation or review issues must be resolved first.")
            report_lines.append("\n**Next steps:** Fix the issues above and run `update_tool` to retry.")
        else:
            update_meta(tool_name, file=str(_TOOLS_DIR / f"{tool_name}.py"))
            register_result = self.register_tool(tool_name, code, llm)
            if "successfully" in register_result:
                set_state(tool_name, STATE_ACTIVE)
                bump_version(tool_name, "minor")  # 0.1.0 → 0.2.0 on first registration
                add_changelog(tool_name, "Pipeline created and registered")
                # Record capability memory
                from memory.memory_manager import save_capability
                save_capability(
                    name=tool_name,
                    reason_created=design.get("description", tool_name),
                    created_by="tool_manager",
                    created_from="conversation",
                    confidence=0.94 if verdict == "PASS" else 0.7,
                )
                report_lines.append(f"✅ {register_result}")
                from tools_meta.manager import get_tool_meta as _gtm
                _tm = _gtm(tool_name)
                report_lines.append(f"   Version: {_tm.get('version', '?') if _tm else '?'}")
            else:
                report_lines.append(f"⚠️ {register_result}")

        # Summary
        report_lines.append("\n---")
        report_lines.append("**Pipeline Summary:**")

        register_status = "⏸️ Blocked"
        if not validation_errors and verdict != "FAIL":
            register_status = "✅ Registered" if register_result and "successfully" in register_result else "⚠️ Partial"

        stages_status = [
            ("DESIGN", "✅" if not isinstance(design, str) else "❌"),  # type: ignore[unreachable]
            ("GENERATE", "✅" if code else "❌"),
            ("VALIDATE", "✅" if not validation_errors else f"⚠️ {len(validation_errors)} issue(s)"),
            ("TEST", f"✅ {passed_tests}/{len(test_results)}" if test_results else "⚠️ No tests"),
            ("BENCHMARK", f"✅ {_avg_ms:.0f}ms avg" if _avg_match else "⚠️ No data"),
            ("REVIEW", f"✅ {verdict}" if verdict != "FAIL" else "❌ FAIL"),
            ("REGISTER", register_status),
        ]
        for stage, status in stages_status:
            report_lines.append(f"  {status} {stage}")

        return "\n".join(report_lines)

    def update_tool(self, name: str, query: str, llm, executor) -> str:
        """Update an existing tool by re-running the pipeline with new design."""
        from tools_meta.manager import get_tool_meta, set_state, STATE_DESIGNED, add_changelog

        meta = get_tool_meta(name)
        if not meta:
            return f"Tool '{name}' not found in metadata registry. Use create_tool first."

        # Reset to designed state
        set_state(name, STATE_DESIGNED)

        # Run pipeline with the existing design as context
        enhanced_query = f"Update the tool '{name}' ({meta.get('description', '')}). New requirements: {query}"
        result = self.run_pipeline(enhanced_query, llm, executor)
        add_changelog(name, f"Updated: {query[:100]}")
        return result

    def benchmark_tool(self, name: str, code: str | None = None, iterations: int = 3) -> str:
        """Benchmark a tool's execution time."""
        from tools_meta.manager import record_benchmark

        if code is None:
            # Try to load from file
            tool_file = _TOOLS_DIR / f"{name}.py"
            if not tool_file.exists():
                return f"Tool '{name}' not found at {tool_file}"
            code = tool_file.read_text(encoding="utf-8")

        # Write to sandbox
        _SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
        sandbox_file = _SANDBOX_DIR / f"_bench_{name}.py"
        sandbox_file.write_text(code, encoding="utf-8")

        bench_script = f"""
import sys, time, json
sys.path.insert(0, r"{_SANDBOX_DIR}")
from _bench_{name} import {name} as bench_fn, get_schemas
# Read schema to determine parameters
schemas = get_schemas()
_params = {{}}
if schemas:
    _props = schemas[0].get("function", {{}}).get("parameters", {{}}).get("properties", {{}})
    _params = {{k: "test" for k in _props}}
# Run function N times
times = []
for i in range({iterations}):
    start = time.time()
    result = bench_fn(**_params) if _params else bench_fn()
    elapsed = (time.time() - start) * 1000
    times.append(elapsed)
avg = sum(times) / len(times)
print(f"AVG:{{avg:.2f}}")
print(f"MIN:{{min(times):.2f}}")
print(f"MAX:{{max(times):.2f}}")
"""

        try:
            proc = subprocess.run(
                [sys.executable, "-c", bench_script],
                capture_output=True, text=True, timeout=30,
            )
            lines = proc.stdout.strip().split("\n")
            avg_ms = 0.0
            for line in lines:
                if line.startswith("AVG:"):
                    avg_ms = float(line.split(":")[1])
                    record_benchmark(name, "execution", avg_ms)

            return (
                f"**Benchmark Results for '{name}':**\n"
                + "\n".join(lines)
                + (f"\n\nStderr: {proc.stderr[:200]}" if proc.stderr else "")
            )
        except Exception as e:
            return f"Benchmark failed: {e}"
        finally:
            with contextlib.suppress(OSError):
                sandbox_file.unlink()

    # ── Helpers ──────────────────────────────────────────────────────────

    def _generate_test_cases(self, name: str, params: list) -> list[dict]:
        """Generate basic test cases from parameter definitions."""
        if not params:
            return [{"name": "basic_call", "args": {}, "expect": "returns string"}]

        test_cases = []

        # Test with all params filled with dummy values
        valid_args = {}
        for p in params:
            pname = p.get("name", "")
            valid_args[pname] = "test"
        test_cases.append({"name": "basic_call", "args": valid_args, "expect": "returns string"})

        # Test with minimal params (only required ones)
        required_args = {}
        for p in params:
            if p.get("required", True):
                pname = p.get("name", "")
                required_args[pname] = "test"
        if required_args and len(required_args) < len(valid_args):
            test_cases.append({"name": "minimal_params", "args": required_args, "expect": "returns string"})

        return test_cases

    def _format_args_for_test(self, args: dict) -> str:
        """Format args dict as Python keyword arguments string."""
        parts = []
        for k, v in args.items():
            if isinstance(v, str):
                parts.append(f'{k}="{v}"')
            else:
                parts.append(f"{k}={v}")
        return ", ".join(parts)

    # ── Skill Execution ──────────────────────────────────────────────────

    def execute(self, llm, executor, query: str = "", **kwargs) -> str:
        """Execute the Tool Manager skill based on the query."""
        q = query.lower()

        # Route to appropriate operation
        if any(kw in q for kw in ["update tool", "modify tool", "change tool"]):
            # Extract tool name from query
            import re
            match = re.search(r"(?:update|modify|change)\s+(?:tool\s+)?(\w+)", q)
            tool_name = match.group(1) if match else ""
            if tool_name:
                return self.update_tool(tool_name, query, llm, executor)
            return "Please specify which tool to update."

        if any(kw in q for kw in ["benchmark tool", "benchmark"]):
            import re
            match = re.search(r"(?:benchmark)\s+(?:tool\s+)?(\w+)", q)
            tool_name = match.group(1) if match else ""
            if tool_name:
                return self.benchmark_tool(tool_name)
            return "Please specify which tool to benchmark."

        # Default: run full creation pipeline
        if any(kw in q for kw in [
            "create a tool", "make a tool", "new tool", "add tool",
            "create tool", "build a tool", "generate tool", "design tool",
        ]):
            return self.run_pipeline(query, llm, executor)

        # Metadata query
        if any(kw in q for kw in ["list tools", "tool status", "tool summary", "show tools"]):
            from tools_meta.manager import get_summary
            return get_summary()

        return (
            "I can help with tool management. Try:\n"
            "- 'Create a tool that...'\n"
            "- 'Update tool <name> to...'\n"
            "- 'Benchmark tool <name>'\n"
            "- 'List tools' or 'Show tool summary'"
        )
