"""Comprehensive test suite for review history persistence, scan comparison engine, and API routes."""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from fastapi.testclient import TestClient
from rich.console import Console

from src.api.routes.history import get_history_storage
from src.cli.main import main, run_cli_history
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
from src.storage.history import ReviewHistoryStorage


def make_finding(
    id: str,
    title: str,
    file_path: str,
    start_line: int,
    end_line: int,
    cwe_id: str = None,
    severity: SeverityEnum = SeverityEnum.HIGH,
    risk_score: float = 7.5,
) -> ModeratedFinding:
    """Helper to construct a valid ModeratedFinding for tests."""
    f = Finding(
        id=id,
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        category="Security Vulnerability",
        cwe_id=cwe_id,
        owasp_category="A03:2021-Injection",
        title=title,
        description=f"Vulnerability report for {title}",
        severity=severity,
        confidence=ConfidenceEnum.HIGH,
        evidence=CodeEvidence(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            code_snippet="vulnerable_statement()",
        ),
        remediation=RemediationAdvice(
            explanation="Ensure user input is sanitized.",
            recommended_fix="safe_statement()",
            references=[],
        ),
        raw_risk_score=risk_score,
        is_advisory_only=True,
    )
    return ModeratedFinding(
        finding=f,
        risk_score=risk_score,
        priority_rank=1,
        is_deduplicated=False,
        sources=[AgentRoleEnum.SECURITY_AUDITOR],
    )


def make_review(
    review_id: str,
    repo_id: str = "test-repo",
    created_at: str = "2026-11-06T12:00:00",
    findings: list = None,
) -> ConsolidatedReview:
    """Helper to construct a valid ConsolidatedReview for tests."""
    findings = findings or []
    sev_counts = {}
    for f in findings:
        sev = f.finding.severity.value
        sev_counts[sev] = sev_counts.get(sev, 0) + 1
    max_risk = max((f.risk_score for f in findings), default=0.0)
    return ConsolidatedReview(
        review_id=review_id,
        repo_id=repo_id,
        created_at=created_at,
        status="completed",
        total_files_reviewed=5,
        total_chunks_reviewed=10,
        findings=findings,
        severity_distribution=sev_counts,
        risk_summary={"max_risk_score": max_risk, "total_findings": len(findings)},
        agent_metrics={"total_agents": 2},
    )


# ---------------------------------------------------------------------------
# 1. Storage Unit Tests
# ---------------------------------------------------------------------------

def test_storage_save_and_get_review(tmp_path: Path):
    """Test saving a review persists JSON file and updates index metadata."""
    storage = ReviewHistoryStorage(storage_dir=tmp_path / "reviews")
    review = make_review(
        review_id="rev-001",
        repo_id="backend-api",
        findings=[make_finding("F1", "SQL Injection", "db.py", 10, 15, cwe_id="CWE-89")],
    )

    saved_path = storage.save_review(review)
    assert saved_path.exists()
    assert saved_path.name == "rev-001.json"

    # Verify retrieval
    loaded = storage.get_review("rev-001")
    assert loaded is not None
    assert loaded.review_id == "rev-001"
    assert loaded.repo_id == "backend-api"
    assert len(loaded.findings) == 1
    assert loaded.findings[0].finding.title == "SQL Injection"


def test_storage_get_nonexistent_returns_none(tmp_path: Path):
    """Test get_review returns None when ID does not exist."""
    storage = ReviewHistoryStorage(storage_dir=tmp_path / "reviews")
    assert storage.get_review("non-existent-id") is None


def test_storage_list_reviews_and_filtering(tmp_path: Path):
    """Test list_reviews returns entries sorted newest first and filters by repo_id."""
    storage = ReviewHistoryStorage(storage_dir=tmp_path / "reviews")
    rev1 = make_review("rev-001", repo_id="repo-a", created_at="2026-11-01T10:00:00")
    rev2 = make_review("rev-002", repo_id="repo-b", created_at="2026-11-02T10:00:00")
    rev3 = make_review("rev-003", repo_id="repo-a", created_at="2026-11-03T10:00:00")

    storage.save_review(rev1)
    storage.save_review(rev2)
    storage.save_review(rev3)

    all_reviews = storage.list_reviews()
    assert len(all_reviews) == 3
    # Check descending sort (newest first: rev3, rev2, rev1)
    assert [r["review_id"] for r in all_reviews] == ["rev-003", "rev-002", "rev-001"]

    # Filter by repo
    repo_a_reviews = storage.list_reviews(repo_id="repo-a")
    assert len(repo_a_reviews) == 2
    assert [r["review_id"] for r in repo_a_reviews] == ["rev-003", "rev-001"]

    # Limit check
    limited = storage.list_reviews(limit=2)
    assert len(limited) == 2


def test_storage_delete_review(tmp_path: Path):
    """Test deleting a review removes file and updates metadata index."""
    storage = ReviewHistoryStorage(storage_dir=tmp_path / "reviews")
    review = make_review("rev-delete-me")
    storage.save_review(review)
    assert storage.get_review("rev-delete-me") is not None
    assert len(storage.list_reviews()) == 1

    deleted = storage.delete_review("rev-delete-me")
    assert deleted is True
    assert storage.get_review("rev-delete-me") is None
    assert len(storage.list_reviews()) == 0


# ---------------------------------------------------------------------------
# 2. Comparison Engine Tests
# ---------------------------------------------------------------------------

def test_compare_reviews_diff(tmp_path: Path):
    """Test scan comparison diff correctly classifies new, resolved, and persistent findings."""
    storage = ReviewHistoryStorage(storage_dir=tmp_path / "reviews")

    # Review A:
    # Finding 1: SQLi at line 10
    # Finding 2: Hardcoded key at line 50
    f1_a = make_finding("F1-A", "SQL Injection Vulnerability", "db/queries.py", 10, 15, cwe_id="CWE-89", severity=SeverityEnum.CRITICAL, risk_score=9.5)
    f2_a = make_finding("F2-A", "Hardcoded Secret Key", "config/settings.py", 50, 52, cwe_id="CWE-798", severity=SeverityEnum.HIGH, risk_score=7.0)
    rev_a = make_review("rev-a", repo_id="my-app", created_at="2026-11-01T00:00:00", findings=[f1_a, f2_a])

    # Review B:
    # Finding 1: SQLi still at line 12 (within 5 lines -> persistent)
    # Finding 3: Command injection at line 80 (new)
    # Finding 2 is gone (resolved)
    f1_b = make_finding("F1-B", "SQL Injection Vulnerability", "db/queries.py", 12, 17, cwe_id="CWE-89", severity=SeverityEnum.CRITICAL, risk_score=9.5)
    f3_b = make_finding("F3-B", "OS Command Injection", "utils/runner.py", 80, 85, cwe_id="CWE-78", severity=SeverityEnum.CRITICAL, risk_score=9.8)
    rev_b = make_review("rev-b", repo_id="my-app", created_at="2026-11-02T00:00:00", findings=[f1_b, f3_b])

    storage.save_review(rev_a)
    storage.save_review(rev_b)

    result = storage.compare_reviews("rev-a", "rev-b")

    # Assert new findings (Finding 3)
    assert len(result["new_findings"]) == 1
    assert result["new_findings"][0].finding.id == "F3-B"

    # Assert resolved findings (Finding 2)
    assert len(result["resolved_findings"]) == 1
    assert result["resolved_findings"][0].finding.id == "F2-A"

    # Assert persistent findings (Finding 1)
    assert len(result["persistent_findings"]) == 1
    assert result["persistent_findings"][0].finding.title == "SQL Injection Vulnerability"

    # Assert summary metrics
    summary = result["summary"]
    assert summary["new_count"] == 1
    assert summary["resolved_count"] == 1
    assert summary["persistent_count"] == 1
    assert summary["base_total"] == 2
    assert summary["target_total"] == 2
    assert "risk_score_delta" in summary
    assert "critical_delta" in summary


def test_compare_reviews_invalid_ids_raise_value_error(tmp_path: Path):
    """Test comparing non-existent review IDs raises ValueError."""
    storage = ReviewHistoryStorage(storage_dir=tmp_path / "reviews")
    storage.save_review(make_review("valid-id"))

    with pytest.raises(ValueError, match="Base review 'missing-base' not found"):
        storage.compare_reviews("missing-base", "valid-id")

    with pytest.raises(ValueError, match="Target review 'missing-target' not found"):
        storage.compare_reviews("valid-id", "missing-target")


# ---------------------------------------------------------------------------
# 3. API Integration Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client(tmp_path: Path):
    """FastAPI TestClient fixture with isolated review storage."""
    storage = ReviewHistoryStorage(storage_dir=tmp_path / "api_reviews")
    app.dependency_overrides[get_history_storage] = lambda: storage
    client = TestClient(app)
    yield client, storage
    app.dependency_overrides.clear()


def test_api_list_history(api_client):
    """Verify GET /api/v1/history returns 200 and list of review summaries."""
    client, storage = api_client
    rev1 = make_review("rev-api-1", repo_id="service-a")
    rev2 = make_review("rev-api-2", repo_id="service-b")
    storage.save_review(rev1)
    storage.save_review(rev2)

    res = client.get("/api/v1/history")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 2

    # Query with repo filter
    res_filtered = client.get("/api/v1/history?repo_id=service-a")
    assert res_filtered.status_code == 200
    filtered_data = res_filtered.json()
    assert len(filtered_data) == 1
    assert filtered_data[0]["repo_id"] == "service-a"


def test_api_get_review_by_id(api_client):
    """Verify GET /api/v1/history/{review_id} returns 200 with review data."""
    client, storage = api_client
    rev = make_review("rev-api-100", repo_id="service-x")
    storage.save_review(rev)

    res = client.get("/api/v1/history/rev-api-100")
    assert res.status_code == 200
    data = res.json()
    assert data["review_id"] == "rev-api-100"
    assert data["repo_id"] == "service-x"


def test_api_get_nonexistent_review_returns_404(api_client):
    """Verify GET /api/v1/history/non-existent returns 404."""
    client, _ = api_client
    res = client.get("/api/v1/history/non-existent-review-id")
    assert res.status_code == 404


def test_api_compare_reviews(api_client):
    """Verify POST /api/v1/history/compare returns 200 and diff structure."""
    client, storage = api_client
    f1 = make_finding("F1", "Issue 1", "test.py", 10, 15)
    f2 = make_finding("F2", "Issue 2", "other.py", 20, 25)
    rev_a = make_review("rev-base", findings=[f1])
    rev_b = make_review("rev-target", findings=[f1, f2])
    storage.save_review(rev_a)
    storage.save_review(rev_b)

    payload = {"base_review_id": "rev-base", "target_review_id": "rev-target"}
    res = client.post("/api/v1/history/compare", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["base_review_id"] == "rev-base"
    assert data["target_review_id"] == "rev-target"
    assert len(data["new_findings"]) == 1
    assert len(data["persistent_findings"]) == 1
    assert len(data["resolved_findings"]) == 0
    assert data["summary"]["new_count"] == 1


def test_api_delete_review(api_client):
    """Verify DELETE /api/v1/history/{review_id} returns 200."""
    client, storage = api_client
    rev = make_review("rev-to-delete")
    storage.save_review(rev)

    res = client.delete("/api/v1/history/rev-to-delete")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "deleted"
    assert data["review_id"] == "rev-to-delete"

    # Confirm it's gone
    assert storage.get_review("rev-to-delete") is None


# ---------------------------------------------------------------------------
# 4. CLI History Integration Tests
# ---------------------------------------------------------------------------

def test_cli_history_table_output(tmp_path: Path):
    """Test reviewer history renders Rich table without exceptions."""
    storage = ReviewHistoryStorage(storage_dir=tmp_path / "cli_reviews")
    rev = make_review(
        "cli-rev-12345678",
        repo_id="cli-target",
        findings=[make_finding("F1", "XSS Defect", "web.js", 5, 8, severity=SeverityEnum.CRITICAL, risk_score=9.0)],
    )
    storage.save_review(rev)

    console = Console(file=io.StringIO(), force_terminal=True, width=120)
    with patch("src.cli.main.ReviewHistoryStorage", return_value=storage):
        exit_code = main(["history"])
        assert exit_code == 0

        # Also test with repo filter
        exit_code_filtered = main(["history", "--repo", "cli-target"])
        assert exit_code_filtered == 0

        # Also test json output
        exit_code_json = main(["history", "--json"])
        assert exit_code_json == 0

