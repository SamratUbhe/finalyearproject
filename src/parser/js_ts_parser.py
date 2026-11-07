"""JavaScript and TypeScript syntax-aware parser with function, class, and method extraction."""

import bisect
import logging
import re
from typing import List, Optional, Tuple

from src.core.models import ChunkType, CodeChunk, LanguageEnum

logger = logging.getLogger("reviewer.parser.js_ts")


class JsTsParser:
    """Extracts semantically structured code units from JavaScript and TypeScript code."""

    def __init__(self) -> None:
        pass

    def parse_code(
        self,
        code: str,
        file_path: str = "",
        relative_path: str = "",
        language: LanguageEnum = LanguageEnum.javascript,
    ) -> List[CodeChunk]:
        """Parse JavaScript / TypeScript source code into structured CodeChunks.

        Args:
            code: Source code text.
            file_path: Absolute or filesystem path to source file.
            relative_path: Repository-relative path to source file.
            language: LanguageEnum.javascript or LanguageEnum.typescript.

        Returns:
            List of parsed CodeChunk objects with accurate line offsets.
        """
        path_label = relative_path or file_path or "unnamed.ts"
        raw_lines = code.splitlines()

        if not code.strip():
            return []

        # Precompute line offsets for accurate character-index to line-number conversion
        line_offsets = self._compute_line_offsets(code)

        # 1. Extract file-level imports
        imports = self._extract_imports(code)

        chunks: List[CodeChunk] = []
        covered_ranges: List[Tuple[int, int]] = []

        # 2. Extract classes and their methods
        class_chunks, class_ranges = self._extract_classes(
            code=code,
            raw_lines=raw_lines,
            line_offsets=line_offsets,
            file_path=file_path,
            relative_path=relative_path,
            language=language,
            imports=imports,
        )
        chunks.extend(class_chunks)
        covered_ranges.extend(class_ranges)

        # 3. Extract top-level function declarations
        func_chunks, func_ranges = self._extract_functions(
            code=code,
            raw_lines=raw_lines,
            line_offsets=line_offsets,
            file_path=file_path,
            relative_path=relative_path,
            language=language,
            imports=imports,
            covered_ranges=covered_ranges,
        )
        chunks.extend(func_chunks)
        covered_ranges.extend(func_ranges)

        # 4. Extract arrow functions and function expressions
        arrow_chunks, arrow_ranges = self._extract_arrow_functions(
            code=code,
            raw_lines=raw_lines,
            line_offsets=line_offsets,
            file_path=file_path,
            relative_path=relative_path,
            language=language,
            imports=imports,
            covered_ranges=covered_ranges,
        )
        chunks.extend(arrow_chunks)
        covered_ranges.extend(arrow_ranges)

        # Sort chunks by start line
        chunks.sort(key=lambda c: (c.start_line, c.end_line))

        # 5. Fallback: If no functions or classes extracted (e.g. flat script or route definitions)
        if not chunks and raw_lines:
            header_chunk = CodeChunk(
                chunk_id=f"{path_label}:1-{len(raw_lines)}:module_header",
                file_path=file_path,
                relative_path=relative_path,
                language=language,
                chunk_type=ChunkType.module_header,
                name="module_header",
                signature=None,
                start_line=1,
                end_line=len(raw_lines),
                code="\n".join(raw_lines),
                docstring=self._extract_preceding_jsdoc(code, 0),
                imports=imports,
                parent_scope=None,
            )
            chunks.append(header_chunk)

        return chunks

    def _compute_line_offsets(self, code: str) -> List[int]:
        """Compute starting character offset for each 1-indexed line."""
        offsets = [0]
        for match in re.finditer(r"\n", code):
            offsets.append(match.end())
        return offsets

    def _offset_to_line(self, line_offsets: List[int], char_pos: int) -> int:
        """Map a character offset to 1-indexed line number."""
        return bisect.bisect_right(line_offsets, max(0, char_pos))

    def _extract_imports(self, code: str) -> List[str]:
        """Extract ES6 and CommonJS import statements."""
        imports: List[str] = []

        # ES6 imports: e.g. import ... from '...' or import '...'
        es6_pattern = re.compile(
            r"^\s*import(?:\s+(?:[\w*\s{},$]+from\s+)?|\s*)['\"][^'\"]+['\"];?",
            re.MULTILINE,
        )
        for m in es6_pattern.finditer(code):
            imp = m.group(0).strip()
            if imp and imp not in imports:
                imports.append(imp)

        # CommonJS requires: const ... = require('...')
        cjs_pattern = re.compile(
            r"^\s*(?:const|let|var)\s+[\w\s{},$]+\s*=\s*require\s*\(['\"][^'\"]+['\"]\);?",
            re.MULTILINE,
        )
        for m in cjs_pattern.finditer(code):
            imp = m.group(0).strip()
            if imp and imp not in imports:
                imports.append(imp)

        return imports

    def _find_matching_brace(self, code: str, open_brace_pos: int) -> int:
        """Find the matching closing brace index taking into account strings, template literals, and comments.

        Args:
            code: Full source text.
            open_brace_pos: Index of opening '{'.

        Returns:
            Index of matching '}', or len(code) - 1 if unclosed.
        """
        n = len(code)
        i = open_brace_pos + 1
        depth = 1

        in_single_quote = False
        in_double_quote = False
        in_template_literal = False
        in_line_comment = False
        in_block_comment = False

        while i < n and depth > 0:
            char = code[i]
            prev_char = code[i - 1] if i > 0 else ""

            # Check if inside line comment
            if in_line_comment:
                if char == "\n":
                    in_line_comment = False
                i += 1
                continue

            # Check if inside block comment
            if in_block_comment:
                if prev_char == "*" and char == "/":
                    in_block_comment = False
                i += 1
                continue

            # Check if inside single-quote string
            if in_single_quote:
                if char == "'" and prev_char != "\\":
                    in_single_quote = False
                i += 1
                continue

            # Check if inside double-quote string
            if in_double_quote:
                if char == '"' and prev_char != "\\":
                    in_double_quote = False
                i += 1
                continue

            # Check if inside template literal
            if in_template_literal:
                if char == "`" and prev_char != "\\":
                    in_template_literal = False
                elif char == "{" and prev_char == "$":
                    depth += 1
                elif char == "}":
                    # Potentially closing ${...} interpolation
                    pass
                i += 1
                continue

            # Start of comments
            if char == "/" and i + 1 < n:
                next_char = code[i + 1]
                if next_char == "/":
                    in_line_comment = True
                    i += 2
                    continue
                elif next_char == "*":
                    in_block_comment = True
                    i += 2
                    continue

            # Start of strings
            if char == "'":
                in_single_quote = True
                i += 1
                continue
            elif char == '"':
                in_double_quote = True
                i += 1
                continue
            elif char == "`":
                in_template_literal = True
                i += 1
                continue

            # Structural curly braces
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return i

            i += 1

        return min(i, n - 1)

    def _extract_preceding_jsdoc(self, code: str, start_pos: int) -> Optional[str]:
        """Extract JSDoc comment (/** ... */) immediately preceding a declaration."""
        prefix = code[:start_pos].rstrip()
        if prefix.endswith("*/"):
            comment_start = prefix.rfind("/*")
            if comment_start != -1:
                comment_text = prefix[comment_start:]
                # Check that between comment end and declaration there are only comments or whitespace
                remaining = code[comment_start + len(comment_text) : start_pos].strip()
                if not remaining:
                    # Clean up comment markers
                    cleaned = re.sub(r"^\s*/\*\*?", "", comment_text)
                    cleaned = re.sub(r"\*/\s*$", "", cleaned)
                    cleaned_lines = [
                        re.sub(r"^\s*\*\s?", "", line) for line in cleaned.splitlines()
                    ]
                    doc = "\n".join(cleaned_lines).strip()
                    return doc if doc else None
        return None

    def _slice_lines(self, raw_lines: List[str], start_line: int, end_line: int) -> str:
        """Slice 1-indexed lines safely."""
        total = len(raw_lines)
        s = max(1, min(start_line, total))
        e = max(s, min(end_line, total))
        return "\n".join(raw_lines[s - 1 : e])

    def _extract_classes(
        self,
        code: str,
        raw_lines: List[str],
        line_offsets: List[int],
        file_path: str,
        relative_path: str,
        language: LanguageEnum,
        imports: List[str],
    ) -> Tuple[List[CodeChunk], List[Tuple[int, int]]]:
        """Extract classes and their member methods."""
        path_label = relative_path or file_path or "unnamed.ts"
        chunks: List[CodeChunk] = []
        ranges: List[Tuple[int, int]] = []

        class_pattern = re.compile(
            r"(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([a-zA-Z_$][a-zA-Z0-9_$]*)(?:\s*<[^>]+>)?(?:\s+extends\s+[^{]+)?(?:\s+implements\s+[^{]+)?\s*\{",
        )

        for match in class_pattern.finditer(code):
            cls_name = match.group(1)
            cls_start_char = match.start()
            open_brace_pos = match.end() - 1
            close_brace_pos = self._find_matching_brace(code, open_brace_pos)

            start_line = self._offset_to_line(line_offsets, cls_start_char)
            end_line = self._offset_to_line(line_offsets, close_brace_pos)

            # Class header signature
            header_str = match.group(0).rstrip("{").strip()
            # Clean export/default keywords for signature
            sig = re.sub(r"^(?:export\s+)?(?:default\s+)?", "", header_str).strip()
            docstring = self._extract_preceding_jsdoc(code, cls_start_char)

            cls_chunk = CodeChunk(
                chunk_id=f"{path_label}:{start_line}-{end_line}:{cls_name}",
                file_path=file_path,
                relative_path=relative_path,
                language=language,
                chunk_type=ChunkType.class_,
                name=cls_name,
                signature=sig,
                start_line=start_line,
                end_line=end_line,
                code=self._slice_lines(raw_lines, start_line, end_line),
                docstring=docstring,
                imports=imports,
                parent_scope=None,
            )
            chunks.append(cls_chunk)
            ranges.append((cls_start_char, close_brace_pos))

            # Extract methods inside this class body
            class_body = code[open_brace_pos + 1 : close_brace_pos]
            method_chunks = self._extract_class_methods(
                class_body=class_body,
                body_offset=open_brace_pos + 1,
                class_name=cls_name,
                raw_lines=raw_lines,
                line_offsets=line_offsets,
                file_path=file_path,
                relative_path=relative_path,
                language=language,
                imports=imports,
            )
            chunks.extend(method_chunks)

        return chunks, ranges

    def _extract_class_methods(
        self,
        class_body: str,
        body_offset: int,
        class_name: str,
        raw_lines: List[str],
        line_offsets: List[int],
        file_path: str,
        relative_path: str,
        language: LanguageEnum,
        imports: List[str],
    ) -> List[CodeChunk]:
        """Extract methods inside a class body."""
        path_label = relative_path or file_path or "unnamed.ts"
        method_chunks: List[CodeChunk] = []

        method_pattern = re.compile(
            r"(?:^|[\r\n;])\s*(?:(?:public|private|protected|static|readonly|async|get|set|override)\s+)*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?:<[^>]+>)?\s*\(([\s\S]*?)\)(?:\s*:\s*[^{]+)?\s*\{",
        )

        reserved_keywords = {
            "if", "for", "while", "switch", "catch", "function", "class", "constructor",
        }

        for match in method_pattern.finditer(class_body):
            method_name = match.group(1)
            if method_name in reserved_keywords and method_name != "constructor":
                continue

            rel_start = match.start()
            # If match had leading newline or comment, find actual declaration position
            decl_match = re.search(
                r"(?:(?:public|private|protected|static|readonly|async|get|set|override)\s+)*" + re.escape(method_name) + r"\s*\(",
                class_body[rel_start:],
            )
            decl_start_char = body_offset + rel_start + (decl_match.start() if decl_match else 0)
            open_brace_pos = body_offset + match.end() - 1
            close_brace_pos = self._find_matching_brace(class_body, match.end() - 1) + body_offset

            start_line = self._offset_to_line(line_offsets, decl_start_char)
            end_line = self._offset_to_line(line_offsets, close_brace_pos)

            raw_header = match.group(0).strip().rstrip("{").strip()
            # Strip preceding JSDoc comment if captured in raw_header
            if "*/" in raw_header:
                raw_header = raw_header.split("*/", 1)[-1].strip()

            docstring = self._extract_preceding_jsdoc(class_body, rel_start)

            method_chunk = CodeChunk(
                chunk_id=f"{path_label}:{start_line}-{end_line}:{class_name}.{method_name}",
                file_path=file_path,
                relative_path=relative_path,
                language=language,
                chunk_type=ChunkType.method,
                name=method_name,
                signature=raw_header,
                start_line=start_line,
                end_line=end_line,
                code=self._slice_lines(raw_lines, start_line, end_line),
                docstring=docstring,
                imports=imports,
                parent_scope=class_name,
            )
            method_chunks.append(method_chunk)

        return method_chunks

    def _extract_functions(
        self,
        code: str,
        raw_lines: List[str],
        line_offsets: List[int],
        file_path: str,
        relative_path: str,
        language: LanguageEnum,
        imports: List[str],
        covered_ranges: List[Tuple[int, int]],
    ) -> Tuple[List[CodeChunk], List[Tuple[int, int]]]:
        """Extract standard function declarations."""
        path_label = relative_path or file_path or "unnamed.ts"
        chunks: List[CodeChunk] = []
        ranges: List[Tuple[int, int]] = []

        fn_pattern = re.compile(
            r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function(?:\s*\*|\s+)\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?:<[^>]+>)?\s*\(([\s\S]*?)\)(?:\s*:\s*[^{]+)?\s*\{",
        )

        for match in fn_pattern.finditer(code):
            start_pos = match.start()
            if self._is_pos_inside_ranges(start_pos, covered_ranges):
                continue

            fn_name = match.group(1)
            open_brace_pos = match.end() - 1
            close_brace_pos = self._find_matching_brace(code, open_brace_pos)

            start_line = self._offset_to_line(line_offsets, start_pos)
            end_line = self._offset_to_line(line_offsets, close_brace_pos)

            sig = match.group(0).rstrip("{").strip()
            docstring = self._extract_preceding_jsdoc(code, start_pos)

            chunks.append(
                CodeChunk(
                    chunk_id=f"{path_label}:{start_line}-{end_line}:{fn_name}",
                    file_path=file_path,
                    relative_path=relative_path,
                    language=language,
                    chunk_type=ChunkType.function,
                    name=fn_name,
                    signature=sig,
                    start_line=start_line,
                    end_line=end_line,
                    code=self._slice_lines(raw_lines, start_line, end_line),
                    docstring=docstring,
                    imports=imports,
                    parent_scope=None,
                )
            )
            ranges.append((start_pos, close_brace_pos))

        return chunks, ranges

    def _extract_arrow_functions(
        self,
        code: str,
        raw_lines: List[str],
        line_offsets: List[int],
        file_path: str,
        relative_path: str,
        language: LanguageEnum,
        imports: List[str],
        covered_ranges: List[Tuple[int, int]],
    ) -> Tuple[List[CodeChunk], List[Tuple[int, int]]]:
        """Extract arrow functions and function expressions assigned to variables."""
        path_label = relative_path or file_path or "unnamed.ts"
        chunks: List[CodeChunk] = []
        ranges: List[Tuple[int, int]] = []

        arrow_pattern = re.compile(
            r"(?:export\s+)?(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?::\s*[^=]+)?\s*=\s*(?:async\s*)?(?:\(([\s\S]*?)\)|[a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?::\s*[^{=]+)?\s*=>\s*\{",
        )

        for match in arrow_pattern.finditer(code):
            start_pos = match.start()
            if self._is_pos_inside_ranges(start_pos, covered_ranges):
                continue

            fn_name = match.group(1)
            open_brace_pos = match.end() - 1
            close_brace_pos = self._find_matching_brace(code, open_brace_pos)

            # Check if semicolon directly follows closing brace
            after_close = close_brace_pos + 1
            while after_close < len(code) and code[after_close] in " \t":
                after_close += 1
            if after_close < len(code) and code[after_close] == ";":
                close_brace_pos = after_close

            start_line = self._offset_to_line(line_offsets, start_pos)
            end_line = self._offset_to_line(line_offsets, close_brace_pos)

            sig = match.group(0).rstrip("{").strip()
            docstring = self._extract_preceding_jsdoc(code, start_pos)

            chunks.append(
                CodeChunk(
                    chunk_id=f"{path_label}:{start_line}-{end_line}:{fn_name}",
                    file_path=file_path,
                    relative_path=relative_path,
                    language=language,
                    chunk_type=ChunkType.function,
                    name=fn_name,
                    signature=sig,
                    start_line=start_line,
                    end_line=end_line,
                    code=self._slice_lines(raw_lines, start_line, end_line),
                    docstring=docstring,
                    imports=imports,
                    parent_scope=None,
                )
            )
            ranges.append((start_pos, close_brace_pos))

        return chunks, ranges

    def _is_pos_inside_ranges(self, pos: int, ranges: List[Tuple[int, int]]) -> bool:
        """Check if character position falls inside any already parsed range."""
        return any(start <= pos <= end for start, end in ranges)
