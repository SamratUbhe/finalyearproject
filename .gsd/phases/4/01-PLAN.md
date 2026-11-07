---
phase: 4
plan: "01"
wave: 1
depends_on: []
files_modified:
  - src/reports/__init__.py
  - src/reports/html_generator.py
  - src/api/routes/reports.py
  - src/main.py
  - src/dashboard/static/index.html
  - src/dashboard/static/app.js
  - src/dashboard/static/style.css
autonomous: true
gap_closure: false
must_haves:
  truths:
    - "HTMLReportGenerator generates a self-contained, offline-ready HTML report containing complete consolidated review data without external CDN dependencies"
    - "HTML report includes an executive metrics summary (Total Findings, Risk Score, Severity Breakdown, Chunks Reviewed)"
    - "Each finding in the HTML report renders priority rank, severity badge, risk score, CWE badge, location, formatted code evidence with line numbers, and actionable remediation guidance"
    - "HTML report embeds a browser print stylesheet (@media print) enabling 1-click clean export to PDF or paper directly from any web browser"
    - "FastAPI endpoint GET /api/v1/reports/html/{review_id} retrieves and serves the HTML report by review ID"
    - "Web Dashboard Findings Explorer and Review History table provide one-click 'Export HTML' download actions"
  artifacts:
    - src/reports/__init__.py
    - src/reports/html_generator.py
    - src/api/routes/reports.py
---

# Plan 4.01: Standalone HTML Report Generation Engine & Dashboard Export

<objective>
Build the standalone HTML report generation engine for the Automated Code Vulnerability Reviewer. The engine transforms a `ConsolidatedReview` into a self-contained, professional, offline-ready HTML report featuring executive metrics cards, severity breakdown bars, prioritized finding cards with syntax-styled code snippets, and remediation guidelines. Expose the report via REST API endpoint (`GET /api/v1/reports/html/{review_id}`) and integrate 1-click export actions into the Web Dashboard's Findings Explorer and Review History table.

Purpose: Fulfill the HTML export requirements of REQ-10 and enable instant offline sharing and browser printing for academic review and developer audits.
Output: `src/reports/__init__.py`, `src/reports/html_generator.py`, `src/api/routes/reports.py`, updated `src/main.py`, and dashboard export UI in `src/dashboard/static/`.
</objective>

<context>
Load for context:
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- .gsd/REQUIREMENTS.md
- src/core/models.py
- src/storage/history.py
- src/dashboard/static/index.html
- src/dashboard/static/app.js
- src/dashboard/static/style.css
- src/main.py
</context>

<tasks>

<task type="auto">
  <name>Build standalone HTML report generator module</name>
  <files>
    src/reports/__init__.py
    src/reports/html_generator.py
  </files>
  <action>
    Create `src/reports/__init__.py` and implement `HTMLReportGenerator` in `src/reports/html_generator.py`:

    1. Class `HTMLReportGenerator`:
       - Method `generate(review: ConsolidatedReview) -> str`:
         * Produces a clean, single-page standalone HTML5 document.
         * Zero external CDN dependencies (all styles, fonts, and SVG icons embedded directly inline).
         * Header section: Project branding ("Automated Code Vulnerability Reviewer"), Review ID, Target Repository/Path, Scan Timestamp, Ingestion Mode, and Total Chunks Reviewed.
         * Executive Summary Dashboard:
           - Metric Cards: Overall Risk Score (Max & Avg), Total Findings Discovered, Deduplicated Duplicates, Agent Contributions.
           - Severity distribution breakdown (Critical, High, Medium, Low, Info counts with colored badges).
         * Prioritized Findings Section:
           - Iterates through `review.findings` ordered by `priority_rank`.
           - Each finding card includes:
             * Header bar: Priority rank badge (e.g. `#1`), Severity badge, Risk score badge (e.g. `Score: 10.0`), finding title.
             * Metadata line: CWE tag (e.g. `CWE-89`), OWASP category, Source Agent(s), Target File & Line Range (`file:lines`).
             * Code Evidence box: Monospace container with line-numbered snippet, visual callout of vulnerable statement, and dark background.
             * Remediation Guidance: Distinct section with recommended fix explanation and actionable remediation advice.
         * Advisory Guidance Disclaimer Banner (REQ-11):
           - Clear standard warning: "AI-generated recommendations provide advisory architectural and security guidance. Automated suggestions must be evaluated and verified by qualified developers before deployment."
         * Print stylesheet (`@media print`):
           - White/light background, high-contrast borders, page-break management (`break-inside: avoid` on finding cards) so prints and browser "Save to PDF" output look neat and publication-ready.
       - Method `save_to_file(review: ConsolidatedReview, file_path: Path) -> Path`:
         * Renders HTML and writes to disk with UTF-8 encoding.
  </action>
  <verify>
    Run a python command to generate an HTML report from an existing test review in `.gsd/reviews/` and verify the file is created with valid HTML, embedded CSS, and non-empty content.
  </verify>
</task>

<task type="auto">
  <name>Expose HTML report REST API endpoint in FastAPI</name>
  <files>
    src/reports/html_generator.py
    src/api/routes/reports.py
    src/main.py
  </files>
  <action>
    1. Create `src/api/routes/reports.py` with FastAPI router `router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])`:
       - `GET /api/v1/reports/html/{review_id}`:
         * Query `ReviewHistoryStorage.get_review(review_id)`. If not found, return 404 HTTP exception.
         * Generate HTML string using `HTMLReportGenerator().generate(review)`.
         * Return as `HTMLResponse(content=html_content, status_code=200, headers={"Content-Disposition": f'inline; filename="review-{review_id}.html"'})` or download parameter `download=true` triggering attachment disposition.
    2. Register `reports_router` in `src/main.py`.
  </action>
  <verify>
    Test endpoint `GET /api/v1/reports/html/{review_id}` using `TestClient` or `curl` on a known review ID.
  </verify>
</task>

<task type="auto">
  <name>Integrate HTML export buttons and triggers into Web Dashboard</name>
  <files>
    src/dashboard/static/index.html
    src/dashboard/static/app.js
    src/dashboard/static/style.css
  </files>
  <action>
    1. In `src/dashboard/static/index.html`:
       - In the Findings Explorer top bar / summary bar: Add an action button group:
         * `<button class="btn-export" onclick="exportCurrentReport('html')"><span>📄</span> Export HTML</button>`
         * `<button class="btn-export" onclick="exportCurrentReport('pdf')"><span>📑</span> Export PDF</button>`
       - In the Review History table: Add quick download links/buttons in the "Actions" column:
         * `<button class="btn-table-action" onclick="downloadReport('${rev.review_id}', 'html')" title="Download HTML">📄 HTML</button>`
         * `<button class="btn-table-action" onclick="downloadReport('${rev.review_id}', 'pdf')" title="Download PDF">📑 PDF</button>`
    2. In `src/dashboard/static/app.js`:
       - Add `exportCurrentReport(format)`:
         * Checks if `state.currentReview` is loaded. If not, alerts user to load/run a review first.
         * Opens `/api/v1/reports/${format}/${state.currentReview.review_id}?download=true` in a new tab or triggers direct browser download.
       - Add `downloadReport(reviewId, format)`:
         * Triggers direct browser download for `/api/v1/reports/${format}/${reviewId}?download=true`.
    3. In `src/dashboard/static/style.css`:
       - Add styles for `.btn-export` and `.btn-table-action` matching the existing dark theme aesthetic with subtle gradients, hover transitions, and responsive sizing.
  </action>
  <verify>
    Verify browser static files load cleanly and test functions in a headless test or API mock test.
  </verify>
</task>

</tasks>

<verification>
- `python -c "from src.reports.html_generator import HTMLReportGenerator; print('HTML generator imported successfully')"`
- Successful generation of standalone HTML report for a test review.
- Endpoint `GET /api/v1/reports/html/{review_id}` returns 200 OK with `text/html`.
</verification>

<success_criteria>
- Standalone HTML report generated with 0 external network dependencies.
- HTML report contains complete findings, severity metrics, code evidence, and advisory disclaimer.
- Report includes responsive layout and `@media print` styling for browser printing.
- Dashboard supports 1-click HTML export for both active scan and historical scans.
</success_criteria>

