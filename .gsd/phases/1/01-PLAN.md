---
phase: 1
plan: "01"
wave: 1
depends_on: []
files_modified:
  - requirements.txt
  - .env.example
  - src/__init__.py
  - src/core/__init__.py
  - src/core/config.py
  - src/core/models.py
  - src/main.py
  - tests/__init__.py
  - tests/test_health.py
autonomous: true
gap_closure: false
must_haves:
  truths:
    - "FastAPI server starts and responds 200 with JSON status to health check endpoint"
    - "Core configuration manager loads environment variables with type validation and defaults"
    - "Pydantic domain models define complete schemas for files, repositories, AST code chunks, and review contexts"
  artifacts:
    - requirements.txt
    - .env.example
    - src/core/config.py
    - src/core/models.py
    - src/main.py
    - tests/test_health.py
---

# Plan 1.01: Project Scaffolding, Configuration, and FastAPI Backend Foundation

<objective>
Establish the Python project structure, environment configuration, Pydantic domain models, and FastAPI backend foundation.

Purpose: Provide the foundational contracts, configuration management, and API server that all subsequent ingestion and context extraction modules integrate into.
Output: Validated `requirements.txt`, `.env.example`, `src/core/config.py`, domain schemas in `src/core/models.py`, FastAPI app in `src/main.py`, and passing health tests in `tests/test_health.py`.
</objective>

<context>
Load for context:
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- .gsd/REQUIREMENTS.md
</context>

<tasks>

<task type="auto">
  <name>Initialize dependencies, environment template, and configuration manager</name>
  <files>
    requirements.txt
    .env.example
    src/__init__.py
    src/core/__init__.py
    src/core/config.py
  </files>
  <action>
    Create project dependency definition, environment variable template, and configuration loader:
    
    1. Create `requirements.txt` with pinned versions:
       - `fastapi>=0.110.0,<1.0.0`
       - `uvicorn[standard]>=0.28.0,<1.0.0`
       - `pydantic>=2.6.0,<3.0.0`
       - `pydantic-settings>=2.2.0,<3.0.0`
       - `httpx>=0.27.0,<1.0.0`
       - `python-dotenv>=1.0.1,<2.0.0`
       - `pathspec>=0.12.1,<1.0.0`
       - `pytest>=8.0.0,<9.0.0`
       - `pytest-asyncio>=0.23.0,<1.0.0`
       - `google-genai>=0.1.1`
    
    2. Create `.env.example` defining runtime environment variables:
       - `GEMINI_API_KEY=` (placeholder)
       - `GITHUB_TOKEN=` (optional, for higher GitHub API rate limits)
       - `APP_ENV=development`
       - `HOST=127.0.0.1`
       - `PORT=8000`
       - `MAX_FILE_SIZE_BYTES=1048576` (1MB limit per file)
       - `SUPPORTED_EXTENSIONS=.py,.js,.jsx,.ts,.tsx`
    
    3. Create `src/__init__.py` and `src/core/__init__.py`.
    
    4. Implement `src/core/config.py` using `pydantic_settings.BaseSettings`:
       - Class `Settings`:
         - `app_name: str = "Automated Code Vulnerability Reviewer"`
         - `app_env: str = "development"`
         - `host: str = "127.0.0.1"`
         - `port: int = 8000`
         - `gemini_api_key: str = ""`
         - `github_token: str = ""`
         - `max_file_size_bytes: int = 1048576`
         - `supported_extensions: list[str] = [".py", ".js", ".jsx", ".ts", ".tsx"]`
         - `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`
       - Export `get_settings()` with `@lru_cache` for efficient dependency injection.
    
    AVOID: Hardcoding secret keys or environment values in application source code.
    USE: `pydantic-settings` with type safety and fallback default values.
  </action>
  <verify>
    python -c "from src.core.config import get_settings; s = get_settings(); assert s.port == 8000; print('Settings loaded successfully:', s.app_name)"
  </verify>
  <done>
    `requirements.txt`, `.env.example`, and `src/core/config.py` exist and config loads with correct defaults.
  </done>
</task>

<task type="auto">
  <name>Implement Pydantic domain models and assemble FastAPI application with health check</name>
  <files>
    src/core/models.py
    src/main.py
    tests/__init__.py
    tests/test_health.py
  </files>
  <action>
    Define core domain models and create the FastAPI backend foundation:
    
    1. In `src/core/models.py`, implement domain models:
       - `LanguageEnum(str, Enum)`: `python = "python"`, `javascript = "javascript"`, `typescript = "typescript"`, `unknown = "unknown"`
       - `IngestionSourceType(str, Enum)`: `local = "local"`, `github = "github"`
       - `ChunkType(str, Enum)`: `function = "function"`, `method = "method"`, `class = "class"`, `module_header = "module_header"`, `standalone_block = "standalone_block"`
       - `IngestedFile(BaseModel)`:
         - `file_path: str`
         - `relative_path: str`
         - `language: LanguageEnum`
         - `content: str`
         - `line_count: int`
         - `size_bytes: int`
       - `DependencyManifest(BaseModel)`:
         - `manifest_path: str`
         - `manifest_type: str` (e.g., "requirements.txt", "package.json", "pyproject.toml")
         - `dependencies: dict[str, str]`
       - `RepositorySummary(BaseModel)`:
         - `source_type: IngestionSourceType`
         - `source_path_or_url: str`
         - `total_files: int`
         - `total_lines: int`
         - `languages: dict[str, int]` (counts of files or lines per language)
         - `manifests: list[DependencyManifest]` = []
         - `files: list[IngestedFile]` = []
       - `CodeChunk(BaseModel)`:
         - `chunk_id: str`
         - `file_path: str`
         - `relative_path: str`
         - `language: LanguageEnum`
         - `chunk_type: ChunkType`
         - `name: str`
         - `signature: str | None = None`
         - `start_line: int`
         - `end_line: int`
         - `code: str`
         - `context_lines: str | None = None`
         - `docstring: str | None = None`
         - `imports: list[str] = []`
         - `parent_scope: str | None = None`
       - `ReviewContext(BaseModel)`:
         - `repo_id: str`
         - `summary: RepositorySummary`
         - `chunks: list[CodeChunk]`
         - `total_chunks: int`
       - `HealthResponse(BaseModel)`:
         - `status: str`
         - `version: str`
         - `app_name: str`
    
    2. In `src/main.py`:
       - Instantiate FastAPI app with metadata (title, description, version "1.0.0").
       - Add CORS middleware allowing all origins (`allow_origins=["*"]`) for local web dashboard access.
       - Implement endpoints `GET /health` and `GET /api/v1/health` returning `HealthResponse(status="ok", version="1.0.0", app_name=settings.app_name)`.
       - Add standard error handling middleware returning JSON `{"error": str(exc), "status_code": 500}`.
    
    3. In `tests/test_health.py`:
       - Use `fastapi.testclient.TestClient` to test `GET /health` and `GET /api/v1/health`.
       - Assert status code 200, status "ok", and non-empty version.
    
    AVOID: Tight coupling of domain models to database or external API structures.
    USE: Pure Pydantic v2 BaseModels with clear type annotations.
  </action>
  <verify>
    python -m pytest tests/test_health.py -v
  </verify>
  <done>
    `src/core/models.py` defines all data schemas, `src/main.py` serves `/health`, and `test_health.py` passes.
  </done>
</task>

</tasks>

<must_haves>
After all tasks complete, verify:
- [ ] `src/core/config.py` loads default settings without raising exceptions
- [ ] `src/core/models.py` contains `IngestedFile`, `RepositorySummary`, `CodeChunk`, and `ReviewContext`
- [ ] `pytest tests/test_health.py` passes with HTTP 200 and valid JSON
</must_haves>

<success_criteria>
- [ ] All tasks verified passing
- [ ] Must-haves confirmed
- [ ] Health check endpoint live and tested
</success_criteria>

