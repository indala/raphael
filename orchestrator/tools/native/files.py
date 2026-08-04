"""File processing tools — process files, analyze images, read/write/edit files."""

import config
from actions.file_processor import process_file as _process_file
from modules import recycle_bin as _recycle_bin
from modules import shortcuts as _shortcuts

# ── Read-before-edit tracking ───────────────────────────────────────
_read_file_registry: set[str] = set()


def clear_read_file_registry() -> None:
    """Clear the read-file registry (called at start of each user request)."""
    _read_file_registry.clear()


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
                "description": "Read the contents of a text file. Returns the file content as a string. Supports all text-based file formats.",
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
        action = "Appended to" if append else "Written"
        return f"{action} {path} ({size} bytes)"
    except Exception as e:
        return f"Error writing file {file_path}: {e}"


def read_file(file_path: str, max_chars: int = 50000) -> str:
    """Read the contents of a text file.

    Args:
        file_path: Full path to the file to read.
        max_chars: Maximum characters to return (prevents overflow).

    Returns:
        The file content as a string.
    """
    from pathlib import Path
    try:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            return f"Error: File not found at {file_path}"
        # Register for read-before-edit enforcement
        _read_file_registry.add(str(path))
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)
        if len(content) >= max_chars:
            content += "\n...(truncated, file exceeds max_chars)"
        return content
    except Exception as e:
        return f"Error reading file {file_path}: {e}"


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

