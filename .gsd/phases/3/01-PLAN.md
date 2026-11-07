---
phase: 3
plan: "01"
wave: 1
depends_on: []
files_modified:
  - requirements.txt
  - src/cli/__init__.py
  - src/cli/formatter.py
  - src/cli/runner.py
  - src/cli/main.py
  - tests/test_cli.py
autonomous: true
gap_closure: false
must_haves:
  truths:
    - "CLI executes complete automated vulnerability reviews on local directory paths via 'reviewer scan <path>' with colored terminal tables and severity badges"
    - "CLI supports remote GitHub repository scans via 'reviewer scan --github <url>' with branch, tag, and PR options"
    - "CLI displays live progress spinners and agent status indicators during ingestion, context chunking, and parallel multi-agent analysis"
    - "Findings cards and tables format severity, CWE identifiers, code evidence with line numbers, and purely advisory remediation advice"
    - "CLI supports --json flag for automated output piping and --output for saving review reports to disk"
  artifacts:
    - requirements.txt
    - src/cli/__init__.py
    - src/cli/formatter.py
    - src/cli/runner.py
    - src/cli/main.py
    - tests/test_cli.py
---

# Plan 3.01: Command-Line Interface (CLI) with Rich Terminal Output & Workflows

<objective>
Implement the Command-Line Interface (CLI) for the Automated Code Vulnerability Reviewer using the Rich library. The CLI provides developers with a terminal interface to initiate automated code scans on local directory paths (`reviewer scan <path>`) and remote GitHub repositories (`reviewer scan --github <url>`), view real-time animated progress spinners and agent status indicators, and inspect formatted vulnerability reports with colored severity badges, findings tables, code evidence panels, and summary metrics.

Purpose: Fulfill REQ-08 by providing a developer-friendly, terminal-native scan and inspection experience with scriptable JSON output capabilities.
Output: Extended `requirements.txt`, `src/cli/__init__.py`, `src/cli/formatter.py`, `src/cli/runner.py`, `src/cli/main.py`, and test suite `tests/test_cli.py`.
</objective>

<context>
Load for context:
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- .gsd/REQUIREMENTS.md
- src/core/models.py
- src/ingestion/local.py
- src/ingestion/github.py
- src/parser/chunker.py
- src/orchestrator/runner.py
- src/moderator/moderator.py
</context>

<tasks>

<task type="auto">
  <name>Add rich dependencies and build terminal presentation formatting module</name>
  <files>
    requirements.txt
    src/cli/__init__.py
    src/cli/formatter.py
  </files>
  <action>
    Add required terminal presentation dependencies and create formatting utilities:

    1. In `requirements.txt`, append:
       - `rich>=13.7.0` (for colored badges, tables, panels, and spinners)
       - `aiofiles>=23.2.1` (for async static file serving and I/O)

    2. Create `src/cli/__init__.py`.

    3. In `src/cli/formatter.py`, implement `CLIFormatter` class:
       - Console configuration: initialize `rich.console.Console`.
       - Color and style mappings for `SeverityEnum`:
         * `CRITICAL`: `bold white on red` or `bold red`
         * `HIGH`: `bold red`
         * `MEDIUM`: `bold yellow`
         * `LOW`: `bold cyan`
         * `INFO`: `dim cyan`
       - Method `format_severity_badge(severity: SeverityEnum) -> Text`: returns styled Rich Text badge `[CRITICAL]`, `[HIGH]`, etc.
       - Method `format_finding_card(finding: ModeratedFinding) -> Panel`:
         * Title bar with priority rank (`#1`), severity badge, risk score (e.g. `Score: 10.0`), and title.
         * Metadata section: Agent sources, category, CWE identifier (e.g. `CWE-89`), OWASP category.
         * Location: `File: {file_path}:{start_line}-{end_line}`.
         * Code evidence snippet displayed inside a syntax-highlighted panel (`rich.syntax.Syntax`) with line numbers.
         * Remediation advice: Explanation and recommended fix pattern.
         * Advisory disclaimer note if applicable.
       - Method `format_findings_table(findings: List[ModeratedFinding], min_severity: Optional[SeverityEnum] = None) -> Table`:
         * Creates a `rich.table.Table` with columns:
           - Rank (`#`)
           - Severity
           - Risk Score
           - Title
           - CWE / Category
           - Location (`file:lines`)
           - Source Agents
         * Filters findings where severity meets or exceeds `min_severity` if specified.
       - Method `format_summary_panel(review: ConsolidatedReview) -> Panel`:
         * Summarizes total files reviewed, total chunks reviewed, total findings.
         * Displays counts broken down by severity (Critical, High, Medium, Low, Info).
         * Displays top risk score and average risk score.
         * Displays standard advisory disclaimer prominently.
       - Method `format_json_output(review: ConsolidatedReview) -> str`:
         * Serializes `ConsolidatedReview` into formatted indented JSON for CLI pipe / stdout redirection.

    AVOID: Hardcoded ANSI escape codes that break across different terminal emulators on Windows or Linux.
    USE: High-level Rich components (`Console`, `Table`, `Panel`, `Text`, `Syntax`) with automatic terminal capability detection.
  </action>
  <verify>
    python -c "from src.cli.formatter import CLIFormatter; f = CLIFormatter(); assert f is not None; print('CLIFormatter imported and initialized successfully')"
  </verify>
  <done>
    `requirements.txt` contains `rich` and `aiofiles`, and `src/cli/formatter.py` provides complete formatting for badges, findings tables, cards, and summary panels.
  </done>
</task>

<task type="auto">
  <name>Implement scan execution runner and rich CLI entrypoint</name>
  <files>
    src/cli/runner.py
    src/cli/main.py
  </files>
  <action>
    Implement the core CLI scanning engine and command-line entrypoint:

    1. In `src/cli/runner.py`, implement `CLIScanRunner`:
       - `async def run_scan(target: str, is_github: bool = False, ref: Optional[str] = None, token: Optional[str] = None, pr_number: Optional[int] = None, max_file_size: Optional[int] = None, on_progress: Optional[Callable] = None) -> ConsolidatedReview`:
         * Stage 1: Ingestion
           - If `is_github` (or target starts with `http://`, `https://`, or `github.com`):
             Calls `ingest_github_repo(target, ref=ref, pr_number=pr_number, token=token)`.
             Constructs `RepositorySummary` using `create_repository_summary`.
             Ensures temporary extracted directories are cleaned up safely in `finally`.
           - If local directory:
             Validates path exists and is a directory (raises `FileNotFoundError` or `ValueError` with clear message).
             Calls `scan_local_directory(target)`.
             Constructs `RepositorySummary`.
         * Stage 2: Context Preparation
           - Invokes `ContextPreparationEngine().prepare_repository_context(summary)`.
         * Stage 3: Multi-Agent Parallel Review
           - Invokes `ReviewOrchestrator().run_review(context, progress_callback=on_progress)`.
         * Stage 4: Review Moderation & Risk Scoring
           - Invokes `ReviewModeratorAgent().moderate_review(context.repo_id, agent_results, len(summary.files), context.total_chunks)`.
           - Returns completed `ConsolidatedReview`.

    2. In `src/cli/main.py`, implement the terminal interface:
       - Configured as executable module (`python -m src.cli.main` or `reviewer` script).
       - Uses `argparse.ArgumentParser` with description "Automated Code Vulnerability Reviewer CLI".
       - Commands & Arguments:
         * `path`: Positional string argument for local folder path (default: current directory `.` if `--github` is not specified).
         * `--github`: Remote GitHub repository URL.
         * `--ref`: Git branch, tag, or commit SHA.
         * `--pr`: GitHub pull request number.
         * `--token`: GitHub personal access token (defaults to `GITHUB_TOKEN` environment variable).
         * `--min-severity`: Minimum severity filter for display (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`).
         * `--json`: Flag to output pure JSON to stdout (disabling rich terminal panels for CI integration).
         * `--output <file>`: File path to save review JSON report.
         * `--detailed`: Flag to print full finding cards with code snippets in addition to the overview table.
       - Terminal Progress Animation:
         * Uses `rich.progress.Progress` with spinner, text description, and progress bar.
         * Shows live updates: "Ingesting repository...", "Parsing AST chunks...", "Analyzing chunks with Security and Architect agents (chunk X/Y)...", "Moderating findings...".
       - Output Rendering:
         * On completion, prints:
           1. Findings summary panel (total issues, severity breakdown).
           2. Overview findings table sorted by priority rank.
           3. If `--detailed` or if critical issues exist: renders code evidence panels with remediation advice.
           4. Advisory disclaimer footer (REQ-11).
         * If `--output` is provided, writes JSON report to the file and logs confirmation.
       - Exit codes: 0 for successful execution; 1 for command or input validation errors; 2 if critical vulnerabilities are detected (optional gate for CI/CD).

    AVOID: Blocking the terminal without progress feedback during lengthy LLM analysis calls.
    USE: Rich Progress spinners and progress callback hooks connected to `ReviewOrchestrator`.
  </action>
  <verify>
    python -m src.cli.main --help
  </verify>
  <done>
    `src/cli/runner.py` coordinates the complete ingestion-to-moderation pipeline, and `python -m src.cli.main --help` outputs comprehensive command-line documentation.
  </done>
</task>

<task type="auto">
  <name>Build CLI test suite and verify commands and formatting</name>
  <files>
    tests/test_cli.py
  </files>
  <action>
    Create automated tests for the CLI in `tests/test_cli.py`:

    1. Test CLI argument parser:
       - Local path scanning syntax: `scan /path/to/project`.
       - GitHub flag syntax: `--github https://github.com/owner/repo --ref main`.
       - Filter and output flags: `--json`, `--output report.json`, `--min-severity HIGH`, `--detailed`.
       - Default argument fallbacks.

    2. Test `CLIFormatter`:
       - Severity badge rendering for all `SeverityEnum` values.
       - Findings table generation with mock findings.
       - Minimum severity filtering in `format_findings_table`.
       - Finding card generation including code evidence syntax rendering and remediation advice.
       - Summary panel rendering with severity distribution counts.
       - JSON serialization output matching `ConsolidatedReview` schema.

    3. Test `CLIScanRunner`:
       - Mock local scan execution using temporary directory with sample `.py` file; verify `run_scan` produces `ConsolidatedReview`.
       - Mock GitHub scan execution using mocked `ingest_github_repo`.
       - Test error handling when given a non-existent local directory path.

    4. Test `main` CLI execution via `unittest.mock`:
       - Test CLI execution with `--json` outputs valid JSON string.
       - Test CLI execution with `--output` creates expected file.

    AVOID: Invoking real live Gemini or GitHub API endpoints in unit tests.
    USE: Mocked agent responses and fixtures returning valid `AgentResult` and `RepositorySummary` objects.
  </action>
  <verify>
    python -m pytest tests/test_cli.py -v
  </verify>
  <done>
    All unit and integration tests in `tests/test_cli.py` pass cleanly.
  </done>
</task>

</tasks>

<must_haves>
After all tasks complete, verify:
- [ ] `requirements.txt` contains `rich` and `aiofiles`
- [ ] `CLIFormatter` renders styled badges, tables, panels, and syntax-highlighted code evidence
- [ ] `CLIScanRunner` coordinates ingestion, AST chunking, parallel agents, and moderation
- [ ] CLI entrypoint executes scans with progress spinners and supports `--json`, `--output`, and `--min-severity`
- [ ] `pytest tests/test_cli.py` passes 100%
</must_haves>

<success_criteria>
- [ ] All tasks verified passing
- [ ] Must-haves confirmed
- [ ] Terminal CLI operational for local and remote scans fulfilling REQ-08
</success_criteria>

