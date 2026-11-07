"""Unit and integration tests for AST parsing, chunk context enrichment, and API routes."""

import pytest
from fastapi.testclient import TestClient

from src.core.models import (
    ChunkType,
    IngestedFile,
    IngestionSourceType,
    LanguageEnum,
    RepositorySummary,
)
from src.main import app
from src.parser.chunker import ContextPreparationEngine
from src.parser.js_ts_parser import JsTsParser
from src.parser.python_parser import PythonASTParser


def test_python_parser_classes_and_methods():
    parser = PythonASTParser()
    code = (
        "import os\n"
        "from typing import Optional\n\n"
        "class AuthService:\n"
        "    \"\"\"Authentication service handling sessions.\"\"\"\n"
        "    def __init__(self, secret: str):\n"
        "        self.secret = secret\n\n"
        "    def verify_token(self, token: str) -> bool:\n"
        "        \"\"\"Verify token validity.\"\"\"\n"
        "        return token == self.secret\n"
    )

    chunks = parser.parse_code(code, "services/auth.py", "services/auth.py")
    assert len(chunks) == 3

    # Check class chunk
    class_chunk = next(c for c in chunks if c.chunk_type == ChunkType.class_)
    assert class_chunk.name == "AuthService"
    assert class_chunk.start_line == 4
    assert class_chunk.end_line == 11
    assert "class AuthService" in class_chunk.signature
    assert "Authentication service" in (class_chunk.docstring or "")
    assert "import os" in class_chunk.imports

    # Check method chunks
    init_method = next(c for c in chunks if c.name == "__init__")
    assert init_method.chunk_type == ChunkType.method
    assert init_method.parent_scope == "AuthService"
    assert init_method.start_line == 6

    verify_method = next(c for c in chunks if c.name == "verify_token")
    assert verify_method.chunk_type == ChunkType.method
    assert verify_method.parent_scope == "AuthService"
    assert "token: str" in verify_method.signature
    assert "-> bool" in verify_method.signature
    assert "Verify token validity." in (verify_method.docstring or "")


def test_python_parser_functions_and_async():
    parser = PythonASTParser()
    code = (
        "async def fetch_data(url: str, timeout: int = 30) -> dict:\n"
        "    \"\"\"Fetch remote data asynchronously.\"\"\"\n"
        "    return {'status': 'ok'}\n\n"
        "def compute_hash(data: bytes) -> str:\n"
        "    return data.hex()\n"
    )

    chunks = parser.parse_code(code, "utils/net.py", "utils/net.py")
    assert len(chunks) == 2

    async_fn = next(c for c in chunks if c.name == "fetch_data")
    assert async_fn.chunk_type == ChunkType.function
    assert "async def fetch_data" in async_fn.signature
    assert async_fn.start_line == 1
    assert async_fn.end_line == 3
    assert "Fetch remote data asynchronously." in (async_fn.docstring or "")

    sync_fn = next(c for c in chunks if c.name == "compute_hash")
    assert sync_fn.chunk_type == ChunkType.function
    assert "def compute_hash" in sync_fn.signature
    assert sync_fn.start_line == 5
    assert sync_fn.end_line == 6


def test_python_parser_decorators_and_docstrings():
    parser = PythonASTParser()
    code = (
        "@router.post('/login')\n"
        "@limiter.limit('5/minute')\n"
        "def login_handler(credentials: dict):\n"
        "    \"\"\"Login endpoint.\"\"\"\n"
        "    return {'token': 'jwt'}\n"
    )

    chunks = parser.parse_code(code, "api.py", "api.py")
    assert len(chunks) == 1
    fn = chunks[0]
    assert fn.name == "login_handler"
    # Decorator included in start_line
    assert fn.start_line == 1
    assert fn.end_line == 5
    assert "@router.post('/login')" in fn.code


def test_python_parser_imports_and_standalone():
    parser = PythonASTParser()
    code = (
        "import sys\n"
        "import logging\n\n"
        "logger = logging.getLogger(__name__)\n"
        "DEBUG_MODE = True\n"
    )

    chunks = parser.parse_code(code, "config.py", "config.py")
    assert len(chunks) == 1
    block = chunks[0]
    assert block.chunk_type == ChunkType.standalone_block
    assert block.start_line == 4
    assert block.end_line == 5
    assert "import sys" in block.imports
    assert "import logging" in block.imports


def test_python_parser_syntax_fallback():
    parser = PythonASTParser()
    # Code with syntax error
    invalid_code = (
        "def broken_function(\n"
        "    this is invalid syntax !!!\n"
        "    return 42\n"
    )

    chunks = parser.parse_code(invalid_code, "broken.py", "broken.py")
    assert len(chunks) >= 1
    assert chunks[0].chunk_type == ChunkType.standalone_block
    assert "Syntax fallback" in (chunks[0].docstring or "")


def test_js_ts_parser_functions_and_arrows():
    parser = JsTsParser()
    ts_code = (
        "import { Request, Response } from 'express';\n\n"
        "export async function handleRequest(req: Request, res: Response): Promise<void> {\n"
        "  res.send('ok');\n"
        "}\n\n"
        "export const calculateSum = (a: number, b: number): number => {\n"
        "  return a + b;\n"
        "};\n"
    )

    chunks = parser.parse_code(ts_code, "handlers.ts", "handlers.ts", LanguageEnum.typescript)
    assert len(chunks) == 2

    fn_chunk = next(c for c in chunks if c.name == "handleRequest")
    assert fn_chunk.chunk_type == ChunkType.function
    assert fn_chunk.start_line == 3
    assert fn_chunk.end_line == 5
    assert "handleRequest" in fn_chunk.signature

    arrow_chunk = next(c for c in chunks if c.name == "calculateSum")
    assert arrow_chunk.chunk_type == ChunkType.function
    assert arrow_chunk.start_line == 7
    assert arrow_chunk.end_line == 9
    assert "calculateSum" in arrow_chunk.signature


def test_js_ts_parser_classes_and_methods():
    parser = JsTsParser()
    code = (
        "/** Base repository */\n"
        "export class BaseRepo {\n"
        "  /** Find item by ID */\n"
        "  async findById(id: string) {\n"
        "    return null;\n"
        "  }\n\n"
        "  delete(id: string) {\n"
        "    return true;\n"
        "  }\n"
        "}\n"
    )

    chunks = parser.parse_code(code, "repo.js", "repo.js", LanguageEnum.javascript)
    assert len(chunks) == 3

    cls_chunk = next(c for c in chunks if c.chunk_type == ChunkType.class_)
    assert cls_chunk.name == "BaseRepo"
    assert cls_chunk.start_line == 2
    assert cls_chunk.end_line == 11
    assert "Base repository" in (cls_chunk.docstring or "")

    find_method = next(c for c in chunks if c.name == "findById")
    assert find_method.chunk_type == ChunkType.method
    assert find_method.parent_scope == "BaseRepo"
    assert find_method.start_line == 4
    assert find_method.end_line == 6
    assert "Find item by ID" in (find_method.docstring or "")


def test_js_ts_parser_jsx_and_imports():
    parser = JsTsParser()
    jsx_code = (
        "import React, { useState } from 'react';\n"
        "const logger = require('./logger');\n\n"
        "export const Button = ({ label, onClick }) => {\n"
        "  return <button onClick={onClick}>{label}</button>;\n"
        "};\n"
    )

    chunks = parser.parse_code(jsx_code, "Button.jsx", "Button.jsx", LanguageEnum.javascript)
    assert len(chunks) == 1
    assert chunks[0].name == "Button"
    assert any("react" in imp for imp in chunks[0].imports)
    assert any("require" in imp for imp in chunks[0].imports)


def test_context_preparation_token_estimation():
    engine = ContextPreparationEngine()
    assert engine.estimate_tokens("") == 0
    assert engine.estimate_tokens("abcd") == 1
    assert engine.estimate_tokens("a" * 100) == 25


def test_context_preparation_enrichment():
    engine = ContextPreparationEngine(context_padding_lines=2)
    source = (
        "import sys\n"
        "# Comment 1\n"
        "# Comment 2\n"
        "def target_func():\n"
        "    return 42\n"
        "# Following 1\n"
        "# Following 2\n"
    )
    file = IngestedFile(
        file_path="mod.py",
        relative_path="mod.py",
        language=LanguageEnum.python,
        content=source,
        line_count=7,
        size_bytes=len(source),
    )

    chunks = engine.prepare_file_context(file)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.context_lines is not None
    assert "Preceding Context:" in chunk.context_lines
    assert "Following Context:" in chunk.context_lines
    assert "import sys" in chunk.context_lines


def test_context_preparation_file_and_repo():
    engine = ContextPreparationEngine()

    py_file = IngestedFile(
        file_path="/repo/math.py",
        relative_path="math.py",
        language=LanguageEnum.python,
        content="def add(a: int, b: int) -> int:\n    return a + b\n",
        line_count=2,
        size_bytes=45,
    )

    ts_file = IngestedFile(
        file_path="/repo/greet.ts",
        relative_path="greet.ts",
        language=LanguageEnum.typescript,
        content="export const greet = (name: string): string => {\n  return `Hello, ${name}`;\n};\n",
        line_count=3,
        size_bytes=70,
    )

    summary = RepositorySummary(
        source_type=IngestionSourceType.local,
        source_path_or_url="/repo",
        total_files=2,
        total_lines=5,
        languages={"python": 2, "typescript": 3},
        manifests=[],
        files=[py_file, ts_file],
    )

    review_context = engine.prepare_repository_context(summary)
    assert review_context.repo_id is not None
    assert review_context.total_chunks == 2
    names = [c.name for c in review_context.chunks]
    assert "add" in names
    assert "greet" in names


def test_context_prepare_api_endpoint():
    client = TestClient(app)

    payload = {
        "source_type": "local",
        "source_path_or_url": "/test/project",
        "total_files": 1,
        "total_lines": 3,
        "languages": {"python": 3},
        "manifests": [],
        "files": [
            {
                "file_path": "/test/project/main.py",
                "relative_path": "main.py",
                "language": "python",
                "content": "def run():\n    return 'success'\n",
                "line_count": 2,
                "size_bytes": 35,
            }
        ],
    }

    response = client.post("/api/v1/context/prepare", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "repo_id" in data
    assert data["total_chunks"] == 1
    assert data["chunks"][0]["name"] == "run"
    assert data["chunks"][0]["language"] == "python"
    assert data["chunks"][0]["chunk_type"] == "function"
