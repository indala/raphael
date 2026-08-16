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

    # Curated tool guide (label → tool names). Only names registered in the
    # tool registry are emitted; unregistered names are dropped with a warning.
    _TOOL_GUIDE = (
        ("Memory", ("save_memory", "recall_memory", "list_memories")),
        ("Search", ("web_search", "web_fetch", "search_online")),
        (
            "System & Volume",
            ("set_system_volume", "get_system_volume"),
        ),
        (
            "Music & Library",
            (
                "play_song",
                "stream_song",
                "save_song",
                "pause_music",
                "resume_music",
                "stop_music",
                "list_local_songs",
                "play_playlist",
                "create_playlist",
                "stream_playlist",
            ),
        ),
        (
            "Files",
            ("edit_file", "write_file", "read_file", "process_file", "save_output"),
        ),
        ("Email", ("read_inbox", "search_emails", "send_email")),
        ("Vision", ("analyze_image",)),
        ("Browser", ("browser_control",)),
        (
            "Desktop UI",
            (
                "ui_click",
                "ui_type_text",
                "ui_press_key",
                "ui_hotkey",
                "ui_focus_window",
                "ui_enum_windows",
                "ui_close_window",
            ),
        ),
        (
            "Desktop State",
            (
                "desktop_snapshot_v2",
                "desktop_taskbar",
                "desktop_tray",
                "desktop_processes",
                "desktop_system_info",
                "desktop_network",
                "desktop_environment",
                "launch_app",
                "run_command",
            ),
        ),
        (
            "Agents & Tasks",
            (
                "spawn_agent",
                "delegate_to_agent",
                "delegate_background",
                "check_task",
                "list_tasks",
                "list_agents",
            ),
        ),
        ("Background", ("run_in_background",)),
    )

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
        input_mode: str = "text",
    ) -> str:
        """Assemble the complete system prompt from modular sections."""
        sections = [
            SystemPromptBuilder._build_identity_section(date_str, time_str),
            SystemPromptBuilder._build_input_modality_section(input_mode),
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
    def _build_input_modality_section(input_mode: str = "text") -> str:
        if input_mode == "voice":
            return (
                "=== USER INPUT MODALITY: VOICE (STT) ===\n"
                "• The user provided this prompt via speech / microphone (STT).\n"
                "• The user is LISTENING and interacting hands-free (may not be looking at the screen).\n"
                "• Provide a clear, natural, conversational response suitable for text-to-speech."
            )
        else:
            return (
                "=== USER INPUT MODALITY: TEXT (CHAT) ===\n"
                "• The user typed this prompt via chat UI.\n"
                "• The user is READING the screen visually.\n"
                "• Provide a complete formatted text response. Spoken TTS will be concise (summaries/subheadings only)."
            )

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
            + SystemPromptBuilder._build_tool_guide()
            + "\n"
            "CODE: Use edit_file with old→new replacement for targeted edits. Use write_file for new files. "
            "Always read_file before editing. "
            "IMPORTANT — when fixing a file you previously created: check the '=== FILES CREATED THIS SESSION ===' "
            "section in this prompt for the exact path. Do NOT use run_command or list_directory to "
            "search for it — that wastes time. The path is already known. Correct flow: "
            "(1) read_file(known_path) → (2) edit_file(known_path, old, new) → done.\n\n"
            "WINDOWS: Always desktop_snapshot_v2 or ui_enum_windows before acting on windows. "
            "Never close PROTECTED windows (Raphael's own process). "
            "Use ui_close_window (WM_CLOSE), not Alt+F4/kill.\n\n"
            "STRICT ACTION RULE: Whenever user asks to perform an action (e.g. play music, pause, resume, stop, set volume, create playlist, write file), "
            "you MUST invoke the appropriate tool (stream_song, play_song, pause_music, resume_music, stop_music, set_system_volume, create_playlist) IN YOUR TURN. "
            "NEVER write conversational text claiming an action succeeded (e.g. 'Now playing Flowers', 'Music paused', 'Resuming') without calling the tool in that turn! "
            "Do NOT call desktop_snapshot_v2 for music or volume tasks — use the native music tools directly.\n\n"
            "MUSIC PLAYER: You have your OWN built-in native Music Player. "
            "For specific song requests (e.g. 'play Faded by Alan Walker'), call stream_song or play_song directly. "
            "For generic requests (e.g. 'play a song from online', 'play something popular', 'play music'), "
            "ALWAYS search first using search_online to discover top real song tracks, "
            "then stream or play a specific resolved song title or stream_playlist. "
            "Always state the EXACT song title and artist being played in your response.\n\n"
            "If user asks NOT to use a tool, respect it and use alternatives."
        )

    @staticmethod
    def _build_tool_guide() -> str:
        """Build the tool bullet list from _TOOL_GUIDE, dropping any name that is
        not actually registered so the prompt can never reference phantom tools.
        
        Task 9: Cache the result via CacheManager with tool registry version.
        Automatically invalidates when tools are reloaded.
        """
        from orchestrator.cache_manager import get_cache_manager
        from orchestrator.tools import get_tool_map, get_tool_registry_version

        cache = get_cache_manager()
        registry_version = get_tool_registry_version()

        # Set version for the tool_guide namespace
        cache.set_version("tool_guide", registry_version)

        # Try to get from cache
        cached = cache.get("tool_guide", "guide_text")
        if cached is not None:
            return cached

        registered = get_tool_map()
        lines = []
        for label, names in SystemPromptBuilder._TOOL_GUIDE:
            existing = [n for n in names if n in registered]
            for dropped in [n for n in names if n not in registered]:
                logger.warning(
                    "Tool guide: '%s' is not registered and was omitted from the prompt", dropped
                )
            if existing:
                lines.append(f"• {label} → {', '.join(existing)}")

        result = "\n".join(lines) + "\n"
        # Cache with no TTL (expires only on version change)
        cache.set("tool_guide", "guide_text", result)
        return result

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
