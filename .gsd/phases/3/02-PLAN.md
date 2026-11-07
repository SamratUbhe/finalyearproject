---
phase: 3
plan: "02"
wave: 2
depends_on:
  - "01"
files_modified:
  - src/storage/__init__.py
  - src/storage/history.py
  - src/api/routes/history.py
  - src/api/routes/review.py
  - src/cli/main.py
  - src/main.py
  - tests/test_history.py
autonomous: true
gap_closure: false
must_haves:
  truths:
    - "Review history storage saves complete ConsolidatedReview records as JSON in .gsd/reviews/{review_id}.json and maintains index.json metadata"
    - "Listing reviews returns chronological historical records with repo_id filtering and summary metrics"
    - "Comparison engine diffs two review scans and accurately identifies new findings, resolved findings, persistent findings, and risk score delta"
    - "FastAPI review endpoints (/api/v1/review/run) automatically persist completed review results to review history"
    - "History API routes (GET /api/v1/history, GET /api/v1/history/{id}, POST /api/v1/history/compare) are mounted in src/main.py"
    - "CLI supports 'reviewer history' command displaying past scans in a rich terminal table"
  artifacts:
    - src/storage/__init__.py
    - src/storage/history.py
    - src/api/routes/history.py
    - tests/test_history.py
---

# Plan 3.02: Review History Persistence, Scan Comparison Engine & History API

<objective>
Implement persistent review storage, scan-to-scan finding comparison, and dedicated history API routes. Build `ReviewHistoryStorage` to serialize completed review reports into JSON under `.gsd/reviews/` alongside a high-performance metadata index, implement a finding comparison algorithm to track newly introduced versus resolved vulnerabilities across revisions, auto-save review runs in the API, expose REST endpoints in `src/api/routes/history.py`, and add the `reviewer history` command to the CLI.

Purpose: Provide persistent review audit trails and revision-over-revision security posture tracking, fulfilling the review history backend requirements of REQ-09.
Output: `src/storage/__init__.py`, `src/storage/history.py`, `src/api/routes/history.py`, extended `src/api/routes/review.py`, extended `src/cli/main.py`, registered in `src/main.py`, and test suite `tests/test_history.py`.
</objective>

<context>
Load for context:
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- .gsd/REQUIREMENTS.md
- src/core/models.py
- src/api/routes/review.py
- src/cli/main.py
- src/main.py
</context>

<tasks>

<task type="auto">
  <name>Build Review History Storage and Comparison Engine</name>
  <files>
    src/storage/__init__.py
    src/storage/history.py
  </files>
  <action>
    Implement JSON-based review persistence and scan comparison logic:

    1. Create `src/storage/__init__.py`.

    2. In `src/storage/history.py`, implement `ReviewHistoryStorage`:
       - Configurable `storage_dir: Path` (defaults to `.gsd/reviews/` in workspace root, created automatically).
       - Method `save_review(review: ConsolidatedReview) -> Path`:
         * Serializes full `ConsolidatedReview` into `.gsd/reviews/{review.review_id}.json`.
         * Updates or appends entry in `.gsd/reviews/index.json` containing lightweight summary metadata:
           - `review_id`: UUID string
           - `repo_id`: repository identifier / folder name
           - `created_at`: ISO timestamp
           - `status`: review status
           - `total_files`: number of files
           - `total_chunks`: number of chunks
           - `total_findings`: count of moderated findings
           - `severity_distribution`: dict of severity counts
           - `max_risk_score`: highest risk score in review
         * Ensures thread-safe / atomic writes (write to temporary file and rename).
         * Returns saved file path.
       - Method `list_reviews(repo_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]`:
         * Reads `index.json`.
         * Filters by `repo_id` if specified.
         * Sorts entries descending by `created_at` (newest first).
         * Returns at most `limit` entries.
       - Method `get_review(review_id: str) -> Optional[ConsolidatedReview]`:
         * Loads `.gsd/reviews/{review_id}.json` and parses into `ConsolidatedReview`.
         * Returns `None` if file does not exist.
       - Method `delete_review(review_id: str) -> bool`:
         * Removes `.gsd/reviews/{review_id}.json` and updates `index.json`.
       - Method `compare_reviews(base_review_id: str, target_review_id: str) -> Dict[str, Any]`:
         * Loads `base_review = get_review(base_review_id)` and `target_review = get_review(target_review_id)`.
         * Raises `ValueError` if either review ID is not found.
         * Finding matching algorithm: Two findings `f1` and `f2` match as the same issue if:
           1. `f1.finding.evidence.file_path == f2.finding.evidence.file_path`
           2. Line spans overlap or are within a 5-line window: `abs(f1.finding.evidence.start_line - f2.finding.evidence.start_line) <= 5`
           3. CWE IDs match (if present) OR title tokens have >0.3 Jaccard similarity.
         * Categorizes findings into:
           - `new_findings`: findings present in `target_review` with no match in `base_review`.
           - `resolved_findings`: findings present in `base_review` no longer present in `target_review`.
           - `persistent_findings`: findings present in both runs.
         * Calculates metrics:
           - `base_review_id`, `target_review_id`
           - `base_total`, `target_total`
           - `new_count`, `resolved_count`, `persistent_count`
           - `risk_score_delta`: `target.max_risk_score - base.max_risk_score`
           - `critical_delta`: `target.critical_count - base.critical_count`
         * Returns structured comparison dictionary.

    AVOID: Re-reading and deserializing all large review JSON files on every list query.
    USE: A dedicated `index.json` metadata index for fast listing and filtering.
  </action>
  <verify>
    python -c "from src.storage.history import ReviewHistoryStorage; s = ReviewHistoryStorage(); assert s is not None; print('ReviewHistoryStorage successfully initialized')"
  </verify>
  <done>
    `ReviewHistoryStorage` reliably persists review reports, manages the metadata index, and computes accurate scan-to-scan diffs.
  </done>
</task>

<task type="auto">
  <name>Implement History API endpoints, review auto-saving, and CLI history command</name>
  <files>
    src/api/routes/history.py
    src/api/routes/review.py
    src/cli/main.py
    src/main.py
  </files>
  <action>
    Expose review history endpoints and integrate persistence across the review pipeline and CLI:

    1. In `src/api/routes/history.py`:
       - Create `APIRouter(prefix="/api/v1/history", tags=["Review History"])`.
       - Define request/response schemas:
         * `ReviewSummaryItem(BaseModel)`: summary metadata for list responses.
         * `CompareReviewsRequest(BaseModel)`: `base_review_id: str`, `target_review_id: str`.
       - Endpoints:
         * `GET /`: returns `List[ReviewSummaryItem]` matching optional `repo_id: Optional[str] = None` and `limit: int = 50`.
         * `GET /{review_id}`: returns `ConsolidatedReview` by ID. Raises 404 if not found.
         * `POST /compare`: takes `CompareReviewsRequest`, invokes `storage.compare_reviews`, returns comparison diff response.
         * `DELETE /{review_id}`: deletes stored review by ID, returns `{"status": "deleted", "review_id": review_id}`.

    2. In `src/api/routes/review.py`:
       - In `run_review_endpoint`, after `moderator.moderate_review` generates the `ConsolidatedReview`:
         * Call `ReviewHistoryStorage().save_review(review)` to automatically record every executed review.
         * Log storage confirmation with review ID.

    3. In `src/main.py`:
       - Import `history_router` from `src.api.routes.history`.
       - Register route: `app.include_router(history_router)`.

    4. In `src/cli/main.py`:
       - Add `history` subcommand:
         * Syntax: `reviewer history [--repo <repo_id>] [--limit <n>]`.
         * Queries `ReviewHistoryStorage().list_reviews()`.
         * Renders a styled Rich Table with columns: Review ID, Repository, Date, Total Findings, Critical, High, Medium, Max Risk Score.
       - In `reviewer scan`:
         * Ensure completed CLI scans are also saved via `ReviewHistoryStorage().save_review(review)` unless `--no-save` is passed.
         * Print notification: `[Review saved to history with ID: {review_id}]`.

    AVOID: Forgetting to register routers in `src/main.py`.
    USE: FastAPI `APIRouter` with explicit response models, status codes, and 404 handling.
  </action>
  <verify>
    python -c "from src.main import app; routes = [r.path for r in app.routes]; assert '/api/v1/history' in routes or any('/api/v1/history' in str(r.path) for r in app.routes); print('History routes successfully mounted')"
  </verify>
  <done>
    `/api/v1/history` endpoints are live in FastAPI, reviews auto-save on completion, and CLI supports `reviewer history`.
  </done>
</task>

<task type="auto">
  <name>Build test suite for review history storage, comparison engine, and API routes</name>
  <files>
    tests/test_history.py
  </files>
  <action>
    Create comprehensive tests in `tests/test_history.py`:

    1. Storage Unit Tests:
       - Use a temporary directory fixture (`tmp_path`) for isolated storage.
       - Test `save_review` writes JSON file and creates/updates `index.json`.
       - Test `list_reviews` returns saved reviews sorted newest first and filters by `repo_id`.
       - Test `get_review` retrieves exact `ConsolidatedReview` matching original.
       - Test `get_review` returns `None` for non-existent IDs.
       - Test `delete_review` removes file and cleans `index.json`.

    2. Comparison Engine Tests:
       - Construct `Review A` with findings 1 (SQLi at line 10) and 2 (Hardcoded key at line 50).
       - Construct `Review B` with finding 1 (SQLi still at line 12 - persistent), finding 3 (Command injection at line 80 - new). Finding 2 was removed (resolved).
       - Run `compare_reviews(Review A, Review B)`.
       - Assert `len(result['new_findings']) == 1` and matches Finding 3.
       - Assert `len(result['resolved_findings']) == 1` and matches Finding 2.
       - Assert `len(result['persistent_findings']) == 1` and matches Finding 1.
       - Assert `result['summary']['new_count'] == 1` and `result['summary']['resolved_count'] == 1`.

    3. API Integration Tests:
       - Use `httpx.AsyncClient` or FastAPI `TestClient` to test:
         * `GET /api/v1/history` returns 200 and list.
         * `GET /api/v1/history/{review_id}` returns 200 with matching review data.
         * `GET /api/v1/history/non-existent-id` returns 404.
         * `POST /api/v1/history/compare` returns 200 and diff structure.
         * `DELETE /api/v1/history/{review_id}` returns 200.

    4. CLI Integration Test:
       - Invoke `history` CLI command handler with mocked storage returning records; verify table output is generated without exceptions.

    AVOID: Polluting the project's real `.gsd/reviews/` folder during automated test runs.
    USE: Pytest `tmp_path` fixture overriding `storage_dir` in tests.
  </action>
  <verify>
    python -m pytest tests/test_history.py -v
  </verify>
  <done>
    All unit and integration tests in `tests/test_history.py` pass cleanly.
  </done>
</task>

</tasks>

<must_haves>
After all tasks complete, verify:
- [ ] `ReviewHistoryStorage` serializes reviews to JSON and maintains `index.json`
- [ ] Comparison engine detects new, resolved, and persistent findings and computes risk deltas
- [ ] `/api/v1/history` endpoints list, fetch, compare, and delete stored reviews
- [ ] Reviews executed via `/api/v1/review/run` and CLI scans are automatically saved to history
- [ ] `reviewer history` displays past scans in a rich terminal table
- [ ] `pytest tests/test_history.py` passes 100%
</must_haves>

<success_criteria>
- [ ] All tasks verified passing
- [ ] Must-haves confirmed
- [ ] Review history and comparison engine fully operational and mounted
</success_criteria>

