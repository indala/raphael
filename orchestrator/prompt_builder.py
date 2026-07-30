"""
SystemPromptBuilder — Modular system prompt construction for Raphael.

Assembles system prompts from structured sections:
1. Identity & Temporal Context
2. User & System Context (Hardware state, Recalled memory, Evolution context)
3. Reasoning & Planning Hierarchy
4. Tool Policies & Capabilities
5. Safety & Security Guardrails
6. Failure & Uncertainty Handling
7. Delegation Philosophy
8. Output Directories & Knowledge Base
"""

import logging

logger = logging.getLogger(__name__)


class SystemPromptBuilder:
    """Builds composable system prompts for Raphael LLM calls."""

    @staticmethod
    @staticmethod
    def build(
        date_str: str,
        time_str: str,
        spk_ok: bool,
        tts_ok: bool,
        mic_ok: bool,
        memory_context: str = "",
        raphael_context: str = "",
        screenshot_dir: str = "outputs",
        proactive_instruction: str | None = None,
        task_context: str | None = None,
    ) -> str:
        """Assemble the complete system prompt from modular sections."""
        sections = [
            SystemPromptBuilder._build_identity_section(date_str, time_str),
            SystemPromptBuilder._build_context_section(
                spk_ok=spk_ok,
                tts_ok=tts_ok,
                mic_ok=mic_ok,
                memory_context=memory_context,
                raphael_context=raphael_context,
            ),
            SystemPromptBuilder._build_reasoning_section(),
            SystemPromptBuilder._build_tool_policies_section(),
            SystemPromptBuilder._build_security_section(),
            SystemPromptBuilder._build_failure_section(),
            SystemPromptBuilder._build_delegation_section(),
            SystemPromptBuilder._build_output_and_knowledge_section(screenshot_dir),
        ]

        if task_context:
            sections.append(task_context)

        if proactive_instruction:
            sections.append(f"=== PROACTIVE CHECK ===\n{proactive_instruction}")

        return "\n\n".join(sec for sec in sections if sec.strip())

    @staticmethod
    def _build_identity_section(date_str: str, time_str: str) -> str:
        return (
            "=== IDENTITY & TIME ===\n"
            "You are Raphael, an advanced AI desktop assistant on Windows. "
            "You are helpful, precise, proactive, and respond concisely.\n"
            f"Current Date: {date_str}\n"
            f"Current Time: {time_str}"
        )

    @staticmethod
    def _build_context_section(
        spk_ok: bool,
        tts_ok: bool,
        mic_ok: bool,
        memory_context: str,
        raphael_context: str,
    ) -> str:
        audio_desc = (
            f"- Speaker (Audio Output): {'AVAILABLE' if spk_ok else 'UNAVAILABLE (No physical speaker device)'}\n"
            f"- TTS Engine: {'ENABLED' if tts_ok else 'DISABLED'}\n"
            f"- Microphone (Audio Input): {'AVAILABLE' if mic_ok else 'UNAVAILABLE'}\n"
        )
        if not spk_ok or not tts_ok:
            audio_desc += (
                "NOTE: Audio output / speaker is currently UNAVAILABLE or DISABLED. "
                "Do NOT call the 'speak' tool. Provide all responses directly in text."
            )
        else:
            audio_desc += "Use the 'speak' tool to deliver verbal responses when appropriate."

        content = f"=== SYSTEM HARDWARE STATE ===\n{audio_desc}"

        combined_memory = ""
        if memory_context:
            combined_memory += memory_context.strip() + "\n"
        if raphael_context:
            combined_memory += raphael_context.strip() + "\n"

        if combined_memory.strip():
            content += f"\n\n=== USER & EVOLUTION CONTEXT ===\n{combined_memory.strip()}"

        return content

    @staticmethod
    def _build_reasoning_section() -> str:
        return (
            "=== REASONING ===\n"
            "Think step-by-step. Use tools when needed, converse directly when not. "
            "For multi-step tasks, plan first then execute."
        )

    @staticmethod
    def _build_tool_policies_section() -> str:
        return (
            "=== TOOL POLICIES ===\n"
            "• Memory → save_memory / recall_memory\n"
            "• Search → web_search\n"
            "• Files → edit_file (preferred for edits), write_file (new files), read_file, process_file\n"
            "• Vision → analyze_image\n"
            "• Browser → browser_control (navigate, click, fill, scroll)\n"
            "• Desktop UI → ui_click, ui_type_text, ui_press_key, ui_hotkey, ui_focus_window, ui_enum_windows, ui_close_window\n"
            "• Desktop State → desktop_snapshot_v2 (comprehensive), desktop_taskbar, desktop_tray, desktop_processes, desktop_system_info, desktop_network, desktop_environment\n"
            "• Background → run_in_background for ops >3s\n\n"
            "CODE: Use edit_file with old→new replacement for targeted edits. Use write_file for new files. "
            "Always read_file before editing.\n\n"
            "WINDOWS: Always desktop_snapshot_v2 or ui_enum_windows before acting on windows. "
            "Never close PROTECTED windows (Raphael's own process). "
            "Use ui_close_window (WM_CLOSE), not Alt+F4/kill.\n\n"
            "If user asks NOT to use a tool, respect it and use alternatives."
        )

    @staticmethod
    def _build_security_section() -> str:
        return (
            "=== SAFETY & SECURITY ===\n"
            "• Never execute destructive system commands (file deletion, formatting, registry modification, bulk file modifications) "
            "without explicit user confirmation.\n"
            "• Keep system command execution safe, targeted, and scoped."
        )

    @staticmethod
    def _build_failure_section() -> str:
        return (
            "=== FAILURE & UNCERTAINTY ===\n"
            "• Never pretend a tool succeeded when it failed. Explain, retry, or use an alternative.\n"
            "• State uncertainty clearly rather than guessing.\n"
            "• INTERRUPT REVERIFY: If user interrupts mid-task, call `desktop_snapshot` "
            "before continuing — coordinates/windows may have changed."
        )

    @staticmethod
    def _build_delegation_section() -> str:
        return (
            "=== AGENT DELEGATION ===\n"
            "Use `list_agents` to see available sub-agents.\n"
            "• `delegate_background(agent, query)` — PREFERRED. Returns immediately. "
            "Acknowledge user and retrieve result with `check_task(task_id)` later.\n"
            "• `delegate_to_agent(agent, query)` — only when you need the result inline "
            "before responding.\n"
            "• `check_task(task_id)` — get result from a background task.\n"
            "Fast acknowledgement is better than making the user wait."
        )

    @staticmethod
    def _build_output_and_knowledge_section(screenshot_dir: str) -> str:
        return (
            "=== OUTPUTS & KNOWLEDGE ===\n"
            f"• Save files to `{screenshot_dir}`.\n"
            "• For interactive content (HTML): write_file to temp dir, open with `open_url`, "
            "use `save_output()` if user likes it.\n"
            "• Knowledge: use `list_knowledge_files` / `read_knowledge_file` in `knowledge/`."
        )
