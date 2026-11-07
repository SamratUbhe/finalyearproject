---
phase: 3
plan: "03"
wave: 3
depends_on:
  - "02"
files_modified:
  - src/dashboard/__init__.py
  - src/dashboard/router.py
  - src/dashboard/static/index.html
  - src/dashboard/static/style.css
  - src/dashboard/static/app.js
  - src/main.py
  - tests/test_dashboard.py
autonomous: true
gap_closure: false
must_haves:
  truths:
    - "Local Web Dashboard is mounted in FastAPI at /dashboard and redirects from / for immediate developer access"
    - "Dashboard provides review initiation for both local folder paths and remote GitHub repository URLs"
    - "Live agent telemetry displays real-time status, execution progress, and metrics for Security Auditor, Software Architect, and Review Moderator agents"
    - "Interactive findings explorer provides multi-attribute filtering by severity, agent role, category, and text search, displaying code evidence with line numbers and remediation advice"
    - "Review history view allows developers to browse past scans, inspect past findings, and perform side-by-side scan comparisons with visual diff breakdowns"
  artifacts:
    - src/dashboard/__init__.py
    - src/dashboard/router.py
    - src/dashboard/static/index.html
    - src/dashboard/static/style.css
    - src/dashboard/static/app.js
    - tests/test_dashboard.py
---

# Plan 3.03: Local Web Dashboard with Live Telemetry, Findings Explorer & History Viewer

<objective>
Build and mount the Local Web Dashboard frontend in `src/dashboard/`, served directly by the FastAPI application. The dashboard gives developers a responsive, modern single-page interface to launch vulnerability reviews against local folders or GitHub repositories, monitor live agent telemetry across the Security Auditor, Software Architect, and Review Moderator agents, explore and filter prioritized findings with syntax-highlighted code evidence and remediation guidance, and browse persistent review history with scan-to-scan diff comparisons.

Purpose: Fulfill REQ-09 by delivering the developer-facing Web Dashboard interface unifying review initiation, live agent telemetry, findings inspection, and audit history.
Output: `src/dashboard/__init__.py`, `src/dashboard/router.py`, `src/dashboard/static/index.html`, `src/dashboard/static/style.css`, `src/dashboard/static/app.js`, mounted in `src/main.py`, and test suite `tests/test_dashboard.py`.
</objective>

<context>
Load for context:
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- .gsd/REQUIREMENTS.md
- src/core/models.py
- src/cli/runner.py
- src/storage/history.py
- src/api/routes/history.py
- src/main.py
</context>

<tasks>

<task type="auto">
  <name>Build responsive Dashboard UI layout and styling</name>
  <files>
    src/dashboard/__init__.py
    src/dashboard/static/index.html
    src/dashboard/static/style.css
  </files>
  <action>
    Create the modern developer dashboard HTML structure and styling:

    1. Create `src/dashboard/__init__.py`.

    2. Create `src/dashboard/static/index.html`:
       - Top Navigation Header:
         * Framework brand: "Automated Code Vulnerability Reviewer" with logo/icon and version badge (`v1.0.0`).
         * Backend health & connectivity indicator (green "Backend Connected" pill).
         * Tab navigation bar:
           - `Tab 1: New Review`
           - `Tab 2: Findings Explorer`
           - `Tab 3: Review History & Comparison`
       - Tab 1 View - New Review:
         * Dual-mode source selector: "Local Folder Path" vs "GitHub Repository".
         * Local inputs: Path input with current directory placeholder, extra ignores input.
         * GitHub inputs: Repository URL input, Branch/Ref input, optional GitHub Token input.
         * "Launch Vulnerability Review" prominent action button.
         * Live Agent Telemetry Panel:
           - Stepper / Progress Bar: Stage 1 Ingestion -> Stage 2 Context Preparation (AST) -> Stage 3 Multi-Agent Parallel Analysis -> Stage 4 Review Moderation.
           - Agent Telemetry Cards:
             * Security Auditor Agent card: status pill, findings count, execution time, OWASP checks badge.
             * Software Architect Agent card: status pill, findings count, execution time, complexity checks badge.
             * Review Moderator Agent card: status pill, deduplication count, arbitration status.
       - Tab 2 View - Findings Explorer:
         * Summary Metrics Bar: Total Findings, Critical, High, Medium, Low, Max Risk Score.
         * Interactive Filter Controls:
           - Text search input: filter by issue title, file path, or CWE identifier.
           - Severity toggle buttons: All, Critical, High, Medium, Low, Info.
           - Agent dropdown: All Agents, Security Auditor, Software Architect.
           - Category dropdown: All Categories, Injection, Cryptography, Complexity, Resource Management, etc.
         * Findings List Container:
           - Cards rendered dynamically with Priority Rank badge, Severity badge, Risk score, Title, Category, File & Line location.
           - Expandable Code Evidence block: Monospace font, line numbers, styled code preview.
           - Remediation Advice block: Explanation, recommended fix, reference links.
           - Advisory Disclaimer banner at bottom of findings.
       - Tab 3 View - Review History & Comparison:
         * Historical Scans Table: Columns for Review ID, Repository, Date/Time, Findings count, Critical count, Max Risk, Actions ("Inspect Findings", "Select for Compare").
         * Scan Comparison Section:
           - Dropdown selector for Base Scan (V1) and Target Scan (V2).
           - "Compare Scans" button.
           - Diff Results Panel: New Findings (+), Resolved Findings (-), Persistent Findings (=), Risk Score Delta card.

    3. Create `src/dashboard/static/style.css`:
       - Developer-focused dark mode theme:
         * Background colors: dark slate `--bg: #0f172a`, card `--card: #1e293b`, header `--header: #0b1120`, border `--border: #334155`.
         * Accent colors: cyan `#06b6d4`, purple `#8b5cf6`, blue `#3b82f6`.
         * Severity palette:
           - Critical: `#ef4444` (badge background: `rgba(239, 68, 68, 0.2)`, text: `#fca5a5`, border: `#ef4444`)
           - High: `#f97316` (badge background: `rgba(249, 115, 22, 0.2)`, text: `#fdba74`, border: `#f97316`)
           - Medium: `#eab308` (badge background: `rgba(234, 179, 8, 0.2)`, text: `#fde047`, border: `#eab308`)
           - Low: `#06b6d4` (badge background: `rgba(6, 182, 212, 0.2)`, text: `#67e8f9`, border: `#06b6d4`)
           - Info: `#64748b` (badge background: `rgba(100, 116, 139, 0.2)`, text: `#cbd5e1`, border: `#64748b`)
       - Code snippet styling: dark code block background `#0d1117`, syntax highlight contrast, line number gutter.
       - Animated pulse and spinner effects for running agent stages.
       - Fully responsive grid and flexbox layout.

    AVOID: Bulky external frontend frameworks (like React/Vue compilation setups) that require Node.js builds or npm tooling.
    USE: Clean, zero-build, native modern HTML5 and responsive CSS variables that run immediately from FastAPI.
  </action>
  <verify>
    python -c "import os; assert os.path.exists('src/dashboard/static/index.html') and os.path.exists('src/dashboard/static/style.css'); print('Dashboard UI files successfully verified')"
  </verify>
  <done>
    `src/dashboard/static/index.html` and `src/dashboard/static/style.css` exist and provide responsive UI layouts for review launching, live telemetry, findings exploration, and history comparison.
  </done>
</task>

<task type="auto">
  <name>Implement frontend client logic and dashboard review runner endpoints</name>
  <files>
    src/dashboard/router.py
    src/dashboard/static/app.js
  </files>
  <action>
    Implement backend dashboard routing and frontend client interactivity:

    1. In `src/dashboard/router.py`:
       - Create `router = APIRouter(tags=["Dashboard"])`.
       - Endpoint `GET /dashboard`: returns `FileResponse("src/dashboard/static/index.html")`.
       - Endpoint `POST /api/v1/dashboard/scan`:
         * Request schema:
           ```python
           class DashboardScanRequest(BaseModel):
               source_type: str = "local"  # "local" or "github"
               path_or_url: str
               ref: Optional[str] = None
               token: Optional[str] = None
               pr_number: Optional[int] = None
           ```
         * Uses `CLIScanRunner` to execute scan:
           - Ingestion (local or github)
           - Context preparation
           - Parallel agent execution
           - Review moderation
         * Saves result via `ReviewHistoryStorage().save_review(review)`.
         * Returns `ConsolidatedReview`.
         * Catches errors and returns formatted 400/500 JSON errors.

    2. In `src/dashboard/static/app.js`:
       - Single-page application logic in vanilla modern JavaScript:
         * Navigation: `switchTab(tabId)` manages active tab state and views.
         * Source type toggle: Switches form fields between Local folder and GitHub URL.
         * Review execution (`startReview()`):
           - Validates inputs.
           - Displays live telemetry panel and activates animated pipeline steps.
           - Sends `POST /api/v1/dashboard/scan`.
           - Simulates agent progress steps during execution.
           - On success: switches to Findings Explorer tab, loads review findings into state, and renders summary counters and cards.
           - On failure: displays descriptive error banner.
         * Findings Explorer (`renderFindings()`):
           - Reactive filtering: filters active findings by search keyword, severity pills, agent role dropdown, and category.
           - Renders finding cards with priority rank, severity badge, risk score, location, CWE badge, code evidence with line numbers, and advisory remediation guidance.
           - Renders advisory disclaimer banner (REQ-11).
         * History & Comparison (`loadHistory()`, `compareScans()`):
           - `loadHistory()`: calls `GET /api/v1/history`, populates past scans table.
           - "View Findings" button: loads that historical scan directly into Findings Explorer.
           - "Select for Compare": selects Base and Target reviews.
           - `compareScans()`: calls `POST /api/v1/history/compare`, renders diff breakdown:
             * New findings list with green/red badges.
             * Resolved findings list.
             * Risk score delta indicator.

    AVOID: Complex frontend state libraries or unhandled network failure states.
    USE: Modular vanilla JavaScript with native `fetch`, DOM template rendering, and instant filter reaction.
  </action>
  <verify>
    python -c "from src.dashboard.router import router; assert router is not None; print('Dashboard router successfully loaded')"
  </verify>
  <done>
    `src/dashboard/router.py` exposes `/dashboard` and `/api/v1/dashboard/scan`; `src/dashboard/static/app.js` powers real-time review execution, live telemetry, reactive findings filtering, and history comparison.
  </done>
</task>

<task type="auto">
  <name>Mount dashboard to FastAPI and build integration test suite</name>
  <files>
    src/main.py
    tests/test_dashboard.py
  </files>
  <action>
    Mount dashboard endpoints and static assets in the main application, and write full integration tests:

    1. In `src/main.py`:
       - Import `router as dashboard_router` from `src.dashboard.router`.
       - Mount static assets:
         ```python
         from fastapi.staticfiles import StaticFiles
         app.mount("/static", StaticFiles(directory="src/dashboard/static"), name="static")
         ```
       - Include dashboard router: `app.include_router(dashboard_router)`.
       - Add root redirect endpoint:
         ```python
         @app.get("/", include_in_schema=False)
         async def root_redirect():
             from fastapi.responses import RedirectResponse
             return RedirectResponse(url="/dashboard")
         ```

    2. In `tests/test_dashboard.py`:
       - Use `httpx.AsyncClient` or FastAPI `TestClient` to verify:
         * `GET /dashboard` returns 200 OK and contains HTML content.
         * `GET /` redirects (307/302) to `/dashboard`.
         * `GET /static/style.css` returns 200 OK with `text/css` header.
         * `GET /static/app.js` returns 200 OK with `javascript` header.
         * `POST /api/v1/dashboard/scan` with mocked `CLIScanRunner` returns 200 OK and valid `ConsolidatedReview`.
         * `POST /api/v1/dashboard/scan` with invalid inputs returns 400/500 with descriptive error.
       - End-to-end integration check: Verify all routers (`/health`, `/api/v1/ingest`, `/api/v1/context`, `/api/v1/review`, `/api/v1/history`, `/dashboard`, `/static`) coexist without path collisions.

    AVOID: Path collisions where static file mounting shadows API routes.
    USE: Explicit `/static` prefix for static assets and `/dashboard` for the web UI.
  </action>
  <verify>
    python -m pytest tests/test_dashboard.py -v
  </verify>
  <done>
    Dashboard is mounted in FastAPI at `/dashboard`, static assets are served, root `/` redirects to dashboard, and all tests in `test_dashboard.py` pass cleanly.
  </done>
</task>

</tasks>

<must_haves>
After all tasks complete, verify:
- [ ] Local Web Dashboard is accessible at `http://127.0.0.1:8000/dashboard` and root `/` redirects to it
- [ ] Review initiation form triggers scan on local paths or remote GitHub repositories
- [ ] Live agent telemetry visually reflects the stages and agent execution metrics
- [ ] Findings Explorer filters findings dynamically by severity, agent, category, and text query
- [ ] Code evidence panels display code snippets with line numbers and advisory remediation guidance
- [ ] Review History & Comparison view lists past scans and renders diffs between revisions
- [ ] `pytest tests/test_dashboard.py` passes 100%
</must_haves>

<success_criteria>
- [ ] All tasks verified passing
- [ ] Must-haves confirmed
- [ ] Local Web Dashboard fully operational fulfilling REQ-09
</success_criteria>

