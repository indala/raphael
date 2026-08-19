"""
AST-Aware Code Retrieval-Augmented Generation (Code RAG) engine.

Provides syntax-aware chunking (classes, functions, methods), FTS5 BM25 keyword indexing,
SIMD vector embeddings, incremental caching, and hybrid Reciprocal Rank Fusion search.
"""

from __future__ import annotations

import ast
import contextlib
import logging
import math
import os
import re
import sqlite3
import struct
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.native_core import batch_cosine_similarity, top_k_indices

logger = logging.getLogger(__name__)

# Extensions to index
_CODE_EXTENSIONS = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (TSX)",
    ".js": "JavaScript",
    ".jsx": "JavaScript (JSX)",
    ".cs": "C#",
    ".rs": "Rust",
    ".go": "Go",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
}

_IGNORED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build",
    "bin", "obj", ".idea", ".vscode", ".pytest_cache", ".ruff_cache", ".mypy_cache",
}


@dataclass
class CodeChunk:
    file_path: str
    symbol_name: str
    symbol_type: str  # 'class', 'function', 'async_function', 'method', 'file_slice'
    signature: str
    docstring: str
    code_body: str
    start_line: int
    end_line: int
    language: str


def _vectorize_text(text: str, dim: int = 64) -> list[float]:
    """Compute a deterministic normalized subword/n-gram feature vector using CRC32."""
    if not text:
        return [0.0] * dim

    vec = [0.0] * dim
    tokens = re.findall(r"[a-zA-Z0-9_]+|[\+\-\*/=<>!&|~^\"]", text.lower())
    for tok in tokens:
        idx = zlib.crc32(tok.encode("utf-8")) % dim
        vec[idx] += 1.0
        if len(tok) >= 3:
            for i in range(len(tok) - 2):
                ngram = tok[i : i + 3]
                n_idx = zlib.crc32(ngram.encode("utf-8")) % dim
                vec[n_idx] += 0.5

    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 1e-9:
        return [x / norm for x in vec]
    return vec


def _pack_vector(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack_vector(blob: bytes) -> list[float]:
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


def chunk_code_file(path: Path) -> list[CodeChunk]:
    """Extract semantic code chunks from a source file using AST or regex."""
    if not path.is_file():
        return []

    ext = path.suffix.lower()
    lang = _CODE_EXTENSIONS.get(ext, "Code")
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.debug("Failed to read %s: %s", path, e)
        return []

    all_lines = content.splitlines()
    if not all_lines:
        return []

    chunks: list[CodeChunk] = []

    # ── Python AST Chunking ──────────────────────────────────────────
    if ext == ".py":
        try:
            tree = ast.parse(content, filename=str(path))
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    c_start = getattr(node, "lineno", 1)
                    c_end = getattr(node, "end_lineno", len(all_lines))
                    c_doc = ast.get_docstring(node) or ""
                    bases = [ast.unparse(b) for b in node.bases]
                    base_str = f"({', '.join(bases)})" if bases else ""
                    c_sig = f"class {node.name}{base_str}"
                    c_body = "\n".join(all_lines[c_start - 1 : c_end])

                    chunks.append(
                        CodeChunk(
                            file_path=str(path),
                            symbol_name=node.name,
                            symbol_type="class",
                            signature=c_sig,
                            docstring=c_doc,
                            code_body=c_body,
                            start_line=c_start,
                            end_line=c_end,
                            language=lang,
                        )
                    )

                    # Extract methods as dedicated searchable chunks
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            m_start = getattr(item, "lineno", c_start)
                            m_end = getattr(item, "end_lineno", c_end)
                            m_doc = ast.get_docstring(item) or ""
                            prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                            args = [a.arg for a in item.args.args]
                            ret = f" -> {ast.unparse(item.returns)}" if item.returns else ""
                            m_sig = f"{prefix} {node.name}.{item.name}({', '.join(args)}){ret}"
                            m_body = "\n".join(all_lines[m_start - 1 : m_end])

                            chunks.append(
                                CodeChunk(
                                    file_path=str(path),
                                    symbol_name=f"{node.name}.{item.name}",
                                    symbol_type="method",
                                    signature=m_sig,
                                    docstring=m_doc,
                                    code_body=m_body,
                                    start_line=m_start,
                                    end_line=m_end,
                                    language=lang,
                                )
                            )

                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    f_start = getattr(node, "lineno", 1)
                    f_end = getattr(node, "end_lineno", len(all_lines))
                    f_doc = ast.get_docstring(node) or ""
                    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                    args = [a.arg for a in node.args.args]
                    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                    f_sig = f"{prefix} {node.name}({', '.join(args)}){ret}"
                    f_body = "\n".join(all_lines[f_start - 1 : f_end])

                    chunks.append(
                        CodeChunk(
                            file_path=str(path),
                            symbol_name=node.name,
                            symbol_type="async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                            signature=f_sig,
                            docstring=f_doc,
                            code_body=f_body,
                            start_line=f_start,
                            end_line=f_end,
                            language=lang,
                        )
                    )
            if chunks:
                return chunks
        except SyntaxError:
            pass  # Fall through to line window chunker

    # ── Generic Regex / Window Chunking for Other Languages ─────────
    sym_regex = re.compile(
        r"^(?:\s*(?:pub\s+|public\s+|private\s+|protected\s+|static\s+|async\s+|export\s+|fn\s+|function\s+|class\s+|struct\s+|interface\s+|enum\s+)+)+([\w_]+)",
        re.MULTILINE,
    )

    decl_lines = []
    for line_idx, line in enumerate(all_lines, start=1):
        m = sym_regex.match(line.strip())
        if m:
            decl_lines.append((line_idx, m.group(1), line.strip()[:100]))

    if decl_lines:
        for i, (l_start, s_name, s_sig) in enumerate(decl_lines):
            l_end = decl_lines[i + 1][0] - 1 if i + 1 < len(decl_lines) else len(all_lines)
            l_end = min(l_end, l_start + 150)
            body = "\n".join(all_lines[l_start - 1 : l_end])
            chunks.append(
                CodeChunk(
                    file_path=str(path),
                    symbol_name=s_name,
                    symbol_type="symbol",
                    signature=s_sig,
                    docstring="",
                    code_body=body,
                    start_line=l_start,
                    end_line=l_end,
                    language=lang,
                )
            )
        return chunks

    # Fallback: Sliding window chunk for files with no explicit top-level symbols
    step = 80
    window = 100
    for i in range(0, len(all_lines), step):
        chunk_lines = all_lines[i : i + window]
        if not chunk_lines:
            break
        chunks.append(
            CodeChunk(
                file_path=str(path),
                symbol_name=path.name,
                symbol_type="file_slice",
                signature=f"{path.name} [lines {i+1}-{i+len(chunk_lines)}]",
                docstring="",
                code_body="\n".join(chunk_lines),
                start_line=i + 1,
                end_line=i + len(chunk_lines),
                language=lang,
            )
        )
    return chunks


class CodebaseIndexStore:
    """SQLite + SIMD Vector Codebase Indexer with incremental sync."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            td = Path(tempfile.gettempdir()) / "Raphael"
            td.mkdir(parents=True, exist_ok=True)
            self.db_path = td / "code_rag.db"
        else:
            self.db_path = Path(db_path)

        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_meta (
                    file_path TEXT PRIMARY KEY,
                    mtime REAL,
                    chunk_count INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS code_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT,
                    symbol_name TEXT,
                    symbol_type TEXT,
                    signature TEXT,
                    docstring TEXT,
                    code_body TEXT,
                    start_line INTEGER,
                    end_line INTEGER,
                    language TEXT,
                    vector BLOB
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS code_chunks_fts USING fts5(
                    symbol_name, signature, docstring, code_body, file_path,
                    content='code_chunks', content_rowid='id'
                )
                """
            )
            conn.commit()

    def index_directory(self, root_path: str | Path = ".", force: bool = False) -> tuple[int, int]:
        """Scan and index all code files under root_path incrementally."""
        root = Path(root_path).resolve()
        if not root.exists():
            return (0, 0)

        target_files = [root] if root.is_file() else []
        if root.is_dir():
            for r, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS and not d.startswith(".")]
                for f in files:
                    ext = Path(f).suffix.lower()
                    if ext in _CODE_EXTENSIONS:
                        target_files.append(Path(r) / f)

        indexed_files = 0
        total_chunks = 0

        with self._get_conn() as conn:
            for fpath in target_files:
                str_path = str(fpath)
                try:
                    mtime = fpath.stat().st_mtime
                except Exception:
                    continue

                # Check if already indexed and unchanged
                if not force:
                    row = conn.execute(
                        "SELECT mtime FROM file_meta WHERE file_path = ?", (str_path,)
                    ).fetchone()
                    if row and abs(row["mtime"] - mtime) < 1e-4:
                        continue

                # Delete old chunks for this file
                old_ids = [
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM code_chunks WHERE file_path = ?", (str_path,)
                    ).fetchall()
                ]
                if old_ids:
                    conn.execute("DELETE FROM code_chunks WHERE file_path = ?", (str_path,))
                    for oid in old_ids:
                        conn.execute("DELETE FROM code_chunks_fts WHERE rowid = ?", (oid,))

                chunks = chunk_code_file(fpath)
                if not chunks:
                    conn.execute(
                        "INSERT OR REPLACE INTO file_meta (file_path, mtime, chunk_count) VALUES (?, ?, ?)",
                        (str_path, mtime, 0),
                    )
                    continue

                for c in chunks:
                    embed_text = f"{c.symbol_name} {c.signature} {c.docstring} {c.code_body[:300]}"
                    vec = _vectorize_text(embed_text, dim=64)
                    blob = _pack_vector(vec)

                    cur = conn.execute(
                        """
                        INSERT INTO code_chunks
                        (file_path, symbol_name, symbol_type, signature, docstring, code_body, start_line, end_line, language, vector)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            c.file_path, c.symbol_name, c.symbol_type, c.signature,
                            c.docstring, c.code_body, c.start_line, c.end_line,
                            c.language, blob,
                        ),
                    )
                    row_id = cur.lastrowid
                    conn.execute(
                        """
                        INSERT INTO code_chunks_fts (rowid, symbol_name, signature, docstring, code_body, file_path)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (row_id, c.symbol_name, c.signature, c.docstring, c.code_body, c.file_path),
                    )

                conn.execute(
                    "INSERT OR REPLACE INTO file_meta (file_path, mtime, chunk_count) VALUES (?, ?, ?)",
                    (str_path, mtime, len(chunks)),
                )
                indexed_files += 1
                total_chunks += len(chunks)

            conn.commit()

        return (indexed_files, total_chunks)

    def search(self, query: str, root_path: str | Path | None = None, top_k: int = 5) -> list[dict[str, Any]]:
        """Hybrid Reciprocal Rank Fusion search over indexed codebase chunks."""
        clean_q = re.sub(r"[^a-zA-Z0-9_\s]", " ", query).strip()
        if not clean_q:
            return []

        with self._get_conn() as conn:
            all_chunks = conn.execute(
                "SELECT id, file_path, symbol_name, symbol_type, signature, docstring, code_body, start_line, end_line, language, vector FROM code_chunks"
            ).fetchall()

            if not all_chunks:
                return []

            # 1. FTS5 BM25 Search
            terms = clean_q.split()
            fts_query = " OR ".join(f'"{t}"*' for t in terms if len(t) > 1) or clean_q
            fts_scores: dict[int, int] = {}
            try:
                fts_rows = conn.execute(
                    """
                    SELECT rowid, rank FROM code_chunks_fts
                    WHERE code_chunks_fts MATCH ?
                    ORDER BY rank LIMIT 50
                    """,
                    (fts_query,),
                ).fetchall()
                for rank_idx, r in enumerate(fts_rows):
                    fts_scores[r["rowid"]] = rank_idx
            except Exception as e:
                logger.debug("FTS5 query failed: %s", e)

            # 2. Vector Cosine Search
            q_vec = _vectorize_text(query, dim=64)
            chunk_vectors = [_unpack_vector(r["vector"]) for r in all_chunks]
            similarities = batch_cosine_similarity(q_vec, chunk_vectors)
            top_vector_indices = top_k_indices(similarities, k=min(50, len(all_chunks)))

            vec_scores: dict[int, int] = {}
            for rank_idx, c_idx in enumerate(top_vector_indices):
                vec_scores[all_chunks[c_idx]["id"]] = rank_idx

            # 3. Reciprocal Rank Fusion (RRF)
            all_ids = set(fts_scores.keys()) | set(vec_scores.keys())
            fused: list[tuple[float, dict]] = []

            chunk_map = {r["id"]: r for r in all_chunks}
            for cid in all_ids:
                if cid not in chunk_map:
                    continue
                row = chunk_map[cid]

                # If root_path filter provided, ensure file is inside it
                if root_path:
                    try:
                        Path(row["file_path"]).relative_to(Path(root_path).resolve())
                    except ValueError:
                        continue

                r_bm25 = fts_scores.get(cid, 100)
                r_vec = vec_scores.get(cid, 100)
                score = (1.0 / (60.0 + r_bm25)) + (1.0 / (60.0 + r_vec))

                fused.append((score, dict(row)))

            fused.sort(key=lambda x: x[0], reverse=True)
            return [item[1] for item in fused[:top_k]]


# Module-level singleton
_default_store: CodebaseIndexStore | None = None


def get_code_rag_store() -> CodebaseIndexStore:
    global _default_store
    if _default_store is None:
        _default_store = CodebaseIndexStore()
    return _default_store


def search_codebase_rag(query: str, path: str = ".", top_k: int = 5) -> str:
    """Public API: Index on-demand and search the codebase."""
    store = get_code_rag_store()
    root = Path(path).resolve()
    # Fast incremental sync before search
    store.index_directory(root)

    results = store.search(query, root_path=root, top_k=top_k)
    if not results:
        return f"No matching code symbols or implementations found for query: '{query}' in '{path}'."

    lines = [f"=== Code RAG Search Results for '{query}' ({len(results)} matches) ===\n"]
    for i, r in enumerate(results, start=1):
        fpath = Path(r["file_path"])
        rel_path = fpath.name
        with contextlib.suppress(Exception):
            rel_path = str(fpath.relative_to(root))

        lines.append(
            f"--- Match #{i}: {r['symbol_type'].upper()} {r['symbol_name']} in {rel_path}:{r['start_line']}-{r['end_line']} ---"
        )
        if r["signature"]:
            lines.append(f"Signature: {r['signature']}")
        if r["docstring"]:
            doc_snip = r["docstring"].strip().splitlines()[0][:120]
            lines.append(f"Doc: \"{doc_snip}\"")

        lines.append("```" + r.get("language", "").lower())
        # Trim code body to max 40 lines to avoid token exhaustion
        code_lines = r["code_body"].splitlines()
        if len(code_lines) > 40:
            lines.append("\n".join(code_lines[:40]))
            lines.append(f"... ({len(code_lines) - 40} lines truncated)")
        else:
            lines.append(r["code_body"])
        lines.append("```\n")

    return "\n".join(lines)


def index_codebase_rag(path: str = ".", force: bool = False) -> str:
    """Public API: Force re-index or synchronize codebase index."""
    store = get_code_rag_store()
    root = Path(path).resolve()
    files_count, chunk_count = store.index_directory(root, force=force)
    mode = "Re-indexed" if force else "Synchronized"
    return f"Code RAG: {mode} {files_count} file(s) generating {chunk_count} semantic code chunk(s) under '{path}'."

