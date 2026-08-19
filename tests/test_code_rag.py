"""Tests for AST-Aware Code RAG & Hybrid Codebase Search."""

import time
from pathlib import Path

from memory.code_rag import CodebaseIndexStore, chunk_code_file
from orchestrator.tools.native import dev_tools


def test_chunk_python_file(tmp_path: Path):
    sample_py = tmp_path / "service.py"
    sample_py.write_text(
        '''"""Authentication Service Module."""

class AuthService:
    """Handles user login and token generation."""

    def login(self, username: str, password_hash: str) -> bool:
        """Authenticate user credentials."""
        return True

    async def verify_jwt_token(self, token: str) -> dict:
        """Decode and validate a JWT access token."""
        return {"sub": "123"}


def hash_password(plain_text: str) -> str:
    """Compute SHA-256 password hash."""
    return "hashed"
''',
        encoding="utf-8",
    )

    chunks = chunk_code_file(sample_py)
    symbols = {c.symbol_name: c for c in chunks}

    assert "AuthService" in symbols
    assert symbols["AuthService"].symbol_type == "class"
    assert "AuthService.login" in symbols
    assert symbols["AuthService.login"].symbol_type == "method"
    assert "AuthService.verify_jwt_token" in symbols
    assert "hash_password" in symbols
    assert symbols["hash_password"].symbol_type == "function"
    assert symbols["hash_password"].start_line >= 14


def test_index_and_search_codebase(tmp_path: Path):
    db_file = tmp_path / "test_code_rag.db"
    store = CodebaseIndexStore(db_path=db_file)

    auth_py = tmp_path / "auth.py"
    auth_py.write_text(
        '''class TokenManager:
    """Manages OAuth2 session revocation and refresh tokens."""

    def revoke_token(self, token_id: str) -> None:
        """Revoke an active refresh token in database."""
        pass
''',
        encoding="utf-8",
    )

    files_indexed, chunk_count = store.index_directory(tmp_path)
    assert files_indexed >= 1
    assert chunk_count >= 2

    # Search for conceptual question
    res = store.search("how to revoke session refresh tokens", root_path=tmp_path, top_k=3)
    assert len(res) >= 1
    assert "TokenManager" in res[0]["symbol_name"] or "revoke_token" in res[0]["symbol_name"]
    assert "revoke_token" in res[0]["code_body"]


def test_search_codebase_native_tool(tmp_path: Path):
    calc_py = tmp_path / "calculator.py"
    calc_py.write_text(
        '''def calculate_compound_interest(principal: float, rate: float, years: int) -> float:
    """Compute annualized compound interest with periodic compounding."""
    return principal * ((1 + rate) ** years)
''',
        encoding="utf-8",
    )

    res = dev_tools.search_codebase("compound interest calculation", path=str(tmp_path), top_k=2)
    assert "Code RAG Search Results" in res
    assert "calculate_compound_interest" in res
    assert "principal" in res


def test_code_rag_latency_benchmark(tmp_path: Path):
    db_file = tmp_path / "bench_code_rag.db"
    store = CodebaseIndexStore(db_path=db_file)

    # Create 10 source files
    for i in range(10):
        f = tmp_path / f"module_{i}.py"
        f.write_text(
            f'''class Handler_{i}:
    """Handler for component {i}."""
    def process_{i}(self, data: dict) -> None:
        pass
''',
            encoding="utf-8",
        )

    store.index_directory(tmp_path)

    start = time.perf_counter()
    res = store.search("process component handler 5", root_path=tmp_path, top_k=5)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len(res) > 0
    assert elapsed_ms < 30.0, f"Query took too long: {elapsed_ms:.2f}ms"

