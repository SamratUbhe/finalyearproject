---
phase: 4
plan: "02"
wave: 2
depends_on:
  - "01"
files_modified:
  - src/reports/pdf_generator.py
  - src/api/routes/reports.py
  - src/cli/main.py
  - src/cli/runner.py
  - tests/test_reports.py
autonomous: true
gap_closure: false
must_haves:
  truths:
    - "PDFReportGenerator compiles a professional, multi-page PDF document using ReportLab featuring an academic header, executive summary table, and detailed finding breakdown"
    - "Each finding in the PDF report includes severity badge styling, CWE identifiers, code evidence in a monospace boxed block, and actionable remediation advice"
    - "PDF pages include running headers, footers with 'Page X of Y' numbering, and the mandatory advisory guidance disclaimer banner (REQ-11)"
    - "FastAPI endpoint GET /api/v1/reports/pdf/{review_id} compiles and streams the PDF document as a downloadable attachment"
    - "CLI supports --export-html and --export-pdf options on 'reviewer scan' and provides a dedicated 'reviewer export <review_id>' command"
    - "Pytest test suite in tests/test_reports.py passes 100% across HTML generation, PDF generation, API endpoints, and CLI export flags"
  artifacts:
    - src/reports/pdf_generator.py
    - src/api/routes/reports.py
    - tests/test_reports.py
---

# Plan 4.02: Academic PDF Report Generator, CLI Export Flags & Test Suite

<objective>
Implement the server-side PDF report generator using `reportlab`, completing REQ-10 for the Automated Code Vulnerability Reviewer. The PDF generator builds an academic and professional audit document formatted for college defense presentations, featuring structured tabular summaries, color-coded severity indicators, monospace code evidence panels, and advisory disclaimers. Expose the PDF download endpoint in FastAPI, add `--export-html` and `--export-pdf` flags to the CLI, and construct a comprehensive test suite in `tests/test_reports.py`.

Purpose: Provide publication- and defense-ready PDF exports and CLI reporting workflows for offline dissemination.
Output: `src/reports/pdf_generator.py`, extended `src/api/routes/reports.py`, updated `src/cli/main.py`, `src/cli/runner.py`, and test suite `tests/test_reports.py`.
</objective>

<context>
Load for context:
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- .gsd/REQUIREMENTS.md
- src/core/models.py
- src/storage/history.py
- src/reports/html_generator.py
- src/api/routes/reports.py
- src/cli/main.py
- src/cli/runner.py
</context>

<tasks>

<task type="auto">
  <name>Build ReportLab PDF report generation engine</name>
  <files>
    src/reports/pdf_generator.py
  </files>
  <action>
    Create `src/reports/pdf_generator.py` implementing `PDFReportGenerator`:

    1. Class `NumberedCanvas(canvas.Canvas)`:
       - Custom canvas tracking total page count dynamically.
       - Renders running header: "Automated Code Vulnerability Reviewer | Security & Architecture Audit Report".
       - Renders running footer: "Page X of Y" and brief advisory note: "Advisory Guidance — Human Verification Required".

    2. Class `PDFReportGenerator`:
       - Uses `reportlab.platypus` (`SimpleDocTemplate`, `Paragraph`, `Spacer`, `Table`, `TableStyle`, `KeepTogether`, `Preformatted`).
       - Custom styles derived from `getSampleStyleSheet()`:
         * Document Title: 20pt Bold Navy (`#0f172a`), centered.
         * Subtitle: 10pt Dim Gray (`#64748b`), centered.
         * Section Headings: 14pt Bold Slate (`#1e293b`) with bottom accent line.
         * Finding Title: 12pt Bold with inline severity color tag.
         * Code evidence block: 8pt Monospace (`Courier`) inside a light gray shaded box (`#f1f5f9`) with border (`#cbd5e1`).
         * Remediation block: 9pt Dark Green (`#065f46`) inside a light green box (`#ecfdf5`).
       - Method `generate(review: ConsolidatedReview, output_path: Optional[Path] = None) -> bytes`:
         * Builds document flowables:
           1. Header Block: Title, Review ID, Target Repository, Scan Timestamp, Ingestion Engine, Analyzed Chunks.
           2. Executive Summary Table:
              - Severity breakdown (Critical, High, Medium, Low, Info) with background colors.
              - Multi-agent statistics: Security Auditor findings vs Software Architect findings vs Deduplicated duplicates.
              - Overall Max & Average Risk Score.
           3. Advisory Guidance Disclaimer Box (REQ-11):
              - Prominent boxed notice before findings indicating that all outputs are advisory and require human validation.
           4. Detailed Findings Breakdown:
              - Iterates through `review.findings` ordered by `priority_rank`.
              - Wraps each finding in `KeepTogether` where possible to prevent awkward mid-card page splits.
              - Finding Details: Priority rank, Severity badge, Title, CWE/Category, File Path & Line Numbers (`evidence.file_path:start_line-end_line`), Risk Score.
              - Formatted Code Evidence panel showing exact vulnerable lines.
              - Actionable Remediation box explaining the recommended architectural or security fix.
         * If `output_path` is provided, writes bytes to file; returns raw `bytes`.
  </action>
  <verify>
    Run a python script to generate a PDF from an existing review in `.gsd/reviews/` and verify the PDF file is created, has a valid `%PDF` header, non-zero size, and opens without errors.
  </verify>
</task>

<task type="auto">
  <name>Add PDF REST endpoint and CLI report export flags</name>
  <files>
    src/api/routes/reports.py
    src/cli/main.py
    src/cli/runner.py
  </files>
  <action>
    1. In `src/api/routes/reports.py`:
       - Add `GET /api/v1/reports/pdf/{review_id}`:
         * Queries `ReviewHistoryStorage.get_review(review_id)`.
         * Generates PDF bytes via `PDFReportGenerator().generate(review)`.
         * Returns `Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="review-{review_id}.pdf"'})`.

    2. In `src/cli/main.py` & `src/cli/runner.py`:
       - Add options to `reviewer scan`:
         * `--export-html PATH`: Exports standalone HTML report directly upon scan completion.
         * `--export-pdf PATH`: Exports professional PDF report directly upon scan completion.
       - Add new CLI command: `reviewer export <review_id>`:
         * Options: `--html PATH`, `--pdf PATH`.
         * Fetches stored review from `.gsd/reviews/` and writes the requested report format(s).
         * Displays rich status panels in terminal upon success.
  </action>
  <verify>
    Execute `python -m src.cli.main export --help` and verify `--html` and `--pdf` options appear. Test generating PDF via CLI.
  </verify>
</task>

<task type="auto">
  <name>Create comprehensive report test suite</name>
  <files>
    tests/test_reports.py
  </files>
  <action>
    Build unit and integration tests in `tests/test_reports.py`:
    1. Test `HTMLReportGenerator`:
       - Generates valid HTML string with expected title, review ID, findings, and disclaimer.
       - Correctly escapes HTML special characters in code snippets.
       - Embeds `@media print` CSS.
       - Generates valid report for reviews with 0 findings (empty state).
    2. Test `PDFReportGenerator`:
       - Generates valid PDF binary stream starting with `%PDF`.
       - Handles single-page and multi-page reports with page numbers.
       - Handles edge cases: missing code snippets, long file paths, unicode characters.
    3. Test FastAPI endpoints:
       - `GET /api/v1/reports/html/{valid_id}` returns 200 and `text/html`.
       - `GET /api/v1/reports/pdf/{valid_id}` returns 200 and `application/pdf`.
       - `GET /api/v1/reports/html/{invalid_id}` returns 404.
       - `GET /api/v1/reports/pdf/{invalid_id}` returns 404.
    4. Test CLI export functionality:
       - CLI `reviewer export` outputs HTML and PDF files correctly.
  </action>
  <verify>
    Run `pytest tests/test_reports.py -v` and confirm all tests pass.
  </verify>
</task>

</tasks>

<verification>
- `pytest tests/test_reports.py -v` passes with 0 failures.
- CLI command `reviewer export` successfully generates both HTML and PDF files.
- FastAPI report endpoints return valid content types (`text/html` and `application/pdf`).
</verification>

<success_criteria>
- ReportLab compiles multi-page PDF reports with professional academic formatting, running headers/footers, and page numbers.
- HTML and PDF reports satisfy all REQ-10 and REQ-11 criteria.
- CLI supports `--export-html` and `--export-pdf` flags.
- Comprehensive test suite achieves 100% pass rate.
</success_criteria>

