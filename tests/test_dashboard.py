"""Integration tests for Local Web Dashboard router, static files, and scan runner."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
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
from src.dashboard.router import get_history_storage, get_scan_runner
from src.main import app
from src.storage.history import ReviewHistoryStorage


@pytest.fixture
def client(tmp_path: Path):
    """TestClient fixture with isolated storage directory."""
    storage = ReviewHistoryStorage(storage_dir=tmp_path / "reviews")
    app.dependency_overrides[get_history_storage] = lambda: storage
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def make_dummy_review(repo_id: str = "test-repo") -> ConsolidatedReview:
    """Helper to create a dummy ConsolidatedReview."""
    finding = Finding(
        id="FIND-01",
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        category="Injection",
        cwe_id="CWE-89",
        owasp_category="A03:2021-Injection",
        title="SQL Injection Vulnerability",
        description="Unsanitized user input in query.",
        severity=SeverityEnum.HIGH,
        confidence=ConfidenceEnum.HIGH,
        evidence=CodeEvidence(
            file_path="src/db.py",
            start_line=10,
            end_line=12,
            code_snippet="db.execute(f'SELECT * FROM users WHERE id={user_id}')",
        ),
        remediation=RemediationAdvice(
            explanation="Dynamic string interpolation into SQL queries creates injection vulnerabilities.",
            recommended_fix="Use parameterized queries with prepared statements.",
            references=["https://cwe.mitre.org/data/definitions/89.html"],
        ),
    )
    mod_finding = ModeratedFinding(
        finding=finding,
        risk_score=7.8,
        priority_rank=1,
        is_deduplicated=False,
        sources=[AgentRoleEnum.SECURITY_AUDITOR],
    )
    return ConsolidatedReview(
        review_id="rev-test-1234",
        repo_id=repo_id,
        created_at="2026-11-06T20:00:00Z",
        status="completed",
        total_files_reviewed=5,
        total_chunks_reviewed=8,
        findings=[mod_finding],
    )


def test_dashboard_page_serves_html(client: TestClient):
    """GET /dashboard should return 200 OK with HTML content."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Automated Code Vulnerability Reviewer" in response.text
    assert "New Review" in response.text
    assert "Findings Explorer" in response.text
    assert "Review History &amp; Comparison" in response.text or "Review History & Comparison" in response.text


def test_root_redirects_to_dashboard(client: TestClient):
    """GET / should redirect to /dashboard."""
    # Without following redirect
    response_no_follow = client.get("/", follow_redirects=False)
    assert response_no_follow.status_code in (302, 307)
    assert response_no_follow.headers.get("location").endswith("/dashboard")

    # With following redirect
    response_follow = client.get("/", follow_redirects=True)
    assert response_follow.status_code == 200
    assert "Automated Code Vulnerability Reviewer" in response_follow.text


def test_static_css_and_js_served(client: TestClient):
    """GET /static/style.css and /static/app.js should return 200 with appropriate mime types."""
    css_res = client.get("/static/style.css")
    assert css_res.status_code == 200
    assert "text/css" in css_res.headers.get("content-type", "")
    assert "--bg: #0f172a" in css_res.text

    js_res = client.get("/static/app.js")
    assert js_res.status_code == 200
    assert "javascript" in js_res.headers.get("content-type", "").lower()
    assert "startReview" in js_res.text


def test_loki_opener_static_assets_served(client: TestClient):
    """GET /static/opener.js and logo assets should return 200 OK."""
    opener_res = client.get("/static/opener.js")
    assert opener_res.status_code == 200
    assert "LokiOpener" in opener_res.text

    logo_res = client.get("/static/assets/loki-logo.png")
    assert logo_res.status_code == 200
    assert "image/png" in logo_res.headers.get("content-type", "")

    logo_cropped_res = client.get("/static/assets/loki-logo-cropped.png")
    assert logo_cropped_res.status_code == 200
    assert "image/png" in logo_cropped_res.headers.get("content-type", "")

    aistudio_res = client.get("/assets/aistudio/IMG_20261107_230930_1a6db8c8.png")
    assert aistudio_res.status_code == 200
    assert "image/png" in aistudio_res.headers.get("content-type", "")


def test_dashboard_scan_local_success(client: TestClient, tmp_path: Path):
    """POST /api/v1/dashboard/scan with valid local directory returns 200 and saves review."""
    sample_dir = tmp_path / "sample_code"
    sample_dir.mkdir()
    (sample_dir / "app.py").write_text("print('hello')", encoding="utf-8")

    mock_runner = MagicMock()
    mock_runner.run_scan = AsyncMock(return_value=make_dummy_review(repo_id="sample_code"))

    app.dependency_overrides[get_scan_runner] = lambda: mock_runner

    payload = {
        "source_type": "local",
        "path_or_url": str(sample_dir),
    }

    response = client.post("/api/v1/dashboard/scan", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["review_id"] == "rev-test-1234"
    assert data["repo_id"] == "sample_code"
    assert len(data["findings"]) == 1
    assert data["findings"][0]["finding"]["cwe_id"] == "CWE-89"

    mock_runner.run_scan.assert_awaited_once()


def test_dashboard_scan_github_success(client: TestClient):
    """POST /api/v1/dashboard/scan with GitHub source triggers runner with remote flags."""
    mock_runner = MagicMock()
    mock_runner.run_scan = AsyncMock(return_value=make_dummy_review(repo_id="github-repo"))

    app.dependency_overrides[get_scan_runner] = lambda: mock_runner

    payload = {
        "source_type": "github",
        "path_or_url": "https://github.com/example/vulnerable-app",
        "ref": "main",
        "token": "ghp_secret123",
    }

    response = client.post("/api/v1/dashboard/scan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["review_id"] == "rev-test-1234"

    mock_runner.run_scan.assert_awaited_once_with(
        target="https://github.com/example/vulnerable-app",
        is_github=True,
        ref="main",
        token="ghp_secret123",
        pr_number=None,
    )


def test_dashboard_scan_empty_target_returns_400(client: TestClient):
    """POST /api/v1/dashboard/scan with blank target returns 400 Bad Request."""
    payload = {
        "source_type": "local",
        "path_or_url": "   ",
    }
    response = client.post("/api/v1/dashboard/scan", json=payload)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_dashboard_scan_nonexistent_local_dir_returns_400(client: TestClient):
    """POST /api/v1/dashboard/scan with missing folder returns 400 Bad Request."""
    payload = {
        "source_type": "local",
        "path_or_url": "path/does/not/exist/at/all",
    }
    response = client.post("/api/v1/dashboard/scan", json=payload)
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_dashboard_scan_runner_failure_returns_500(client: TestClient, tmp_path: Path):
    """POST /api/v1/dashboard/scan returns 500 when scan runner raises an unexpected exception."""
    sample_dir = tmp_path / "test_error"
    sample_dir.mkdir()

    mock_runner = MagicMock()
    mock_runner.run_scan = AsyncMock(side_effect=RuntimeError("LLM API quota exceeded"))

    app.dependency_overrides[get_scan_runner] = lambda: mock_runner

    payload = {
        "source_type": "local",
        "path_or_url": str(sample_dir),
    }
    response = client.post("/api/v1/dashboard/scan", json=payload)
    assert response.status_code == 500
    assert "LLM API quota exceeded" in response.json()["detail"]


def test_all_routes_coexist_without_collision(client: TestClient):
    """Verify health, api endpoints, dashboard, and static coexist smoothly."""
    # Health route
    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "ok"

    # API Health route
    api_health_res = client.get("/api/v1/health")
    assert api_health_res.status_code == 200

    # History list route
    history_res = client.get("/api/v1/history")
    assert history_res.status_code == 200

    # Dashboard root route
    dash_res = client.get("/dashboard")
    assert dash_res.status_code == 200


def test_dashboard_cancel_scan_endpoint(client: TestClient):
    """POST /api/v1/dashboard/cancel cancels active scans and returns status 200."""
    # Test cancelling without active scan ID
    res = client.post("/api/v1/dashboard/cancel", json={})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "cancelled"

    # Test cancelling with specific scan ID
    res_id = client.post("/api/v1/dashboard/cancel", json={"scan_id": "nonexistent-scan"})
    assert res_id.status_code == 200
    assert res_id.json()["status"] == "cancelled"


def test_dashboard_scan_cancellation_handling(client: TestClient, tmp_path: Path):
    """POST /api/v1/dashboard/scan handles asyncio.CancelledError gracefully returning 400."""
    sample_dir = tmp_path / "test_cancel"
    sample_dir.mkdir()

    import asyncio
    mock_runner = MagicMock()
    mock_runner.run_scan = AsyncMock(side_effect=asyncio.CancelledError())

    app.dependency_overrides[get_scan_runner] = lambda: mock_runner

    payload = {
        "source_type": "local",
        "path_or_url": str(sample_dir),
    }
    response = client.post("/api/v1/dashboard/scan", json=payload)
    assert response.status_code == 400
    assert "cancelled by user" in response.json()["detail"].lower()

