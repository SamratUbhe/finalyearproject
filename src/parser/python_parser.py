"""Python AST parser extracting classes, functions, methods, and syntax boundaries."""

import ast
import logging
import re
from typing import List, Optional

from src.core.models import ChunkType, CodeChunk, LanguageEnum

logger = logging.getLogger("reviewer.parser.python")


class PythonASTParser:
    """Extracts semantically structured code units using Python's native AST module."""

    def __init__(self) -> None:
        pass

    def parse_code(
        self,
        code: str,
        file_path: str = "",
        relative_path: str = "",
    ) -> List[CodeChunk]:
        """Parse Python source code into structured CodeChunks.

        Args:
            code: Source code content.
            file_path: Absolute or filesystem path to source file.
            relative_path: Repository-relative path to source file.

        Returns:
            List of parsed CodeChunk objects with accurate line offsets and context.
        """
        path_label = relative_path or file_path or "unnamed.py"
        raw_lines = code.splitlines()

        if not code.strip():
            return []

        try:
            tree = ast.parse(code, filename=path_label)
        except (SyntaxError, ValueError) as exc:
            logger.warning(
                "Syntax parsing error in %s (%s). Falling back to resilient block chunker.",
                path_label,
                exc,
            )
            return self._fallback_line_chunker(
                code=code,
                raw_lines=raw_lines,
                file_path=file_path,
                relative_path=relative_path,
                error_message=str(exc),
            )

        # 1. Collect module-level imports
        imports = self._extract_imports(tree)

        chunks: List[CodeChunk] = []
        top_level_stmts: List[ast.stmt] = []

        # 2. Traverse top-level body nodes
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            elif isinstance(node, ast.ClassDef):
                cls_chunks = self._process_class_node(
                    node=node,
                    raw_lines=raw_lines,
                    file_path=file_path,
                    relative_path=relative_path,
                    imports=imports,
                )
                chunks.extend(cls_chunks)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_chunk = self._process_function_node(
                    node=node,
                    raw_lines=raw_lines,
                    file_path=file_path,
                    relative_path=relative_path,
                    imports=imports,
                    parent_scope=None,
                )
                chunks.append(func_chunk)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                # Module-level docstring
                continue
            else:
                top_level_stmts.append(node)

        # 3. Handle top-level statements / script blocks if present
        if top_level_stmts:
            standalone_chunks = self._process_standalone_statements(
                statements=top_level_stmts,
                raw_lines=raw_lines,
                file_path=file_path,
                relative_path=relative_path,
                imports=imports,
            )
            chunks.extend(standalone_chunks)

        # 4. If no chunks extracted (e.g. only imports or docstrings), emit a module_header chunk
        if not chunks and raw_lines:
            header_chunk = CodeChunk(
                chunk_id=f"{path_label}:1-{len(raw_lines)}:module_header",
                file_path=file_path,
                relative_path=relative_path,
                language=LanguageEnum.python,
                chunk_type=ChunkType.module_header,
                name="module_header",
                signature=None,
                start_line=1,
                end_line=len(raw_lines),
                code="\n".join(raw_lines),
                docstring=ast.get_docstring(tree),
                imports=imports,
                parent_scope=None,
            )
            chunks.append(header_chunk)

        return chunks

    def _extract_imports(self, tree: ast.AST) -> List[str]:
        """Extract all import statements preserving source appearance order."""
        import_nodes: List[ast.stmt] = [
            n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
        ]
        import_nodes.sort(key=lambda n: getattr(n, "lineno", 0))

        results: List[str] = []
        for imp in import_nodes:
            try:
                unparsed = ast.unparse(imp).strip()
                if unparsed and unparsed not in results:
                    results.append(unparsed)
            except Exception:
                pass
        return results

    def _get_node_start_line(self, node: ast.AST) -> int:
        """Compute start line including any preceding decorators."""
        lineno = getattr(node, "lineno", 1)
        decorator_list = getattr(node, "decorator_list", [])
        if decorator_list:
            dec_lines = [getattr(d, "lineno", lineno) for d in decorator_list]
            return min(dec_lines + [lineno])
        return lineno

    def _get_node_end_line(self, node: ast.AST, default: int = 1) -> int:
        """Compute end line with fallback to lineno."""
        return getattr(node, "end_lineno", getattr(node, "lineno", default))

    def _slice_code(self, raw_lines: List[str], start_line: int, end_line: int) -> str:
        """Extract exact lines from 1-indexed start and end line boundaries."""
        total = len(raw_lines)
        clamped_start = max(1, min(start_line, total))
        clamped_end = max(clamped_start, min(end_line, total))
        return "\n".join(raw_lines[clamped_start - 1 : clamped_end])

    def _format_function_signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> str:
        """Format a clean Python function/method signature."""
        prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
        try:
            args_str = ast.unparse(node.args)
        except Exception:
            args_str = ""
        ret_str = ""
        if node.returns:
            try:
                ret_str = f" -> {ast.unparse(node.returns)}"
            except Exception:
                ret_str = ""
        return f"{prefix}{node.name}({args_str}){ret_str}"

    def _format_class_signature(self, node: ast.ClassDef) -> str:
        """Format class definition header signature."""
        bases_list: List[str] = []
        for b in node.bases:
            try:
                bases_list.append(ast.unparse(b))
            except Exception:
                pass
        bases_str = f"({', '.join(bases_list)})" if bases_list else ""
        return f"class {node.name}{bases_str}"

    def _process_function_node(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        raw_lines: List[str],
        file_path: str,
        relative_path: str,
        imports: List[str],
        parent_scope: Optional[str] = None,
    ) -> CodeChunk:
        """Convert a function or method AST node into a CodeChunk."""
        path_label = relative_path or file_path or "unnamed.py"
        start_line = self._get_node_start_line(node)
        end_line = self._get_node_end_line(node, start_line)
        code_slice = self._slice_code(raw_lines, start_line, end_line)
        docstring = ast.get_docstring(node)
        signature = self._format_function_signature(node)

        chunk_type = ChunkType.method if parent_scope else ChunkType.function
        name_qual = f"{parent_scope}.{node.name}" if parent_scope else node.name
        chunk_id = f"{path_label}:{start_line}-{end_line}:{name_qual}"

        return CodeChunk(
            chunk_id=chunk_id,
            file_path=file_path,
            relative_path=relative_path,
            language=LanguageEnum.python,
            chunk_type=chunk_type,
            name=node.name,
            signature=signature,
            start_line=start_line,
            end_line=end_line,
            code=code_slice,
            docstring=docstring,
            imports=imports,
            parent_scope=parent_scope,
        )

    def _process_class_node(
        self,
        node: ast.ClassDef,
        raw_lines: List[str],
        file_path: str,
        relative_path: str,
        imports: List[str],
    ) -> List[CodeChunk]:
        """Convert a class AST node into a class chunk and child method chunks."""
        path_label = relative_path or file_path or "unnamed.py"
        start_line = self._get_node_start_line(node)
        end_line = self._get_node_end_line(node, start_line)
        code_slice = self._slice_code(raw_lines, start_line, end_line)
        docstring = ast.get_docstring(node)
        signature = self._format_class_signature(node)

        class_chunk_id = f"{path_label}:{start_line}-{end_line}:{node.name}"
        class_chunk = CodeChunk(
            chunk_id=class_chunk_id,
            file_path=file_path,
            relative_path=relative_path,
            language=LanguageEnum.python,
            chunk_type=ChunkType.class_,
            name=node.name,
            signature=signature,
            start_line=start_line,
            end_line=end_line,
            code=code_slice,
            docstring=docstring,
            imports=imports,
            parent_scope=None,
        )

        chunks: List[CodeChunk] = [class_chunk]

        # Extract internal methods
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_chunk = self._process_function_node(
                    node=item,
                    raw_lines=raw_lines,
                    file_path=file_path,
                    relative_path=relative_path,
                    imports=imports,
                    parent_scope=node.name,
                )
                chunks.append(method_chunk)

        return chunks

    def _process_standalone_statements(
        self,
        statements: List[ast.stmt],
        raw_lines: List[str],
        file_path: str,
        relative_path: str,
        imports: List[str],
    ) -> List[CodeChunk]:
        """Group top-level statements into logical standalone code blocks."""
        if not statements:
            return []

        path_label = relative_path or file_path or "unnamed.py"
        # Determine continuous or aggregate line range for top-level code
        start_line = min(getattr(s, "lineno", 1) for s in statements)
        end_line = max(getattr(s, "end_lineno", getattr(s, "lineno", start_line)) for s in statements)
        code_slice = self._slice_code(raw_lines, start_line, end_line)

        chunk_id = f"{path_label}:{start_line}-{end_line}:module_block"
        return [
            CodeChunk(
                chunk_id=chunk_id,
                file_path=file_path,
                relative_path=relative_path,
                language=LanguageEnum.python,
                chunk_type=ChunkType.standalone_block,
                name="module_block",
                signature=None,
                start_line=start_line,
                end_line=end_line,
                code=code_slice,
                docstring=None,
                imports=imports,
                parent_scope=None,
            )
        ]

    def _fallback_line_chunker(
        self,
        code: str,
        raw_lines: List[str],
        file_path: str,
        relative_path: str,
        error_message: str,
    ) -> List[CodeChunk]:
        """Fallback chunker for unparseable or syntax-errored Python files."""
        path_label = relative_path or file_path or "unnamed.py"
        # Extract any obvious import lines using regex
        import_pattern = re.compile(r"^\s*(?:import\s+[a-zA-Z0-9_\.]+|from\s+[a-zA-Z0-9_\.]+\s+import\s+.+)")
        imports = [line.strip() for line in raw_lines if import_pattern.match(line)]

        chunks: List[CodeChunk] = []
        total_lines = len(raw_lines)
        if total_lines == 0:
            return []

        block_size = 60
        for i in range(0, total_lines, block_size):
            s_line = i + 1
            e_line = min(i + block_size, total_lines)
            chunk_lines = raw_lines[i:e_line]
            chunk_code = "\n".join(chunk_lines)

            chunk_id = f"{path_label}:{s_line}-{e_line}:fallback_block_{s_line}"
            chunks.append(
                CodeChunk(
                    chunk_id=chunk_id,
                    file_path=file_path,
                    relative_path=relative_path,
                    language=LanguageEnum.python,
                    chunk_type=ChunkType.standalone_block,
                    name=f"block_{s_line}_{e_line}",
                    signature=None,
                    start_line=s_line,
                    end_line=e_line,
                    code=chunk_code,
                    docstring=f"Syntax fallback: {error_message}",
                    imports=imports,
                    parent_scope=None,
                )
            )

        return chunks

