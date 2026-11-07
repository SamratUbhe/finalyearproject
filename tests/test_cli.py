"""Comprehensive unit and integration tests for CLI argument parsing, Rich presentation, and scan runners."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.cli.formatter import CLIFormatter, SEVERITY_ORDER
from src.cli.main import build_parser, execute_coroutine_sync, main, normalize_cli_args, run_cli_scan
from src.cli.runner import CLIScanRunner
from src.core.models import (
    AgentResult,
    AgentRoleEnum,
    CodeEvidence,
    ConfidenceEnum,
    ConsolidatedReview,
    Finding,
    IngestedFile,
    LanguageEnum,
    ModeratedFinding,
    RemediationAdvice,
    SeverityEnum,
)


@pytest.fixture
def sample_finding() -> ModeratedFinding:
    f = Finding(
        id="SEC-001",
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        category="Injection",
        cwe_id="CWE-89",
        owasp_category="A03:2021-Injection",
        title="SQL Injection Vulnerability",
        description="Unsanitized user input is concatenated into an SQL query string.",
        severity=SeverityEnum.CRITICAL,
        confidence=ConfidenceEnum.HIGH,
        evidence=CodeEvidence(
            file_path="src/database/query.py",
            start_line=12,
            end_line=14,
            code_snippet='query = f"SELECT * FROM users WHERE id = {user_id}"\ncursor.execute(query)',
        ),
        remediation=RemediationAdvice(
            explanation="Use parameterized queries rather than string formatting.",
            recommended_fix="cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
            references=["https://owasp.org/Top10/A03_2021-Injection/"],
        ),
        raw_risk_score=10.0,
        is_advisory_only=True,
    )
    return ModeratedFinding(
        finding=f,
        risk_score=10.0,
        priority_rank=1,
        is_deduplicated=False,
        sources=[AgentRoleEnum.SECURITY_AUDITOR],
        arbitration_notes="Verified security vulnerability with clear code evidence.",
    )


@pytest.fixture
def sample_medium_finding() -> ModeratedFinding:
    f = Finding(
        id="ARCH-002",
        agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
        category="Maintainability",
        cwe_id=None,
        owasp_category=None,
        title="High Cyclomatic Complexity",
        description="Function contains excessive branching nesting exceeding thresholds.",
        severity=SeverityEnum.MEDIUM,
        confidence=ConfidenceEnum.MEDIUM,
        evidence=CodeEvidence(
            file_path="src/services/billing.py",
            start_line=45,
            end_line=50,
            code_snippet="if a:\n    if b:\n        return c",
        ),
        remediation=RemediationAdvice(
            explanation="Decompose nested branches into guard clauses.",
            recommended_fix="if not a or not b:\n    return None\nreturn c",
            references=[],
        ),
        raw_risk_score=5.0,
        is_advisory_only=True,
    )
    return ModeratedFinding(
        finding=f,
        risk_score=5.0,
        priority_rank=2,
        is_deduplicated=False,
        sources=[AgentRoleEnum.SOFTWARE_ARCHITECT],
    )


@pytest.fixture
def sample_review(sample_finding, sample_medium_finding) -> ConsolidatedReview:
    return ConsolidatedReview(
        review_id="rev-cli-test-1",
        repo_id="repo-cli-123",
        created_at="2026-11-06T12:00:00Z",
        status="completed",
        total_files_reviewed=2,
        total_chunks_reviewed=5,
        findings=[sample_finding, sample_medium_finding],
        severity_distribution={
            "CRITICAL": 1,
            "HIGH": 0,
            "MEDIUM": 1,
            "LOW": 0,
            "INFO": 0,
        },
        risk_summary={
            "total_findings": 2,
            "average_risk_score": 7.5,
            "max_risk_score": 10.0,
            "critical_count": 1,
            "high_count": 0,
            "deduplicated_count": 0,
        },
        agent_metrics={
            "total_agent_calls": 10,
            "successful_agent_calls": 10,
            "failed_agent_calls": 0,
            "total_execution_time_ms": 1200.0,
            "total_tokens_used": 1500,
        },
    )


# ---------------------------------------------------------------------------
# 1. Argument Parser Tests
# ---------------------------------------------------------------------------

def test_argument_parser_local_scan():
    parser = build_parser()
    args = parser.parse_args(["scan", "/path/to/project"])
    assert args.command == "scan"
    assert args.path == "/path/to/project"
    assert args.github is None
    assert args.json is False
    assert args.detailed is False


def test_argument_parser_github_flags():
    parser = build_parser()
    args = parser.parse_args([
        "scan",
        "--github", "https://github.com/owner/repo",
        "--ref", "feature-branch",
        "--pr", "42",
        "--token", "ghp_secrettoken123",
    ])
    assert args.github == "https://github.com/owner/repo"
    assert args.ref == "feature-branch"
    assert args.pr == 42
    assert args.token == "ghp_secrettoken123"


def test_argument_parser_filter_and_output_flags():
    parser = build_parser()
    args = parser.parse_args([
        "scan",
        ".",
        "--json",
        "--output", "report.json",
        "--min-severity", "HIGH",
        "--detailed",
    ])
    assert args.json is True
    assert args.output == "report.json"
    assert args.min_severity == "HIGH"
    assert args.detailed is True


def test_argument_parser_default_fallbacks():
    normalized = normalize_cli_args([])
    assert normalized == ["scan", "."]

    parser = build_parser()
    args = parser.parse_args(normalized)
    assert args.path == "."
    assert args.command == "scan"


def test_argument_parser_direct_path_without_scan_keyword():
    normalized = normalize_cli_args(["/my/custom/path", "--json"])
    assert normalized[0] == "scan"
    parser = build_parser()
    args = parser.parse_args(normalized)
    assert args.path == "/my/custom/path"
    assert args.json is True


# ---------------------------------------------------------------------------
# 2. CLIFormatter Tests
# ---------------------------------------------------------------------------

def test_formatter_severity_badges():
    formatter = CLIFormatter()
    for sev in SeverityEnum:
        badge = formatter.format_severity_badge(sev)
        assert isinstance(badge, Text)
        assert sev.value in badge.plain


def test_formatter_findings_table(sample_finding, sample_medium_finding):
    formatter = CLIFormatter()
    table = formatter.format_findings_table([sample_finding, sample_medium_finding])
    assert isinstance(table, Table)
    assert table.title == "Automated Vulnerability & Architecture Findings"
    assert len(table.rows) == 2


def test_formatter_findings_table_min_severity_filter(sample_finding, sample_medium_finding):
    formatter = CLIFormatter()
    # Filter with min_severity=HIGH: CRITICAL should remain, MEDIUM should be excluded
    table = formatter.format_findings_table(
        [sample_finding, sample_medium_finding],
        min_severity=SeverityEnum.HIGH,
    )
    assert len(table.rows) == 1


def test_formatter_finding_card(sample_finding):
    formatter = CLIFormatter()
    card = formatter.format_finding_card(sample_finding)
    assert isinstance(card, Panel)


def test_formatter_summary_panel(sample_review):
    formatter = CLIFormatter()
    summary = formatter.format_summary_panel(sample_review)
    assert isinstance(summary, Panel)


def test_formatter_json_output(sample_review):
    formatter = CLIFormatter()
    json_str = formatter.format_json_output(sample_review)
    data = json.loads(json_str)
    assert data["review_id"] == "rev-cli-test-1"
    assert len(data["findings"]) == 2
    assert "advisory_disclaimer" in data


# ---------------------------------------------------------------------------
# 3. CLIScanRunner Tests
# ---------------------------------------------------------------------------

def test_runner_local_scan(tmp_path):
    sample_file = tmp_path / "hello.py"
    sample_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    runner = CLIScanRunner()

    mock_result = AgentResult(
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        chunk_id="chunk-1",
        file_path=str(sample_file),
        execution_time_ms=10.0,
        success=True,
        findings=[],
    )

    async def mock_run_review(*args, **kwargs):
        return [mock_result]

    runner.orchestrator.run_review = mock_run_review

    stage_log = []
    def track_stage(stage, msg):
        stage_log.append(stage)

    review = execute_coroutine_sync(runner.run_scan(str(tmp_path), on_stage=track_stage))

    assert isinstance(review, ConsolidatedReview)
    assert review.status == "completed"
    assert review.total_files_reviewed >= 1
    assert "ingestion" in stage_log
    assert "context" in stage_log
    assert "analysis" in stage_log
    assert "moderation" in stage_log


def test_runner_github_scan(tmp_path):
    runner = CLIScanRunner()

    mock_file = IngestedFile(
        file_path=str(tmp_path / "app.py"),
        relative_path="app.py",
        language=LanguageEnum.python,
        content="x = 1\n",
        line_count=1,
        size_bytes=6,
    )

    async def mock_ingest(*args, **kwargs):
        return str(tmp_path), [mock_file]

    async def mock_run_review(*args, **kwargs):
        return []

    runner.orchestrator.run_review = mock_run_review

    with patch("src.cli.runner.ingest_github_repo", side_effect=mock_ingest):
        review = execute_coroutine_sync(
            runner.run_scan("https://github.com/test-org/test-repo", is_github=True)
        )

        assert isinstance(review, ConsolidatedReview)
        assert review.status == "completed"


def test_runner_invalid_local_path():
    runner = CLIScanRunner()
    with pytest.raises(FileNotFoundError):
        execute_coroutine_sync(runner.run_scan("/non/existent/path/for/sure/12345"))


# ---------------------------------------------------------------------------
# 4. main() Entrypoint Tests
# ---------------------------------------------------------------------------

def test_main_json_output(tmp_path, sample_review, capsys):
    async def mock_run(*args, **kwargs):
        return sample_review

    with patch.object(CLIScanRunner, "run_scan", side_effect=mock_run):
        exit_code = main(["scan", str(tmp_path), "--json"])

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["review_id"] == "rev-cli-test-1"
        # sample_review contains CRITICAL finding, so exit code should be 2
        assert exit_code == 2


def test_main_output_to_file(tmp_path, sample_medium_finding):
    clean_review = ConsolidatedReview(
        review_id="rev-clean-1",
        repo_id="repo-clean",
        created_at="2026-11-06T12:00:00Z",
        status="completed",
        total_files_reviewed=1,
        total_chunks_reviewed=1,
        findings=[sample_medium_finding],
        severity_distribution={"MEDIUM": 1},
        risk_summary={"critical_count": 0},
    )

    out_file = tmp_path / "output_report.json"

    async def mock_run(*args, **kwargs):
        return clean_review

    with patch.object(CLIScanRunner, "run_scan", side_effect=mock_run):
        exit_code = main(["scan", str(tmp_path), "--output", str(out_file)])

        assert exit_code == 0
        assert out_file.exists()
        saved_data = json.loads(out_file.read_text(encoding="utf-8"))
        assert saved_data["review_id"] == "rev-clean-1"


def test_main_validation_error_exit_code():
    exit_code = main(["scan", "/path/that/definitely/does/not/exist/9999"])
    assert exit_code == 1
