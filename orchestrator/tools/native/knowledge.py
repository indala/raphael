"""Knowledge Base tools — list and read local knowledge files."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_knowledge_files",
                "description": "List all markdown guide files available in the local knowledge base directory.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_knowledge_file",
                "description": "Read the contents of a specific markdown guide file from the knowledge base directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "The name of the markdown file to read (e.g., 'winget_packages.md' or 'windows_cli.md').",
                        }
                    },
                    "required": ["filename"],
                },
            },
        },
    ]


def list_knowledge_files() -> list[str]:
    """Return a list of all markdown files in the knowledge directory."""
    try:
        if not KNOWLEDGE_DIR.exists():
            return []
        files = [f.name for f in KNOWLEDGE_DIR.iterdir() if f.is_file() and f.suffix == ".md"]
        return sorted(files)
    except Exception as e:
        return [f"Error listing knowledge files: {e}"]


def read_knowledge_file(filename: str) -> str:
    """Read and return the text content of a specific knowledge file. Prevent directory traversal."""
    try:
        # Prevent traversal by keeping only the basename
        clean_name = os.path.basename(filename)
        file_path = KNOWLEDGE_DIR / clean_name

        if not file_path.exists():
            return f"Error: Knowledge file '{clean_name}' not found."

        if not file_path.is_file() or file_path.suffix != ".md":
            return "Error: Invalid knowledge file request."

        content = file_path.read_text(encoding="utf-8")
        return content
    except Exception as e:
        return f"Error reading knowledge file '{filename}': {e}"
