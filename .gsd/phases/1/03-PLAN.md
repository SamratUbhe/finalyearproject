---
phase: 1
plan: "03"
wave: 3
depends_on:
  - "01"
  - "02"
files_modified:
  - src/parser/__init__.py
  - src/parser/python_parser.py
  - src/parser/js_ts_parser.py
  - src/parser/chunker.py
  - src/api/routes/context.py
  - src/main.py
  - tests/test_parser.py
autonomous: true
gap_closure: false
must_haves:
  truths:
    - "Python AST parser extracts classes, functions, async methods, docstrings, imports, and line spans without external C compiler requirements"
    - "JS/TS parser extracts function declarations, arrow functions, classes, methods, and imports with accurate line boundaries"
    - "Context preparation engine enriches code chunks with leading imports, parent class scope, and token size metadata"
    - "API endpoint /api/v1/context/prepare transforms repository files into structured ReviewContext"
  artifacts:
    - src/parser/python_parser.py
    - src/parser/js_ts_parser.py
    - src/parser/chunker.py
    - src/api/routes/context.py
    - tests/test_parser.py
---

# Plan 1.03: Syntax-Aware Context Preparation & AST Chunking Engine

<objective>
Build the AST and syntax-aware code chunking engine for Python and JavaScript/TypeScript. The engine decomposes repository source files into semantically intact code units (classes, functions, async methods) with exact line spans, signatures, docstrings, and surrounding contextual imports, packaging them into `ReviewContext` ready for multi-agent LLM analysis.

Purpose: Fulfill REQ-03 by replacing arbitrary text splitting with syntax-aware code boundaries that provide agents with complete semantic context for vulnerability detection and architecture evaluation.
Output: `src/parser/python_parser.py`, `src/parser/js_ts_parser.py`, `src/parser/chunker.py`, `src/api/routes/context.py`, and verification suite `tests/test_parser.py`.
</objective>

<context>
Load for context:
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- .gsd/REQUIREMENTS.md
- src/core/models.py
- src/ingestion/detector.py
</context>

<tasks>

<task type="auto">
  <name>Build Python AST structural extractor using Python's native ast module</name>
  <files>
    src/parser/__init__.py
    src/parser/python_parser.py
  </files>
  <action>
    Implement Python AST parsing in `src/parser/python_parser.py`:
    
    1. Implement `PythonASTParser` class:
       - Method `parse_code(code: str, file_path: str = "", relative_path: str = "") -> list[CodeChunk]`:
         - Parse source using `ast.parse(code)`.
         - If `SyntaxError` is raised, record syntax warning and fallback to a resilient line-based block chunker.
         - Traverse AST nodes to extract:
           - Module-level imports: collect all `ast.Import` (e.g. `import os`) and `ast.ImportFrom` (e.g. `from typing import List`) statements as strings.
           - Classes (`ast.ClassDef`):
             - Name, base classes / inheritance list.
             - Class docstring (`ast.get_docstring(node)`).
             - Decorator list.
             - Start line (`node.lineno`) and end line (`node.end_lineno`).
             - Class-level code slice.
           - Top-level functions (`ast.FunctionDef`, `ast.AsyncFunctionDef`):
             - Function name.
             - Signature (parameter list with type hints, return type annotation).
             - Decorators.
             - Docstring.
             - Start line and end line.
             - Function code slice.
             - Complexity score (number of statements, branch points).
           - Class methods:
             - Process methods inside each `ast.ClassDef`.
             - Record `parent_scope` as the class name.
             - Set `chunk_type` to `ChunkType.method`.
           - Module-level code blocks outside functions/classes:
             - If there are top-level execution statements (e.g. scripts or configs), group them into a `standalone_block` chunk.
         - Attach extracted imports to every chunk generated from that file.
         - Generate deterministic `chunk_id` (e.g., hash or `{file_path}:{start_line}-{end_line}:{name}`).
         - Return `list[CodeChunk]`.
    
    AVOID: Using external C-extension binary wheels on Windows for Python parsing when the built-in `ast` module provides 100% standard library compliance and exact line offset fidelity.
    USE: Native `ast` with `lineno` and `end_lineno` properties (Python 3.8+ standard).
  </action>
  <verify>
    python -c "from src.parser.python_parser import PythonASTParser; p = PythonASTParser(); chunks = p.parse_code('class Demo:\n    def run(self, x: int) -> bool:\n        \"\"\"Runs demo.\"\"\"\n        return x > 0\n', 'demo.py', 'demo.py'); assert len(chunks) >= 1; print('Python AST parser verified:', [c.name for c in chunks])"
  </verify>
  <done>
    `PythonASTParser` extracts classes, methods, functions, signatures, docstrings, and exact line boundaries from Python source.
  </done>
</task>

<task type="auto">
  <name>Build JavaScript and TypeScript syntax-aware parser with function, class, and method extraction</name>
  <files>
    src/parser/js_ts_parser.py
  </files>
  <action>
    Implement JavaScript/TypeScript syntax extractor in `src/parser/js_ts_parser.py`:
    
    1. Implement `JsTsParser` class supporting `.js`, `.jsx`, `.ts`, `.tsx`:
       - Method `parse_code(code: str, file_path: str = "", relative_path: str = "", language: LanguageEnum = LanguageEnum.javascript) -> list[CodeChunk]`:
         - Extract module imports:
           - ES6 imports (`import ... from '...'`)
           - CommonJS requires (`const ... = require('...')`)
         - Extract structural units with balanced brace matching to capture complete bodies:
           - Class declarations: `class <Name> (extends <Base>)? { ... }`
           - Function declarations: `(export )?(async )?function <name>(<args>) { ... }`
           - Arrow functions and function expressions: `(export )?const <name> = (async )?(<args>) => { ... }`
           - Class methods: `<name>(<args>) { ... }`, `async <name>(<args>) { ... }`
         - Capture accurate `start_line` and `end_line` (1-indexed).
         - Extract docstrings / JSDoc comments (`/** ... */`) immediately preceding the node.
         - Extract signatures (parameters and return types if TypeScript).
         - Associate file-level imports with each chunk.
         - Deterministic `chunk_id` format `{file_path}:{start_line}-{end_line}:{name}`.
         - Return `list[CodeChunk]`.
    
    2. Ensure parser handles modern syntax: async/await, arrow functions, exported functions, and JSX/TSX tags without syntax breakage.
    
    AVOID: Brittle fixed-length string slicing that cuts closures or multi-line function bodies in half.
    USE: Balanced delimiter tracking (curly braces) combined with regex signature scanning for bulletproof syntax boundaries.
  </action>
  <verify>
    python -c "from src.parser.js_ts_parser import JsTsParser; from src.core.models import LanguageEnum; p = JsTsParser(); chunks = p.parse_code('export const calculate = (a: number, b: number): number => {\n  return a + b;\n};\n', 'calc.ts', 'calc.ts', LanguageEnum.typescript); assert len(chunks) == 1 and chunks[0].name == 'calculate'; print('JS/TS parser verified:', chunks[0].name, 'lines', chunks[0].start_line, '-', chunks[0].end_line)"
  </verify>
  <done>
    `JsTsParser` parses JavaScript and TypeScript files, extracting functions, arrow functions, classes, and imports with valid start and end line ranges.
  </done>
</task>

<task type="auto">
  <name>Build context preparation engine, context API route, and parser test suite</name>
  <files>
    src/parser/chunker.py
    src/api/routes/context.py
    src/main.py
    tests/test_parser.py
  </files>
  <action>
    Assemble context preparation pipeline, expose API route, and write test suite:
    
    1. In `src/parser/chunker.py`:
       - Implement `ContextPreparationEngine`:
         - `__init__(max_chunk_tokens: int = 2000, context_padding_lines: int = 3)`
         - `estimate_tokens(text: str) -> int`: heuristic ~4 characters per token.
         - `enrich_chunk_context(chunk: CodeChunk, full_file_lines: list[str]) -> str`:
           - Assembles surrounding context: leading module imports, parent class definition line, and `context_padding_lines` immediately preceding and following the chunk.
           - Sets `chunk.context_lines`.
         - `prepare_file_context(file: IngestedFile) -> list[CodeChunk]`:
           - If `file.language == LanguageEnum.python`, use `PythonASTParser`.
           - If `file.language in (LanguageEnum.javascript, LanguageEnum.typescript)`, use `JsTsParser`.
           - For files with no extracted functions/classes (e.g. flat script), creates a `module_header` chunk.
           - Enriches each chunk with context lines and validates token estimates.
         - `prepare_repository_context(summary: RepositorySummary) -> ReviewContext`:
           - Processes all ingested files.
           - Aggregates all chunks into a `ReviewContext(repo_id=..., summary=summary, chunks=all_chunks, total_chunks=len(all_chunks))`.
    
    2. In `src/api/routes/context.py`:
       - Create APIRouter with prefix `/api/v1/context`, tags=["Context Preparation"].
       - Implement `POST /prepare`:
         - Accepts `RepositorySummary` body.
         - Invokes `ContextPreparationEngine().prepare_repository_context(summary)`.
         - Returns `ReviewContext`.
    
    3. In `src/main.py`:
       - Register context router: `app.include_router(context_router)`.
    
    4. In `tests/test_parser.py`:
       - Test Python parser on classes, functions, async functions, decorators, and imports.
       - Test JS/TS parser on function declarations, arrow functions, classes, and JSX/TSX.
       - Test `ContextPreparationEngine` chunk enrichment and token estimation.
       - Test `POST /api/v1/context/prepare` using FastAPI `TestClient`.
    
    AVOID: Arbitrary chunking without semantic boundaries.
    USE: Enriched AST chunks containing surrounding context so downstream LLM agents have complete situational awareness.
  </action>
  <verify>
    python -m pytest tests/test_parser.py -v
  </verify>
  <done>
    `test_parser.py` passes 100% of tests verifying Python and JS/TS parsing, chunk context enrichment, and `/api/v1/context/prepare` API endpoint.
  </done>
</task>

</tasks>

<must_haves>
After all tasks complete, verify:
- [ ] `PythonASTParser` extracts classes and functions with docstrings and line offsets
- [ ] `JsTsParser` extracts JS/TS functions, arrow functions, and classes
- [ ] `ContextPreparationEngine` produces `ReviewContext` with enriched code chunks
- [ ] `pytest tests/test_parser.py` passes all unit and integration tests
</must_haves>

<success_criteria>
- [ ] All tasks verified passing
- [ ] Must-haves confirmed
- [ ] Syntax-aware context preparation pipeline ready for Phase 2 agent consumption
</success_criteria>

