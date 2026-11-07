"""Context preparation engine enriching AST chunks with contextual scope and token metrics."""

import hashlib
import logging
from pathlib import Path
from typing import List, Optional

from src.core.models import (
    ChunkType,
    CodeChunk,
    IngestedFile,
    LanguageEnum,
    RepositorySummary,
    ReviewContext,
)
from src.parser.js_ts_parser import JsTsParser
from src.parser.python_parser import PythonASTParser

logger = logging.getLogger("reviewer.parser.chunker")


class ContextPreparationEngine:
    """Orchestrates multi-language AST chunking and surrounding context enrichment."""

    def __init__(
        self,
        max_chunk_tokens: int = 2000,
        context_padding_lines: int = 3,
    ) -> None:
        """Initialize engine with token and context boundaries.

        Args:
            max_chunk_tokens: Maximum target token count per code chunk.
            context_padding_lines: Number of surrounding lines to include as context.
        """
        self.max_chunk_tokens = max_chunk_tokens
        self.context_padding_lines = context_padding_lines
        self.python_parser = PythonASTParser()
        self.js_ts_parser = JsTsParser()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Heuristic token estimation based on character count (~4 chars per token).

        Args:
            text: Input string.

        Returns:
            Estimated token count.
        """
        if not text:
            return 0
        return max(1, len(text) // 4)

    def enrich_chunk_context(
        self,
        chunk: CodeChunk,
        full_file_lines: List[str],
    ) -> str:
        """Assemble preceding/following context lines, leading imports, and scope tags.

        Args:
            chunk: The extracted CodeChunk.
            full_file_lines: Complete source lines of the parent file.

        Returns:
            Enriched context lines string stored in chunk.context_lines.
        """
        context_parts: List[str] = []

        # 1. Scope and parent hierarchy
        if chunk.parent_scope:
            context_parts.append(f"// Scope: {chunk.parent_scope}")

        # 2. Leading module imports (up to first 8 imports to prevent overflow)
        if chunk.imports:
            sample_imports = chunk.imports[:8]
            context_parts.append("// Context Imports:")
            for imp in sample_imports:
                context_parts.append(f"//   {imp}")
            if len(chunk.imports) > 8:
                context_parts.append(f"//   ... (+{len(chunk.imports) - 8} more imports)")

        # 3. Preceding lines (padding)
        total_lines = len(full_file_lines)
        if total_lines > 0:
            pre_start = max(1, chunk.start_line - self.context_padding_lines)
            if pre_start < chunk.start_line:
                context_parts.append("// Preceding Context:")
                for line_idx in range(pre_start - 1, chunk.start_line - 1):
                    context_parts.append(f"// {line_idx + 1}: {full_file_lines[line_idx]}")

        # 4. Following lines (padding)
        if total_lines > 0:
            post_end = min(total_lines, chunk.end_line + self.context_padding_lines)
            if post_end > chunk.end_line:
                context_parts.append("// Following Context:")
                for line_idx in range(chunk.end_line, post_end):
                    context_parts.append(f"// {line_idx + 1}: {full_file_lines[line_idx]}")

        context_str = "\n".join(context_parts)
        chunk.context_lines = context_str
        return context_str

    def prepare_file_context(self, file: IngestedFile) -> List[CodeChunk]:
        """Parse source file into AST chunks and enrich each with contextual scope.

        Args:
            file: Ingested repository file.

        Returns:
            List of enriched CodeChunk objects.
        """
        raw_lines = file.content.splitlines()

        if file.language == LanguageEnum.python:
            chunks = self.python_parser.parse_code(
                code=file.content,
                file_path=file.file_path,
                relative_path=file.relative_path,
            )
        elif file.language in (LanguageEnum.javascript, LanguageEnum.typescript):
            chunks = self.js_ts_parser.parse_code(
                code=file.content,
                file_path=file.file_path,
                relative_path=file.relative_path,
                language=file.language,
            )
        else:
            # Skip non-code files and unsupported languages
            return []

        # If file has non-empty content but no chunks parsed, create a module_header chunk
        if not chunks and file.content.strip():
            chunks = [
                CodeChunk(
                    chunk_id=f"{file.relative_path}:1-{len(raw_lines)}:module_header",
                    file_path=file.file_path,
                    relative_path=file.relative_path,
                    language=file.language,
                    chunk_type=ChunkType.module_header,
                    name="module_header",
                    signature=None,
                    start_line=1,
                    end_line=len(raw_lines),
                    code=file.content,
                    docstring=None,
                    imports=[],
                    parent_scope=None,
                )
            ]

        # Enrich each chunk with surrounding context
        for chunk in chunks:
            self.enrich_chunk_context(chunk, raw_lines)

        return chunks

    def prepare_repository_context(self, summary: RepositorySummary) -> ReviewContext:
        """Process all files in a repository summary and construct unified ReviewContext.

        Args:
            summary: Aggregated repository summary.

        Returns:
            ReviewContext containing all extracted code chunks and metadata.
        """
        all_chunks: List[CodeChunk] = []
        for file in summary.files:
            file_chunks = self.prepare_file_context(file)
            all_chunks.extend(file_chunks)

        source_key = summary.source_path_or_url or "repository"
        repo_id = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:12]

        return ReviewContext(
            repo_id=repo_id,
            summary=summary,
            chunks=all_chunks,
            total_chunks=len(all_chunks),
        )

