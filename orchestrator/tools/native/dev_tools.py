"""Developer tools — grep search, file finding, git inspection, test and linter execution."""

from __future__ import annotations

import ast
import fnmatch
import os
import re
import subprocess
from pathlib import Path

# Directories and patterns to ignore during file searches
_IGNORED_DIRS = {
    ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__",
    "node_modules", "dist", "build", "bin", "obj", ".venv", "venv", ".idea", ".vscode",
}

_IGNORED_EXTENSIONS = {
    ".exe", ".dll", ".pyd", ".so", ".dylib", ".bin", ".pyc", ".pfx", ".cer",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".wav", ".mp3", ".mp4", ".pdf",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".db", ".sqlite", ".sqlite3",
}

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "grep_search",
                "description": "Search for a text pattern or regular expression across files in a directory tree. Returns matches with file paths and line numbers. Automatically ignores binary files and build caches.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Text or regex pattern to search for",
                        },
                        "path": {
                            "type": "string",
                            "description": "Directory or file path to search within. Defaults to '.' (repo root).",
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": "Glob pattern to filter file names (e.g. '*.py', '*.cs', '*test*'). Defaults to '*'.",
                        },
                        "case_sensitive": {
                            "type": "boolean",
                            "description": "Whether the search is case-sensitive. Default: false.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of matching lines to return. Default: 50.",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "find_files",
                "description": "Find files matching a glob pattern across a directory tree (e.g. '*.py', '*controller*', 'test_*.cs'). Automatically ignores .git, build artifacts, and virtual environments.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "File name pattern or glob to search for (e.g. '*.py', 'Cargo.toml', '*test*')",
                        },
                        "directory": {
                            "type": "string",
                            "description": "Root directory to search within. Defaults to '.'.",
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum directory recursion depth. Default: 6.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of files to return. Default: 50.",
                        },
                    },
                    "required": ["pattern"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_code_outline",
                "description": "Extract an AST structural map of a source code file (classes, methods, functions, docstrings, and line ranges) without loading full file into context. Supports Python, C#, Rust, JS/TS.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the code file (e.g. 'agents/coding_agent.py', 'hybrid/bridge.py')",
                        }
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file_range",
                "description": "Read an exact line slice of a file with line numbers (e.g. lines 40 to 120) to inspect specific functions without consuming excessive context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "1-based start line number. Default: 1.",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "1-based end line number. Default: 100.",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "git_status",
                "description": "Inspect git repository status: current branch, staged changes, unstaged modified files, and untracked files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Path to the git repository. Defaults to '.'.",
                        }
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "git_diff",
                "description": "Inspect git diff of modified files or staged changes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Path to the git repository. Defaults to '.'.",
                        },
                        "staged": {
                            "type": "boolean",
                            "description": "If true, show staged changes (git diff --staged). Default: false.",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Optional specific file to view diff for.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_tests",
                "description": "Run automated test suites (pytest, cargo test, dotnet test, npm test) with structured output and failure reports.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "test_path": {
                            "type": "string",
                            "description": "Optional specific test file, directory, or test name (e.g. 'tests/test_smoke.py').",
                        },
                        "framework": {
                            "type": "string",
                            "description": "Test runner framework: 'auto' (detects), 'pytest', 'cargo', 'dotnet', 'npm'. Default: 'auto'.",
                        },
                        "timeout_s": {
                            "type": "integer",
                            "description": "Execution timeout in seconds. Default: 60.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "count_lines_of_code",
                "description": "Count physical lines of code, comments, and blank lines across files or directories grouped by programming language (like cloc).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File or directory path to analyze. Defaults to '.'.",
                        },
                        "extension_filter": {
                            "type": "string",
                            "description": "Optional comma-separated extensions to include (e.g. '.py,.ts,.cs').",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "tree_directory",
                "description": "Generate a visual ASCII tree hierarchy of a directory structure with depth controls and gitignore exclusions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Root directory path. Defaults to '.'.",
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum tree depth. Default: 3.",
                        },
                        "show_hidden": {
                            "type": "boolean",
                            "description": "If true, include hidden files/folders. Default: false.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_json",
                "description": "Extract and inspect specific fields from JSON or YAML files using dot-path notation (e.g. 'scripts.build', 'dependencies.react', 'servers[0].url') without reading huge JSON files into context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the JSON or YAML file",
                        },
                        "json_path": {
                            "type": "string",
                            "description": "Optional dot-path or bracket path to extract (e.g. 'dependencies', 'scripts.test'). Omit to get top-level keys.",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_linter",
                "description": "Run code linters, syntax checks, or type checkers (ruff, mypy, dotnet build) on files or projects.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File or directory path to lint. Defaults to '.'.",
                        },
                        "linter": {
                            "type": "string",
                            "description": "Linter tool: 'auto' (detects), 'ruff', 'mypy', 'dotnet'. Default: 'auto'.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scan_secrets",
                "description": "Scan codebase or files for hardcoded secrets, API keys (OpenAI, AWS, Google, Anthropic), private keys, and passwords (like gitleaks/trufflehog).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory or file path to scan. Defaults to '.'.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_codebase",
                "description": "Semantic AST-aware Code RAG search across classes, methods, functions, and docstrings in the codebase. Combines BM25 and SIMD vector embeddings to find relevant code implementations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language or technical question/symbol to search for (e.g. 'how is audio RMS calculated', 'session manager', 'token verification')",
                        },
                        "path": {
                            "type": "string",
                            "description": "Root directory or file to search within. Defaults to '.'.",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of top matching code chunks to return. Default: 5.",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "index_codebase",
                "description": "Synchronize or rebuild the semantic Code RAG index for a repository. Automatically parses AST and vectorizes code.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Root directory to index. Defaults to '.'.",
                        },
                        "force": {
                            "type": "boolean",
                            "description": "If true, force full re-index bypassing timestamp cache. Default: false.",
                        },
                    },
                },
            },
        },
    ]


def grep_search(
    query: str,
    path: str = ".",
    file_pattern: str = "*",
    case_sensitive: bool = False,
    max_results: int = 50,
) -> str:
    """Search for text or regex pattern in files."""
    if not query:
        return "Please provide a non-empty search query."

    root_path = Path(path).resolve()
    if not root_path.exists():
        return f"Path does not exist: {path}"

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(query, flags)
    except re.error as e:
        return f"Invalid regex query '{query}': {e}"

    results = []
    files_searched = 0

    if root_path.is_file():
        file_list = [root_path]
    else:
        file_list = []
        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS and not d.startswith(".")]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in _IGNORED_EXTENSIONS:
                    continue
                if fnmatch.fnmatch(file, file_pattern):
                    file_list.append(Path(root) / file)

    for file_path in file_list:
        files_searched += 1
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                for line_no, line in enumerate(f, start=1):
                    if regex.search(line):
                        rel_path = file_path.relative_to(root_path) if root_path.is_dir() else file_path.name
                        clean_line = line.rstrip("\r\n")
                        if len(clean_line) > 150:
                            clean_line = clean_line[:147] + "..."
                        results.append(f"{rel_path}:{line_no}: {clean_line}")
                        if len(results) >= max_results:
                            break
        except (OSError, PermissionError):
            continue

        if len(results) >= max_results:
            break

    if not results:
        return f"No matches found for '{query}' across {files_searched} file(s)."

    header = f"Found {len(results)} match(es) across {files_searched} file(s)"
    if len(results) >= max_results:
        header += f" (capped at {max_results})"
    header += ":\n"
    return header + "\n".join(results)


def find_files(
    pattern: str,
    directory: str = ".",
    max_depth: int = 6,
    max_results: int = 50,
) -> str:
    """Find files matching glob pattern."""
    if not pattern:
        return "Please provide a file search pattern (e.g. '*.py')."

    root_path = Path(directory).resolve()
    if not root_path.exists():
        return f"Directory does not exist: {directory}"

    matches = []
    root_depth = len(root_path.parts)

    for root, dirs, files in os.walk(root_path):
        current_path = Path(root)
        current_depth = len(current_path.parts) - root_depth
        if current_depth > max_depth:
            dirs.clear()
            continue

        dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS and not d.startswith(".")]

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in _IGNORED_EXTENSIONS and pattern != f"*{ext}":
                continue
            if fnmatch.fnmatch(file, pattern) or fnmatch.fnmatch(file.lower(), pattern.lower()):
                rel = current_path.relative_to(root_path) / file
                matches.append(str(rel).replace("\\", "/"))
                if len(matches) >= max_results:
                    break

        if len(matches) >= max_results:
            break

    if not matches:
        return f"No files found matching '{pattern}' under '{directory}'."

    summary = f"Found {len(matches)} file(s)"
    if len(matches) >= max_results:
        summary += f" (capped at {max_results})"
    summary += ":\n"
    return summary + "\n".join(f"  • {m}" for m in matches)


def git_status(repo_path: str = ".") -> str:
    """Inspect git repository status."""
    path = Path(repo_path).resolve()
    try:
        branch_res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=path, capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW
        )
        status_res = subprocess.run(
            ["git", "status", "--short"],
            cwd=path, capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return f"Git command failed: {e}"

    if status_res.returncode != 0:
        return f"Not a git repository or git error: {status_res.stderr.strip()}"

    branch = branch_res.stdout.strip() or "HEAD (detached)"
    status_out = status_res.stdout.strip()

    if not status_out:
        return f"Git branch: {branch}\nWorking tree clean (no modified or untracked files)."

    lines = status_out.splitlines()
    return f"Git branch: {branch}\nChanges ({len(lines)} file(s)):\n" + status_out


def git_diff(repo_path: str = ".", staged: bool = False, file_path: str = "") -> str:
    """Inspect git diff."""
    path = Path(repo_path).resolve()
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--staged")
    if file_path:
        cmd.append(file_path)

    try:
        res = subprocess.run(
            cmd, cwd=path, capture_output=True, text=True, timeout=15, creationflags=_NO_WINDOW
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return f"Git diff failed: {e}"

    if res.returncode != 0:
        return f"Git diff error: {res.stderr.strip()}"

    diff_text = res.stdout.strip()
    if not diff_text:
        target = "staged" if staged else "unstaged"
        return f"No {target} changes found."

    if len(diff_text) > 4000:
        return diff_text[:3900] + f"\n\n... [Truncated {len(diff_text) - 3900} remaining characters]"
    return diff_text


def run_tests(test_path: str = "", framework: str = "auto", timeout_s: int = 60) -> str:
    """Run test suite."""
    fw = framework.lower().strip()
    cmd = []

    if fw in ("auto", "pytest") and (Path("pytest.ini").exists() or Path("pyproject.toml").exists() or Path("tests").exists()):
        cmd = ["python", "-m", "pytest", "-v", "--tb=short"]
        if test_path:
            cmd.append(test_path)
    elif fw in ("auto", "cargo") and Path("Cargo.toml").exists():
        cmd = ["cargo", "test"]
        if test_path:
            cmd.append(test_path)
    elif fw in ("auto", "dotnet") and list(Path(".").glob("*.sln")) + list(Path(".").glob("**/*.csproj")):
        cmd = ["dotnet", "test"]
        if test_path:
            cmd.append(test_path)
    else:
        cmd = ["python", "-m", "pytest", "-v", "--tb=short"]
        if test_path:
            cmd.append(test_path)

    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s, creationflags=_NO_WINDOW
        )
    except subprocess.TimeoutExpired:
        return f"Tests timed out after {timeout_s}s: {' '.join(cmd)}"
    except Exception as e:
        return f"Failed to execute test runner: {e}"

    output = (res.stdout + "\n" + res.stderr).strip()
    status_str = "PASSED" if res.returncode == 0 else f"FAILED (exit code {res.returncode})"
    return f"Test Run [{status_str}]: {' '.join(cmd)}\n\n{output}"


def run_linter(path: str = ".", linter: str = "auto") -> str:
    """Run linter / static analysis."""
    lt = linter.lower().strip()
    cmd = []

    if lt in ("auto", "ruff"):
        cmd = ["ruff", "check", path]
    elif lt == "mypy":
        cmd = ["mypy", path]
    elif lt == "dotnet":
        cmd = ["dotnet", "build"]
    else:
        cmd = ["ruff", "check", path]

    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, creationflags=_NO_WINDOW
        )
    except FileNotFoundError:
        return f"Linter tool '{cmd[0]}' not found on PATH."
    except Exception as e:
        return f"Failed to execute linter: {e}"

    output = (res.stdout + "\n" + res.stderr).strip()
    status_str = "CLEAN" if res.returncode == 0 else f"ISSUES FOUND (exit code {res.returncode})"
    return f"Linter [{status_str}]: {' '.join(cmd)}\n\n{output}"


def get_code_outline(file_path: str) -> str:
    """Extract AST structural outline (classes, functions, methods, line ranges) from a source file."""
    path = Path(file_path).resolve()
    if not path.exists() or not path.is_file():
        return f"File does not exist: {file_path}"

    ext = path.suffix.lower()
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Failed to read file '{file_path}': {e}"

    if ext == ".py":
        try:
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as e:
            return f"Python syntax error in '{file_path}': {e}"

        lines = [f"Code Outline for {path.name} ({len(content.splitlines())} lines):"]
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                bases = [ast.unparse(b) for b in node.bases]
                base_str = f"({', '.join(bases)})" if bases else ""
                end_lineno = getattr(node, "end_lineno", node.lineno)
                lines.append(f"\n• class {node.name}{base_str} [lines {node.lineno}-{end_lineno}]:")
                doc = ast.get_docstring(node)
                if doc:
                    lines.append(f"    \"\"\"{doc.splitlines()[0][:80]}\"\"\"")
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                        args = [a.arg for a in item.args.args]
                        ret = f" -> {ast.unparse(item.returns)}" if item.returns else ""
                        item_end = getattr(item, "end_lineno", item.lineno)
                        lines.append(f"    - {prefix} {item.name}({', '.join(args)}){ret} [lines {item.lineno}-{item_end}]")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                args = [a.arg for a in node.args.args]
                ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                end_lineno = getattr(node, "end_lineno", node.lineno)
                lines.append(f"• {prefix} {node.name}({', '.join(args)}){ret} [lines {node.lineno}-{end_lineno}]")
                doc = ast.get_docstring(node)
                if doc:
                    lines.append(f"    \"\"\"{doc.splitlines()[0][:80]}\"\"\"")
        return "\n".join(lines) if len(lines) > 1 else f"No top-level classes or functions found in {path.name}."

    # Generic regex parser for other languages (.cs, .rs, .js, .ts, .go, .cpp)
    lines = [f"Code Symbols for {path.name} ({len(content.splitlines())} lines):"]
    symbol_regex = re.compile(
        r"^(?:\s*(?:pub\s+|public\s+|private\s+|protected\s+|static\s+|async\s+|export\s+|fn\s+|function\s+|class\s+|struct\s+|interface\s+|enum\s+)+)+([\w_]+)",
        re.MULTILINE
    )
    for line_no, line in enumerate(content.splitlines(), start=1):
        clean = line.strip()
        if symbol_regex.match(clean):
            lines.append(f"• line {line_no}: {clean[:100]}")
    return "\n".join(lines) if len(lines) > 1 else f"No symbol declarations found in {path.name}."


def read_file_range(file_path: str, start_line: int = 1, end_line: int = 100) -> str:
    """Read a specific slice of lines from a file with 1-based line numbering."""
    path = Path(file_path).resolve()
    if not path.exists() or not path.is_file():
        return f"File does not exist: {file_path}"

    if start_line < 1:
        start_line = 1
    if end_line < start_line:
        end_line = start_line + 50
    if end_line - start_line > 500:
        end_line = start_line + 500  # Cap at 500 lines per call to prevent memory/token exhaustion

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except Exception as e:
        return f"Failed to read file '{file_path}': {e}"

    total_lines = len(all_lines)
    if start_line > total_lines:
        return f"Start line {start_line} exceeds total file length ({total_lines} lines)."

    actual_end = min(end_line, total_lines)
    selected = all_lines[start_line - 1:actual_end]

    header = f"[{path.name} lines {start_line}-{actual_end} of {total_lines}]\n"
    numbered = [f"{start_line + i:4d}: {line.rstrip()}" for i, line in enumerate(selected)]
    return header + "\n".join(numbered)


_LANG_EXTENSIONS = {
    ".py": "Python", ".rs": "Rust", ".cs": "C#", ".js": "JavaScript", ".jsx": "JavaScript (JSX)",
    ".ts": "TypeScript", ".tsx": "TypeScript (TSX)", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".json": "JSON", ".toml": "TOML", ".yaml": "YAML", ".yml": "YAML", ".md": "Markdown",
    ".c": "C", ".cpp": "C++", ".h": "C/C++ Header", ".hpp": "C++ Header", ".go": "Go",
    ".sh": "Shell", ".ps1": "PowerShell", ".sql": "SQL", ".xml": "XML",
}

_COMMENT_STARTS = {
    "Python": ("#",), "Shell": ("#",), "PowerShell": ("#",), "YAML": ("#",), "TOML": ("#",),
    "C": ("//", "/*", "*"), "C++": ("//", "/*", "*"), "C/C++ Header": ("//", "/*", "*"), "C++ Header": ("//", "/*", "*"),
    "C#": ("//", "/*", "*"), "Rust": ("//", "/*", "*"), "Go": ("//", "/*", "*"),
    "JavaScript": ("//", "/*", "*"), "JavaScript (JSX)": ("//", "/*", "*"),
    "TypeScript": ("//", "/*", "*"), "TypeScript (TSX)": ("//", "/*", "*"),
    "HTML": ("<!--",), "XML": ("<!--",), "Markdown": ("<!--",), "CSS": ("/*", "*"), "SCSS": ("//", "/*", "*"),
    "SQL": ("--", "/*", "*"),
}


def count_lines_of_code(path: str = ".", extension_filter: str = "") -> str:
    """Count physical lines, comments, and blanks by programming language (like cloc)."""
    root = Path(path).resolve()
    if not root.exists():
        return f"Path does not exist: {path}"

    ext_filter = {e.strip().lower() if e.strip().startswith(".") else f".{e.strip().lower()}"
                  for e in extension_filter.split(",") if e.strip()} if extension_filter else None

    # stats: {lang: [files, blank, comment, code]}
    stats: dict[str, list[int]] = {}

    target_files = [root] if root.is_file() else []
    if root.is_dir():
        for r, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS and not d.startswith(".")]
            for f in files:
                target_files.append(Path(r) / f)

    for fpath in target_files:
        ext = fpath.suffix.lower()
        if ext_filter and ext not in ext_filter:
            continue
        if ext in _IGNORED_EXTENSIONS:
            continue
        lang = _LANG_EXTENSIONS.get(ext)
        if not lang:
            continue

        if lang not in stats:
            stats[lang] = [0, 0, 0, 0]
        stats[lang][0] += 1

        comm_prefixes = _COMMENT_STARTS.get(lang, ("#", "//"))
        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        stats[lang][1] += 1
                    elif any(stripped.startswith(cp) for cp in comm_prefixes):
                        stats[lang][2] += 1
                    else:
                        stats[lang][3] += 1
        except Exception:
            continue

    if not stats:
        return f"No recognized source code files found in '{path}'."

    # Format table
    header = f"{'Language':<20} {'Files':>8} {'Blank':>10} {'Comment':>10} {'Code':>10}"
    sep = "-" * len(header)
    lines = [f"Code Metrics for '{path}':", sep, header, sep]

    tot_files = tot_blank = tot_comment = tot_code = 0
    for lang, (fc, bl, cm, cd) in sorted(stats.items(), key=lambda x: x[1][3], reverse=True):
        lines.append(f"{lang:<20} {fc:>8} {bl:>10} {cm:>10} {cd:>10}")
        tot_files += fc
        tot_blank += bl
        tot_comment += cm
        tot_code += cd

    lines.append(sep)
    lines.append(f"{'SUM:':<20} {tot_files:>8} {tot_blank:>10} {tot_comment:>10} {tot_code:>10}")
    lines.append(sep)
    return "\n".join(lines)


def tree_directory(path: str = ".", max_depth: int = 3, show_hidden: bool = False) -> str:
    """Generate a clean visual ASCII directory tree."""
    root = Path(path).resolve()
    if not root.exists():
        return f"Path does not exist: {path}"
    if not root.is_dir():
        return f"Path is a file: {path}"

    lines = [f"{root.name}/"]
    dir_count = 0
    file_count = 0

    def _build_tree(curr_dir: Path, prefix: str, depth: int):
        nonlocal dir_count, file_count
        if depth > max_depth:
            return

        try:
            entries = sorted(curr_dir.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        if not show_hidden:
            entries = [e for e in entries if not e.name.startswith(".") and e.name not in _IGNORED_DIRS]

        for i, entry in enumerate(entries):
            is_last = (i == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "

            if entry.is_dir():
                dir_count += 1
                lines.append(f"{prefix}{connector}{entry.name}/")
                _build_tree(entry, prefix + child_prefix, depth + 1)
            else:
                file_count += 1
                size_str = f" ({round(entry.stat().st_size / 1024, 1)} KB)" if entry.stat().st_size > 0 else ""
                lines.append(f"{prefix}{connector}{entry.name}{size_str}")

    _build_tree(root, "", 1)
    lines.append(f"\n{dir_count} directories, {file_count} files (max depth: {max_depth})")
    return "\n".join(lines)


def query_json(file_path: str, json_path: str = "") -> str:
    """Extract and inspect specific fields from JSON or YAML files using dot notation."""
    import json
    path = Path(file_path).resolve()
    if not path.exists() or not path.is_file():
        return f"File does not exist: {file_path}"

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return f"Failed to parse JSON in '{file_path}': {e}"
    except Exception as e:
        return f"Error reading '{file_path}': {e}"

    if not json_path or not json_path.strip():
        if isinstance(data, dict):
            keys = list(data.keys())
            return f"Top-level keys in {path.name} ({len(keys)}):\n" + "\n".join(f"  • {k}" for k in keys[:50])
        elif isinstance(data, list):
            return f"Array with {len(data)} items in {path.name}."
        return json.dumps(data, indent=2)[:2000]

    # Evaluate dot-path (e.g. 'scripts.test' or 'dependencies.react')
    curr = data
    parts = re.split(r"\.|\/|\[|\]", json_path)
    parts = [p for p in parts if p]

    for p in parts:
        if isinstance(curr, dict):
            if p in curr:
                curr = curr[p]
            else:
                avail = list(curr.keys())[:10]
                return f"Key '{p}' not found in path. Available keys at this level: {', '.join(avail)}"
        elif isinstance(curr, list):
            try:
                idx = int(p)
                curr = curr[idx]
            except (ValueError, IndexError):
                return f"Index '{p}' out of bounds for array with {len(curr)} items."
        else:
            return f"Cannot navigate further into primitive value: {curr}"

    return json.dumps(curr, indent=2, ensure_ascii=False)


_SECRET_PATTERNS = [
    ("OpenAI API Key", re.compile(r"sk-(?:proj-)?[a-zA-Z0-9_\-]{20,}")),
    ("Anthropic API Key", re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}")),
    ("Google API Key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Private Key Header", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("Database URI with Password", re.compile(r"(?:postgres|mysql|mongodb|redis):\/\/[a-zA-Z0-9_\-]+:([a-zA-Z0-9_\-!@#$%^&*]+)@")),
    ("Generic Bearer/Secret", re.compile(r"(?:api_key|secret_key|app_secret|auth_token)\s*[:=]\s*['\"]([a-zA-Z0-9_\-]{16,})['\"]", re.IGNORECASE)),
]


def scan_secrets(path: str = ".") -> str:
    """Scan codebase for exposed credentials, API keys, private keys, and passwords."""
    root = Path(path).resolve()
    if not root.exists():
        return f"Path does not exist: {path}"

    target_files = [root] if root.is_file() else []
    if root.is_dir():
        for r, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS and not d.startswith(".")]
            for f in files:
                ext = Path(f).suffix.lower()
                if ext not in _IGNORED_EXTENSIONS:
                    target_files.append(Path(r) / f)

    findings = []
    scanned_count = 0

    for fpath in target_files:
        scanned_count += 1
        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                for line_no, line in enumerate(f, start=1):
                    for label, pattern in _SECRET_PATTERNS:
                        match = pattern.search(line)
                        if match:
                            rel = fpath.relative_to(root) if root.is_dir() else fpath.name
                            matched_str = match.group(0)
                            redacted = matched_str[:6] + "..." + matched_str[-4:] if len(matched_str) > 10 else "***"
                            findings.append(f"⚠️  [{label}] {rel}:{line_no} -> {redacted}")
        except Exception:
            continue

    if not findings:
        return f"Security Audit Clean: Scanned {scanned_count} file(s) under '{path}'. No hardcoded secrets or API keys detected."

    header = f"Found {len(findings)} potential secret(s) across {scanned_count} file(s):\n"
    return header + "\n".join(findings)


def search_codebase(query: str, path: str = ".", top_k: int = 5) -> str:
    """Semantic AST-aware hybrid code search over codebase functions, classes, and docstrings."""
    from memory.code_rag import search_codebase_rag
    return search_codebase_rag(query, path=path, top_k=top_k)


def index_codebase(path: str = ".", force: bool = False) -> str:
    """Synchronize or rebuild the semantic Code RAG index for a repository."""
    from memory.code_rag import index_codebase_rag
    return index_codebase_rag(path=path, force=force)
