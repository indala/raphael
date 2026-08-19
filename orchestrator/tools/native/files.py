"""File processing tools — process files, analyze images, read/write/edit files."""

import config
from actions.file_processor import process_file as _process_file
from modules import recycle_bin as _recycle_bin
from modules import shortcuts as _shortcuts

# ── Read-before-edit tracking ───────────────────────────────────────
_read_file_registry: set[str] = set()

# ── Written-file registry — tracks files created this session ───────
# Maps resolved absolute path → original path string as passed by the LLM.
# Surfaced back to the LLM via get_written_files_context() so it can find
# previously created files without shell searches.
_written_files_registry: dict[str, str] = {}


def clear_read_file_registry() -> None:
    """Clear the read-file registry (called at start of each user request)."""
    _read_file_registry.clear()


def get_written_files_context() -> str:
    """Return a summary of files written this session for injection into the system prompt.

    Returns an empty string when nothing has been written yet.
    """
    if not _written_files_registry:
        return ""
    lines = ["Files created/written this session (use these exact paths — do NOT search):"]
    for resolved in _written_files_registry:
        lines.append(f"  • {resolved}")
    return "\n".join(lines)


def clear_written_files_registry() -> None:
    """Clear the written-files registry (e.g. on full session reset)."""
    _written_files_registry.clear()


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write text content directly to a file. Handles encoding safely — no shell escaping needed. Use this INSTEAD of 'run_command' with Python/PowerShell for creating or overwriting files. Supports all text-based files: HTML, Python, JS, CSS, JSON, TXT, MD, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Full path to the output file (e.g. 'C:/Users/admin/AppData/Local/Raphael/outputs/game.html')",
                        },
                        "content": {
                            "type": "string",
                            "description": "The full text content to write to the file",
                        },
                        "append": {
                            "type": "boolean",
                            "description": "If true, append to the file instead of overwriting. Default: false.",
                        },
                    },
                    "required": ["file_path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a text file with file metadata and binary protection. Returns the file content as a string. Supports all text-based file formats.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Full path to the file to read",
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "Maximum number of characters to return. Default 50000. Use to avoid reading extremely large files.",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "view_file",
                "description": "View file contents with 1-based line numbers, file metadata (total lines, size, type), line slicing, and binary protection. Preferred for inspecting code files before editing.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Full path to the file to view",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "1-based starting line number (optional).",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "1-based ending line number (optional).",
                        },
                        "max_lines": {
                            "type": "integer",
                            "description": "Maximum number of lines to display. Default: 500.",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "replace_file_content",
                "description": "Make a precise surgical replacement of a contiguous block of text in an existing file. Throws clear errors if the target block does not match.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Full path to the file to modify",
                        },
                        "target_content": {
                            "type": "string",
                            "description": "The exact existing text chunk to replace (must match characters and indentation exactly)",
                        },
                        "replacement_content": {
                            "type": "string",
                            "description": "The new replacement text to insert",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "Optional starting line hint for disambiguation",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "Optional ending line hint for disambiguation",
                        },
                    },
                    "required": ["file_path", "target_content", "replacement_content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "process_file",
                "description": "Process a file on the system. Supports: image (resize/convert/compress/crop/info), pdf (extract_text/info/to_word/extract_pages), docx (extract_text/info), text (word_count/info), csv (filter/sort/convert/stats/info), excel (filter/convert/stats/info), json (validate/format/extract/info), code (run/info), video (info/extract_audio), archive (list/extract/info), pptx (extract_text/info). For AI analysis (summarize, analyze, describe, explain), the extracted content is returned for the LLM to process.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file",
                        },
                        "action": {
                            "type": "string",
                            "description": "Action to perform: info, resize, convert, compress, crop, extract_text, to_word, extract_pages, word_count, filter, sort, stats, validate, format, run, list, extract, summarize, analyze, describe",
                        },
                    },
                    "required": ["file_path", "action"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_image",
                "description": "Analyze an image file using vision AI — describe what's in the picture, extract text, identify objects, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Full path to the image file (PNG, JPG, etc.)",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "List files and subdirectories inside a specific path on the filesystem.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory_path": {
                            "type": "string",
                            "description": "The path to the directory (e.g. '.', 'C:/Users/Admin/Documents'). Defaults to the current working directory.",
                        }
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "edit_file",
                "description": "Make a targeted edit to an existing text file by finding and replacing a specific string. PREFERRED over write_file for small changes — only the changed portion is sent, preserving indentation and the rest of the file. Always read_file first before editing.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Full path to the file to edit (e.g. 'C:/Users/admin/file.py')",
                        },
                        "old_string": {
                            "type": "string",
                            "description": "The exact existing text to replace. Use 2-4 adjacent lines of surrounding context to make it unique. Must match exactly including indentation and quotes.",
                        },
                        "new_string": {
                            "type": "string",
                            "description": "The new text to insert in place of old_string. Preserve the same indentation style.",
                        },
                        "replace_all": {
                            "type": "boolean",
                            "description": "If true, replace ALL occurrences of old_string. Default: false. Use sparingly — prefer unique matches.",
                        },
                    },
                    "required": ["file_path", "old_string", "new_string"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_output",
                "description": "Save a previously-generated file (game, web page, creative content) from the temp outputs folder to the permanent outputs directory. Call this when the user says they like a generated file and want to keep it permanently.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Filename to save from the temp outputs folder (e.g. 'game.html', 'script.py')",
                        }
                    },
                    "required": ["filename"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_shortcut",
                "description": "Create a Windows .lnk shortcut file that points to a target application or file. Optionally sets launch arguments, a working directory, and a description. Use when the user wants a desktop or Start Menu shortcut.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "link_path": {
                            "type": "string",
                            "description": "Full path where the .lnk file should be created (e.g. 'C:/Users/admin/Desktop/My App.lnk')",
                        },
                        "target": {
                            "type": "string",
                            "description": "Full path to the application or file the shortcut launches",
                        },
                        "arguments": {
                            "type": "string",
                            "description": "Optional command-line arguments passed to the target",
                        },
                        "working_dir": {
                            "type": "string",
                            "description": "Optional working directory for the launched process",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional human-readable description shown in the shortcut's tooltip",
                        },
                    },
                    "required": ["link_path", "target"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "recycle_bin_get",
                "description": "Query the Windows Recycle Bin and report how many items it contains and their total size in bytes across all drives. Use when the user asks how full the recycle bin is or wants to check its contents before emptying.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "recycle_bin_empty",
                "description": "Permanently empty the Windows Recycle Bin, deleting every item across all drives. Destructive and irreversible: it requires an explicit confirm=true argument and otherwise does nothing at all.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirm": {
                            "type": "boolean",
                            "description": "Must be true to actually empty the recycle bin; false or omitted is a no-op",
                        },
                    },
                    "required": [],
                },
            },
        },
    ]


def save_output(filename: str) -> str:
    """Save a generated file from temp to the permanent outputs directory.

    Args:
        filename: The file name (with extension) to promote from temp to permanent.

    Returns:
        A confirmation message with the destination path.
    """
    import shutil
    import tempfile
    from pathlib import Path

    temp_dir = Path(tempfile.gettempdir()) / "Raphael" / "outputs"
    output_dir = Path(getattr(config, "SCREENSHOT_DIR", str(Path.cwd() / "outputs")))

    src = temp_dir / filename
    if not src.is_file():
        available = [p.name for p in temp_dir.iterdir()] if temp_dir.is_dir() else []
        listing = f" Available temp files: {', '.join(available)}" if available else ""
        return f"File '{filename}' not found in temp outputs directory ({temp_dir}).{listing}"

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        dest = output_dir / filename
        shutil.copy2(src, dest)
        return f"Saved '{filename}' to {dest} ({dest.stat().st_size} bytes)."
    except Exception as e:
        return f"Error saving '{filename}': {e}"


def process_file(file_path: str, action: str = "info") -> str:
    """Process a file with the given action."""
    try:
        return _process_file(file_path, action)
    except Exception as e:
        return f"Error processing file: {e}"


def analyze_image(file_path: str) -> str:
    """Send an image to the vision model and return a description."""
    from pathlib import Path
    path = Path(file_path)
    if not path.is_file():
        return f"Error: File not found at {file_path}"
    ext = path.suffix.lower().lstrip(".")
    image_exts = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "svg", "ico"}
    if ext not in image_exts:
        return f"Error: '{ext}' is not a supported image format ({', '.join(sorted(image_exts))})"

    try:
        from orchestrator.core import LLMClient
        client = LLMClient()
        messages = [
            {"role": "system", "content": "You are an image analyst. Describe everything you see in detail — objects, text, colors, layout, and any notable features."},
            {"role": "user", "content": "Analyze this image in detail."},
        ]
        result = client.chat_with_vision(messages, str(path))
        if result and hasattr(result, "content") and result.content:
            return result.content  # type: ignore[no-any-return]
        return "The vision model returned an empty response."
    except Exception as e:
        return f"Error analyzing image: {e}"


def write_file(file_path: str, content: str, append: bool = False) -> str:
    """Write text content directly to a file. No shell escaping needed.

    Args:
        file_path: Full path to the output file.
        content: The text content to write.
        append: If True, append to existing file instead of overwriting.

    Returns:
        A confirmation message with file path and size.
    """
    import os
    from pathlib import Path
    try:
        path = Path(file_path).expanduser().resolve()
        # Create parent directories if they don't exist
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(content)
        size = os.path.getsize(path)
        # Track this file so Raphael can find it later without shell searches
        _written_files_registry[str(path)] = file_path
        action = "Appended to" if append else "Written"
        return f"{action} {path} ({size} bytes)"
    except Exception as e:
        return f"Error writing file {file_path}: {e}"


_BINARY_EXTENSIONS: dict[str, str] = {
    ".pdf": "PDF document (use process_file with action='extract_text' or action='info')",
    ".png": "Image file (use analyze_image or process_file with action='info')",
    ".jpg": "Image file (use analyze_image or process_file with action='info')",
    ".jpeg": "Image file (use analyze_image or process_file with action='info')",
    ".gif": "Image file (use analyze_image)",
    ".webp": "Image file (use analyze_image)",
    ".ico": "Image file (use analyze_image)",
    ".exe": "Windows executable binary (cannot read as plain text)",
    ".dll": "Dynamic link library binary (cannot read as plain text)",
    ".pyd": "Python native C-extension binary (cannot read as plain text)",
    ".so": "Shared object library binary (cannot read as plain text)",
    ".zip": "Archive file (use process_file with action='list' or action='extract')",
    ".tar": "Archive file (use process_file with action='list' or action='extract')",
    ".gz": "Archive file (use process_file with action='list' or action='extract')",
    ".7z": "Archive file (use process_file with action='list' or action='extract')",
    ".docx": "Word document (use process_file with action='extract_text')",
    ".pptx": "PowerPoint document (use process_file with action='extract_text')",
    ".xlsx": "Excel spreadsheet (use process_file with action='convert' or action='stats')",
    ".mp3": "Audio file (use play_audio_file or process_file)",
    ".wav": "Audio file (use play_audio_file or process_file)",
    ".mp4": "Video file (use process_file with action='extract_audio')",
    ".db": "SQLite database binary (use sqlite or database tools)",
    ".sqlite": "SQLite database binary (use sqlite or database tools)",
    ".pyc": "Compiled Python bytecode",
}


def read_file(file_path: str, max_chars: int = 50000) -> str:
    """Read the contents of a text file with metadata and binary protection."""
    from pathlib import Path
    try:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            return f"Error: File not found at {file_path}"

        ext = path.suffix.lower()
        if ext in _BINARY_EXTENSIONS:
            return (
                f"Cannot read '{path.name}' as plain text: detected {ext} binary format.\n"
                f"Recommendation: {_BINARY_EXTENSIONS[ext]}"
            )

        # Register for read-before-edit enforcement
        _read_file_registry.add(str(path))
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)

        file_size_kb = round(path.stat().st_size / 1024, 1)
        type_name = ext.lstrip(".").upper() if ext else "TEXT"
        header = f"=== [File: {path.name} | Type: {type_name} | Size: {file_size_kb} KB] ===\n"

        if len(content) >= max_chars:
            content += f"\n\n...(truncated at {max_chars} chars, total file size is {file_size_kb} KB. Use view_file or read_file_range to inspect remaining lines)"
        return header + content
    except Exception as e:
        return f"Error reading file {file_path}: {e}"


def view_file(
    file_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    max_lines: int = 500,
) -> str:
    """View file contents with 1-based line numbers, metadata header, and line range slicing."""
    from pathlib import Path
    try:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            return f"Error: File not found at {file_path}"

        ext = path.suffix.lower()
        if ext in _BINARY_EXTENSIONS:
            return (
                f"Cannot view '{path.name}' as plain text: detected {ext} binary format.\n"
                f"Recommendation: {_BINARY_EXTENSIONS[ext]}"
            )

        _read_file_registry.add(str(path))

        with open(path, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        file_size_kb = round(path.stat().st_size / 1024, 1)

        s_line = start_line if start_line is not None and start_line >= 1 else 1
        if s_line > total_lines:
            return f"Start line {s_line} exceeds total file length ({total_lines} lines in {path.name})."

        e_line = end_line if end_line is not None and end_line >= s_line else min(s_line + max_lines - 1, total_lines)
        e_line = min(e_line, s_line + max_lines - 1, total_lines)

        selected_lines = all_lines[s_line - 1 : e_line]

        type_name = ext.lstrip(".").upper() if ext else "TEXT"
        header = f"=== [File: {path.name} | Type: {type_name} | Lines: {s_line}-{e_line} of {total_lines} | Size: {file_size_kb} KB] ==="

        if total_lines > e_line and end_line is None:
            header += f"\n[Note: Showing first {e_line} of {total_lines} lines. Specify start_line/end_line to view remaining content.]"

        numbered = [f"{s_line + i:4d}: {line.rstrip()}" for i, line in enumerate(selected_lines)]
        return header + "\n" + "\n".join(numbered)
    except Exception as e:
        return f"Error viewing file {file_path}: {e}"


def replace_file_content(
    file_path: str,
    target_content: str,
    replacement_content: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    """Make a precise surgical replacement of a contiguous block of text in an existing file."""
    from pathlib import Path
    try:
        path = Path(file_path).expanduser().resolve()
        resolved = str(path)

        if resolved not in _read_file_registry:
            return (
                f"Error: You must read or view '{file_path}' before editing it. "
                f"Use view_file or read_file first."
            )

        if not path.is_file():
            return f"Error: File not found at {file_path}"

        with open(path, encoding="utf-8") as f:
            content = f.read()

        if start_line is not None or end_line is not None:
            lines = content.splitlines(keepends=True)
            total = len(lines)
            s = (start_line - 1) if start_line and start_line >= 1 else 0
            e = end_line if end_line and end_line >= s else total
            e = min(e, total)

            sub_content = "".join(lines[s:e])
            if target_content not in sub_content:
                return (
                    f"Error: Target content was not found within lines {s+1}-{e} of '{path.name}'. "
                    f"Please verify the line range or target text."
                )

            new_sub = sub_content.replace(target_content, replacement_content, 1)
            new_content = "".join(lines[:s]) + new_sub + "".join(lines[e:])
        else:
            if target_content not in content:
                return (
                    f"Error: Target content was not found in '{path.name}'. "
                    f"Please ensure target_content exactly matches the existing file contents."
                )

            occurrences = content.count(target_content)
            if occurrences > 1:
                return (
                    f"Error: Target content occurs {occurrences} times in '{path.name}'. "
                    f"Please provide more surrounding context or specify start_line and end_line."
                )

            new_content = content.replace(target_content, replacement_content, 1)

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        _written_files_registry[str(path)] = file_path
        new_size = path.stat().st_size
        return f"Successfully updated '{path.name}' ({new_size} bytes). Replaced 1 block."
    except Exception as e:
        return f"Error replacing content in {file_path}: {e}"


def list_directory(directory_path: str = ".") -> str:
    """List files and subdirectories inside a directory."""
    import os
    from pathlib import Path
    try:
        path = Path(directory_path).expanduser().resolve()
        if not path.exists():
            return f"Directory '{directory_path}' does not exist."
        if not path.is_dir():
            return f"Path '{directory_path}' is a file, not a directory."

        items = os.listdir(path)
        lines = [f"Contents of {path}:"]

        # Sort items: directories first, then files
        dirs = []
        files = []
        for item in items:
            item_path = path / item
            try:
                if item_path.is_dir():
                    dirs.append(item)
                else:
                    files.append((item, item_path.stat().st_size))
            except Exception:
                # Handle permission errors on individual items gracefully
                files.append((item, 0))

        dirs.sort()
        files.sort(key=lambda x: x[0])

        for d in dirs:
            lines.append(f"  [DIR]  {d}/")
        for f, sz in files:
            lines.append(f"  [FILE] {f} ({sz} bytes)")

        if not dirs and not files:
            lines.append("  (empty directory)")

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to list directory contents: {e}"


def edit_file(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Make a targeted edit to an existing text file by replacing old_string with new_string.

    PREFERRED over write_file for small changes — only the diff is sent.
    Always read_file first before editing (enforced by read-before-edit registry).

    Args:
        file_path: Full path to the file to edit.
        old_string: The exact existing text to replace (must match exactly).
        new_string: The new text to insert in place of old_string.
        replace_all: If True, replace ALL occurrences of old_string.

    Returns:
        A confirmation message with file path and size.
    """
    import os
    from pathlib import Path
    try:
        path = Path(file_path).expanduser().resolve()
        resolved = str(path)

        # Read-before-edit enforcement
        if resolved not in _read_file_registry:
            return (
                f"Error: You must read '{file_path}' before editing it. "
                f"Use read_file first."
            )

        if not path.is_file():
            return f"Error: File not found at {file_path}"

        with open(path, encoding="utf-8") as f:
            content = f.read()

        count = content.count(old_string)
        if count == 0:
            return (
                "Error: old_string not found in file. "
                "Make sure the text matches exactly including indentation, "
                "quotes, and whitespace. Use read_file to verify the exact content."
            )
        if count > 1 and not replace_all:
            return (
                f"Error: old_string appears {count} times in the file. "
                f"Use more surrounding context (2-4 adjacent lines) to make it unique, "
                f"or set replace_all=True to replace all occurrences."
            )

        new_content = content.replace(old_string, new_string)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        size = os.path.getsize(path)
        old_preview = old_string[:60].replace("\n", "\\n")
        new_preview = new_string[:60].replace("\n", "\\n")
        return f"Edited {path} ({size} bytes) — replaced '{old_preview}' with '{new_preview}'"
    except Exception as e:
        return f"Error editing file {file_path}: {e}"


def create_shortcut(
    link_path: str,
    target: str,
    arguments: str = "",
    working_dir: str = "",
    description: str = "",
) -> str:
    """Create a .lnk shortcut pointing at a target application or file."""
    return _shortcuts.create_shortcut(link_path, target, arguments, working_dir, description)


def recycle_bin_get() -> str:
    """Query the recycle bin's item count and total size."""
    return _recycle_bin.recycle_bin_get()


def recycle_bin_empty(confirm: bool = False) -> str:
    """Empty the recycle bin; no-op unless confirm=True."""
    return _recycle_bin.recycle_bin_empty(confirm)

