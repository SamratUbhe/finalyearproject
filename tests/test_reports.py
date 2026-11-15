"""Unit and integration tests for HTML and PDF Report Generation engines and endpoints."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from src.core.models import (
    AgentRoleEnum,
    CodeEvidence,
    ConfidenceEnum,
    ConsolidatedReview,
    Finding,
    ModeratedFinding,
    RemediationAdvice,
    SeverityEnum,
)
from src.main import app
from src.reports.html_generator import HTMLReportGenerator
from src.reports.pdf_generator import PDFReportGenerator
from src.storage.history import ReviewHistoryStorage
from src.cli.main import run_cli_export


def create_dummy_review(
    review_id: str = "rev-test-report",
    num_findings: int = 2,
) -> ConsolidatedReview:
    """Helper to construct dummy ConsolidatedReview models."""
    findings = []
    if num_findings > 0:
        findings.append(
            ModeratedFinding(
                finding=Finding(
                    id="FIND-01",
                    agent_role=AgentRoleEnum.SECURITY_AUDITOR,
                    category="Injection",
                    cwe_id="CWE-89",
                    owasp_category="A03:2021-Injection",
                    title="SQL Injection in auth handler",
                    description="User input is concatenated into raw query string.",
                    severity=SeverityEnum.CRITICAL,
                    confidence=ConfidenceEnum.HIGH,
                    evidence=CodeEvidence(
                        file_path="src/auth.py",
                        start_line=25,
                        end_line=27,
                        code_snippet="cursor.execute('SELECT * FROM users WHERE name = ' + user_input)",
                    ),
                    remediation=RemediationAdvice(
                        recommended_fix="Use parameterized queries with parameterized placeholders.",
                        explanation="Prevents SQL injection vulnerabilities.",
                    ),
                    raw_risk_score=9.5,
                ),
                priority_rank=1,
                sources=[AgentRoleEnum.SECURITY_AUDITOR],
                risk_score=10.0,
            )
        )
    if num_findings > 1:
        findings.append(
            ModeratedFinding(
                finding=Finding(
                    id="FIND-02",
                    agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
                    category="Resource Management",
                    cwe_id="CWE-404",
                    owasp_category="Architecture",
                    title="Unclosed Database Connection Leak",
                    description="Connection is opened without context manager or close call.",
                    severity=SeverityEnum.MEDIUM,
                    confidence=ConfidenceEnum.MEDIUM,
                    evidence=CodeEvidence(
                        file_path="src/db_pool.py",
                        start_line=50,
                        end_line=55,
                        code_snippet="conn = pool.get_connection()\n# missing conn.close()",
                    ),
                    remediation=RemediationAdvice(
                        recommended_fix="Use contextlib context manager to release connection.",
                        explanation="Prevents connection pool exhaustion.",
                    ),
                    raw_risk_score=6.0,
                ),
                priority_rank=2,
                sources=[AgentRoleEnum.SOFTWARE_ARCHITECT],
                risk_score=6.5,
            )
        )

    return ConsolidatedReview(
        review_id=review_id,
        repo_id="test-org/dummy-repo",
        created_at="2026-11-07T14:00:00Z",
        status="completed",
        total_files_reviewed=5,
        total_chunks_reviewed=12,
        findings=findings,
        severity_distribution={"CRITICAL": 1 if num_findings > 0 else 0, "MEDIUM": 1 if num_findings > 1 else 0},
        risk_summary={"max_risk_score": 10.0 if num_findings > 0 else 0.0, "average_risk_score": 8.25, "deduplicated_count": 1},
        agent_metrics={"security_auditor_findings": 1, "software_architect_findings": 1},
    )


# -------------------------------------------------------------
# HTML Generator Tests
# -------------------------------------------------------------

def test_html_generator_renders_review(tmp_path: Path):
    """Test HTMLReportGenerator builds valid HTML document with metadata and finding cards."""
    review = create_dummy_review("rev-html-01", num_findings=2)
    generator = HTMLReportGenerator()

    html = generator.generate(review)
    assert "<!DOCTYPE html>" in html
    assert "rev-html-01" in html
    assert "test-org/dummy-repo" in html
    assert "SQL Injection in auth handler" in html
    assert "CWE-89" in html
    assert "@media print" in html
    assert "ADVISORY" in html or "Advisory" in html

    # Test file saving
    save_path = tmp_path / "report.html"
    res_path = generator.save_to_file(review, save_path)
    assert res_path.exists()
    assert res_path.read_text(encoding="utf-8") == html


def test_html_generator_empty_review():
    """Test HTMLReportGenerator handles review with zero findings without errors."""
    review = create_dummy_review("rev-html-empty", num_findings=0)
    generator = HTMLReportGenerator()

    html = generator.generate(review)
    assert "rev-html-empty" in html
    assert "No security or architectural defects were detected" in html or "0" in html


def test_html_generator_escapes_special_chars():
    """Test HTMLReportGenerator escapes XML/HTML tags in code evidence and descriptions."""
    review = create_dummy_review("rev-html-escape", num_findings=1)
    review.findings[0].finding.evidence.code_snippet = "<script>alert('xss')</script>"
    generator = HTMLReportGenerator()

    html = generator.generate(review)
    assert "<script>alert('xss')</script>" not in html
    assert "&lt;script&gt;alert('xss')&lt;/script&gt;" in html or "&lt;script&gt;" in html


# -------------------------------------------------------------
# PDF Generator Tests
# -------------------------------------------------------------

def test_pdf_generator_renders_pdf(tmp_path: Path):
    """Test PDFReportGenerator builds valid binary PDF document with %PDF- header."""
    review = create_dummy_review("rev-pdf-01", num_findings=2)
    generator = PDFReportGenerator()

    pdf_bytes = generator.generate(review)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")

    # Test file saving
    save_path = tmp_path / "report.pdf"
    generator.generate(review, output_path=save_path)
    assert save_path.exists()
    assert save_path.stat().st_size == len(pdf_bytes)


def test_pdf_generator_empty_findings():
    """Test PDFReportGenerator compiles cleanly for zero findings."""
    review = create_dummy_review("rev-pdf-empty", num_findings=0)
    generator = PDFReportGenerator()

    pdf_bytes = generator.generate(review)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")


# -------------------------------------------------------------
# REST API Endpoints Tests
# -------------------------------------------------------------

def test_reports_api_endpoints(tmp_path: Path):
    """Test GET /api/v1/reports/html/{id} and /pdf/{id} return expected responses and headers."""
    storage = ReviewHistoryStorage(storage_dir=tmp_path / "reviews")
    review = create_dummy_review("rev-api-test", num_findings=1)
    storage.save_review(review)

    from src.api.routes.reports import get_history_storage
    app.dependency_overrides[get_history_storage] = lambda: storage
    client = TestClient(app)

    try:
        # 1. HTML Endpoint
        res_html = client.get("/api/v1/reports/html/rev-api-test")
        assert res_html.status_code == 200
        assert "text/html" in res_html.headers.get("content-type", "")
        assert "inline" in res_html.headers.get("content-disposition", "")
        assert "rev-api-test" in res_html.text

        # 1b. HTML Endpoint with download=true
        res_html_dl = client.get("/api/v1/reports/html/rev-api-test?download=true")
        assert res_html_dl.status_code == 200
        assert "attachment" in res_html_dl.headers.get("content-disposition", "")

        # 2. PDF Endpoint
        res_pdf = client.get("/api/v1/reports/pdf/rev-api-test")
        assert res_pdf.status_code == 200
        assert res_pdf.headers.get("content-type") == "application/pdf"
        assert res_pdf.content.startswith(b"%PDF-")

        # 3. 404 for unknown review ID
        res_404_html = client.get("/api/v1/reports/html/rev-does-not-exist")
        assert res_404_html.status_code == 404

        res_404_pdf = client.get("/api/v1/reports/pdf/rev-does-not-exist")
        assert res_404_pdf.status_code == 404

    finally:
        app.dependency_overrides.clear()


# -------------------------------------------------------------
# CLI Export Command Tests
# -------------------------------------------------------------

def test_cli_export_command(tmp_path: Path):
    """Test CLI run_cli_export handles historical scans and outputs files."""
    storage = ReviewHistoryStorage(storage_dir=tmp_path / "reviews")
    review = create_dummy_review("rev-cli-exp", num_findings=1)
    storage.save_review(review)

    from unittest.mock import patch
    html_out = tmp_path / "cli_report.html"
    pdf_out = tmp_path / "cli_report.pdf"

    mock_args = MagicMock()
    mock_args.review_id = "rev-cli-exp"
    mock_args.html = str(html_out)
    mock_args.pdf = str(pdf_out)

    with patch("src.cli.main.ReviewHistoryStorage", return_value=storage):
        exit_code = run_cli_export(mock_args)
        assert exit_code == 0
        assert html_out.exists()
        assert pdf_out.exists()
        assert pdf_out.read_bytes().startswith(b"%PDF-")

    # Test unknown review ID
    mock_args.review_id = "rev-nonexistent"
    with patch("src.cli.main.ReviewHistoryStorage", return_value=storage):
        exit_code_err = run_cli_export(mock_args)
        assert exit_code_err == 1

