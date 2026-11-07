---
phase: 1
plan: "02"
wave: 2
depends_on:
  - "01"
files_modified:
  - src/ingestion/__init__.py
  - src/ingestion/local.py
  - src/ingestion/github.py
  - src/ingestion/detector.py
  - src/api/__init__.py
  - src/api/routes/__init__.py
  - src/api/routes/ingest.py
  - src/main.py
  - tests/test_ingestion.py
autonomous: true
gap_closure: false
must_haves:
  truths:
    - "Local directory scanner traverses repository while respecting .gitignore, ignoring binaries, and adhering to file size caps"
    - "GitHub ingestion retrieves remote repositories, specific branches, commits, and PRs via archive streaming"
    - "Language detection identifies Python and JS/TS codebases and parses dependency manifests (requirements.txt, package.json)"
    - "Ingestion API endpoints (/api/v1/ingest/local and /api/v1/ingest/github) return structured RepositorySummary objects"
  artifacts:
    - src/ingestion/local.py
    - src/ingestion/github.py
    - src/ingestion/detector.py
    - src/api/routes/ingest.py
    - tests/test_ingestion.py
---

# Plan 1.02: Local Workspace and Remote GitHub Repository Ingestion Engine

<objective>
Implement repository ingestion supporting both local directories and remote GitHub repositories (with branch, commit, and PR support), file filtering (excluding binaries, large files, and ignored patterns), automatic language detection, and dependency manifest parsing for Python and JavaScript/TypeScript.

Purpose: Fulfill REQ-01 and REQ-02 by providing a reliable source ingestion pipeline that converts raw repos into sanitized, structured `IngestedFile` and `RepositorySummary` objects.
Output: `src/ingestion/local.py`, `src/ingestion/github.py`, `src/ingestion/detector.py`, `src/api/routes/ingest.py`, and comprehensive test suite in `tests/test_ingestion.py`.
</objective>

<context>
Load for context:
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- .gsd/REQUIREMENTS.md
- src/core/config.py
- src/core/models.py
</context>

<tasks>

<task type="auto">
  <name>Build local directory traversal scanner with path filtering, gitignore support, and file safety checks</name>
  <files>
    src/ingestion/__init__.py
    src/ingestion/local.py
  </files>
  <action>
    Implement local directory scanner in `src/ingestion/local.py`:
    
    1. Define default ignore patterns:
       - Directories: `.git`, `node_modules`, `__pycache__`, `.venv`, `venv`, `env`, `.env`, `dist`, `build`, `.next`, `.nuxt`, `.pytest_cache`, `.mypy_cache`, `.tox`, `.idea`, `.vscode`
       - Binary & non-code extensions: `.png`, `.jpg`, `.jpeg`, `.gif`, `.ico`, `.svg`, `.pdf`, `.zip`, `.tar`, `.gz`, `.exe`, `.dll`, `.so`, `.dylib`, `.woff`, `.woff2`, `.ttf`, `.eot`, `.pyc`, `.pyo`, `.db`, `.sqlite`, `.lock`
    
    2. Implement `is_binary_file(file_path: Path) -> bool`:
       - Quick check for common binary extensions.
       - Read first 1024 bytes; if null byte (`b'\x00'`) is found, treat as binary.
    
    3. Implement `LocalScanner` class:
       - `__init__(base_path: str | Path, max_file_size: int = 1048576, extra_ignores: list[str] | None = None)`
       - Validates `base_path` exists and is a directory. Raises `ValueError` or `FileNotFoundError` if invalid.
       - Loads `.gitignore` from `base_path` if present using `pathspec.PathSpec.from_lines("gitwildmatch", lines)`.
       - Combines `.gitignore` rules with default ignore patterns.
       - Method `scan() -> list[IngestedFile]`:
         - Recursively traverses `base_path`.
         - Skips ignored directories and ignored files.
         - Skips files exceeding `max_file_size`.
         - Skips binary files.
         - Reads text files with UTF-8 encoding (fallback to latin-1 if decode error).
         - Resolves `relative_path` normalized with forward slashes (`/`).
         - Detects language from extension (`.py` -> `LanguageEnum.python`, `.js`/`.jsx` -> `LanguageEnum.javascript`, `.ts`/`.tsx` -> `LanguageEnum.typescript`).
         - Returns `list[IngestedFile]`.
    
    4. Provide convenience function `scan_local_directory(path: str | Path, ...) -> list[IngestedFile]`.
    
    AVOID: Loading giant binary files into memory; check file size before reading.
    USE: `pathspec` for standard Git wildmatch pattern matching so existing `.gitignore` files work out of the box.
  </action>
  <verify>
    python -c "from src.ingestion.local import scan_local_directory; files = scan_local_directory('.'); print('Successfully scanned directory, files found:', len(files))"
  </verify>
  <done>
    `LocalScanner` correctly traverses directories, skips ignored directories and binary files, and returns validated `IngestedFile` objects.
  </done>
</task>

<task type="auto">
  <name>Build remote GitHub repository ingestion engine supporting repo URLs, branches, commits, and PRs via archive streaming</name>
  <files>
    src/ingestion/github.py
  </files>
  <action>
    Implement remote GitHub repository retrieval in `src/ingestion/github.py`:
    
    1. Implement GitHub URL parser `parse_github_url(url: str) -> dict`:
       - Parses `https://github.com/{owner}/{repo}` (handles optional `.git` suffix).
       - Extracts branch/ref from `https://github.com/{owner}/{repo}/tree/{branch}`.
       - Extracts commit SHA from `https://github.com/{owner}/{repo}/commit/{sha}`.
       - Extracts PR number from `https://github.com/{owner}/{repo}/pull/{pr_number}`.
       - Returns `{"owner": owner, "repo": repo, "ref": ref, "pr_number": pr_number}`.
    
    2. Implement `GitHubIngestionService` class:
       - Uses `httpx.AsyncClient` with custom timeout (30s) and User-Agent header.
       - Uses `GITHUB_TOKEN` from parameters or `get_settings().github_token` for authorization (`Authorization: Bearer <token>`) when available.
       - If `pr_number` is provided:
         - Query GitHub API `GET /repos/{owner}/{repo}/pulls/{pr_number}`.
         - Extract head commit SHA and ref.
         - Query `GET /repos/{owner}/{repo}/pulls/{pr_number}/files` to get list of changed files for targeted review.
       - Downloads repository archive via `GET https://api.github.com/repos/{owner}/{repo}/zipball/{ref or 'main'}`.
       - If main fails with 404, fallback to master.
       - Streams zip archive to a temporary directory created with `tempfile.mkdtemp(prefix="gsd_github_")`.
       - Extracts zip safely (verifying member paths to prevent directory traversal attacks / Zip Slip).
       - Finds the root unpacked folder inside the zip.
       - Runs `LocalScanner` on the unpacked folder to produce `list[IngestedFile]`.
       - Provides helper method `cleanup_temp_dir(path: Path)` to remove temporary files.
    
    3. Implement async helper `ingest_github_repo(repo_url: str, ref: str | None = None, pr_number: int | None = None, token: str | None = None) -> tuple[str, list[IngestedFile]]`.
    
    AVOID: Making separate API calls for every single file in the repository (which exhausts rate limits).
    USE: Single zipball archive download with streaming extraction.
  </action>
  <verify>
    python -c "from src.ingestion.github import parse_github_url; res = parse_github_url('https://github.com/octocat/Hello-World/tree/master'); assert res['owner']=='octocat' and res['repo']=='Hello-World' and res['ref']=='master'; print('GitHub URL parser verified:', res)"
  </verify>
  <done>
    `parse_github_url` parses repo URLs, branches, commits, and PRs, and `GitHubIngestionService` provides zipball downloading and safe extraction.
  </done>
</task>

<task type="auto">
  <name>Implement language detection, dependency manifest parsing, and ingestion API routes</name>
  <files>
    src/ingestion/detector.py
    src/api/__init__.py
    src/api/routes/__init__.py
    src/api/routes/ingest.py
    src/main.py
    tests/test_ingestion.py
  </files>
  <action>
    Build language detection, dependency parsing, API endpoints, and comprehensive tests:
    
    1. In `src/ingestion/detector.py`:
       - Implement `detect_repository_languages(files: list[IngestedFile]) -> dict[str, int]`:
         - Counts files and lines per language (`python`, `javascript`, `typescript`).
       - Implement `parse_dependency_manifests(base_path: Path | str, files: list[IngestedFile]) -> list[DependencyManifest]`:
         - Detects Python dependency manifests:
           - `requirements.txt`: regex matches `^([a-zA-Z0-9_\-\.]+)\s*([=><~]=?\s*[^#\s]+)?` to extract dependency name and pinned version.
           - `pyproject.toml`: extracts dependencies from `[project.dependencies]` or `[tool.poetry.dependencies]` if present.
         - Detects JS/TS dependency manifests:
           - `package.json`: parses JSON, extracts `dependencies` and `devDependencies` mapping package name -> version string.
         - Returns `list[DependencyManifest]`.
       - Implement `create_repository_summary(source_type: IngestionSourceType, source_path_or_url: str, files: list[IngestedFile], base_path: Path | None = None) -> RepositorySummary`.
    
    2. In `src/api/routes/ingest.py`:
       - Create APIRouter with prefix `/api/v1/ingest`, tags=["Ingestion"].
       - Implement `POST /local`:
         - Accepts `request: LocalIngestRequest` body.
         - Executes `scan_local_directory`.
         - Calls `create_repository_summary`.
         - Returns `RepositorySummary`.
       - Implement `POST /github`:
         - Accepts `request: GitHubIngestRequest` body.
         - Calls `ingest_github_repo`.
         - Calls `create_repository_summary`.
         - Returns `RepositorySummary`.
    
    3. In `src/main.py`:
       - Include ingest router: `app.include_router(ingest_router)`.
    
    4. In `tests/test_ingestion.py`:
       - Test `LocalScanner` with a fixture folder containing Python, JS, and ignored files.
       - Test `parse_github_url` for repo root, branch URL, and PR URL.
       - Test `parse_dependency_manifests` for sample `requirements.txt` and `package.json` fixtures.
       - Test `POST /api/v1/ingest/local` via `TestClient`.
    
    AVOID: Crashing if a dependency file is invalid or malformed; log warning and continue.
    USE: Defensive JSON and regex parsing with explicit error handling.
  </action>
  <verify>
    python -m pytest tests/test_ingestion.py -v
  </verify>
  <done>
    `test_ingestion.py` passes all tests for local scanning, GitHub URL parsing, dependency manifest detection, and API endpoints.
  </done>
</task>

</tasks>

<must_haves>
After all tasks complete, verify:
- [ ] `scan_local_directory` filters out `.git`, binary files, and files above size limits
- [ ] `parse_github_url` extracts owner, repo, ref, and PR number
- [ ] `parse_dependency_manifests` extracts dependencies from `requirements.txt` and `package.json`
- [ ] `pytest tests/test_ingestion.py` passes cleanly
</must_haves>

<success_criteria>
- [ ] All tasks verified passing
- [ ] Must-haves confirmed
- [ ] Both local and GitHub ingestion pathways functional
</success_criteria>

