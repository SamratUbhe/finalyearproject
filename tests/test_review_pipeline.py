"""Integration tests for the multi-agent review and moderation API pipeline."""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from src.core.models import (
    AgentResult,
    AgentRoleEnum,
    ChunkType,
    CodeChunk,
    CodeEvidence,
    ConfidenceEnum,
    ConsolidatedReview,
    Finding,
    IngestedFile,
    IngestionSourceType,
    LanguageEnum,
    RemediationAdvice,
    RepositorySummary,
    ReviewContext,
    SeverityEnum,
)
from src.main import app
from src.moderator.moderator import STANDARD_ADVISORY_DISCLAIMER

client = TestClient(app)


def make_dummy_chunk(chunk_id: str, file_path: str = "src/database.py") -> CodeChunk:
    return CodeChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        relative_path=file_path.split("/")[-1],
        language=LanguageEnum.python,
        chunk_type=ChunkType.function,
        name=f"func_{chunk_id.replace('-', '_')}",
        start_line=10,
        end_line=25,
        code="def query_user(user_id):\n    return db.execute(f'SELECT * FROM users WHERE id = {user_id}')\n",
    )


def make_test_finding(
    id: str,
    agent_role: AgentRoleEnum,
    file_path: str = "src/database.py",
    start_line: int = 10,
    end_line: int = 15,
    title: str = "SQL Injection in User Query",
    category: str = "OWASP A03:2021-Injection",
    cwe_id: str = "CWE-89",
    severity: SeverityEnum = SeverityEnum.CRITICAL,
    confidence: ConfidenceEnum = ConfidenceEnum.HIGH,
) -> Finding:
    return Finding(
        id=id,
        agent_role=agent_role,
        category=category,
        cwe_id=cwe_id,
        title=title,
        description="Raw SQL query string concatenation without parameterization.",
        severity=severity,
        confidence=confidence,
        evidence=CodeEvidence(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            code_snippet="db.execute(f'SELECT * FROM users WHERE id = {user_id}')",
        ),
        remediation=RemediationAdvice(
            explanation="Use query parameter substitution",
            recommended_fix="db.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
        ),
    )


def test_review_run_endpoint_end_to_end():
    """Verify POST /api/v1/review/run with multi-chunk context and deduplication."""
    chunk1 = make_dummy_chunk("chunk-1", "src/database.py")
    chunk2 = make_dummy_chunk("chunk-2", "src/service.py")

    file1 = IngestedFile(
        file_path="src/database.py",
        relative_path="database.py",
        language=LanguageEnum.python,
        content="...",
        line_count=30,
        size_bytes=400,
    )
    file2 = IngestedFile(
        file_path="src/service.py",
        relative_path="service.py",
        language=LanguageEnum.python,
        content="...",
        line_count=40,
        size_bytes=600,
    )

    summary = RepositorySummary(
        source_type=IngestionSourceType.local,
        source_path_or_url="/mock/repo",
        total_files=2,
        total_lines=70,
        files=[file1, file2],
    )
    context = ReviewContext(
        repo_id="test-repo-pipeline",
        summary=summary,
        chunks=[chunk1, chunk2],
        total_chunks=2,
    )

    # 1. Critical Security finding on chunk 1
    sec_finding = make_test_finding(
        id="SEC-001",
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        file_path="src/database.py",
        start_line=10,
        end_line=15,
        title="SQL Injection in User Query",
        cwe_id="CWE-89",
        severity=SeverityEnum.CRITICAL,
        confidence=ConfidenceEnum.HIGH,
    )

    # 2. Duplicate Architectural finding on chunk 1 (same lines/file)
    arch_finding_dup = make_test_finding(
        id="ARCH-001",
        agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
        file_path="src/database.py",
        start_line=12,
        end_line=16,
        title="SQL Query Execution Pattern Defect",
        cwe_id=None,
        severity=SeverityEnum.MEDIUM,
        confidence=ConfidenceEnum.MEDIUM,
    )

    # 3. Distinct architectural finding on chunk 2
    arch_finding_distinct = make_test_finding(
        id="ARCH-002",
        agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
        file_path="src/service.py",
        start_line=20,
        end_line=35,
        title="High Cyclomatic Complexity in Service Layer",
        category="Complexity Defect",
        cwe_id=None,
        severity=SeverityEnum.LOW,
        confidence=ConfidenceEnum.HIGH,
    )

    mock_agent_results = [
        AgentResult(
            agent_role=AgentRoleEnum.SECURITY_AUDITOR,
            chunk_id="chunk-1",
            file_path="src/database.py",
            execution_time_ms=85.0,
            success=True,
            findings=[sec_finding],
            tokens_used=120,
        ),
        AgentResult(
            agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
            chunk_id="chunk-1",
            file_path="src/database.py",
            execution_time_ms=90.0,
            success=True,
            findings=[arch_finding_dup],
            tokens_used=140,
        ),
        AgentResult(
            agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
            chunk_id="chunk-2",
            file_path="src/service.py",
            execution_time_ms=75.0,
            success=True,
            findings=[arch_finding_distinct],
            tokens_used=110,
        ),
    ]

    async def mock_run_review(self, ctx, progress_callback=None):
        return mock_agent_results

    with patch("src.orchestrator.runner.ReviewOrchestrator.run_review", new=mock_run_review):
        response = client.post("/api/v1/review/run", json=context.model_dump())

    assert response.status_code == 200
    data = response.json()

    # Validate against ConsolidatedReview Pydantic schema
    review = ConsolidatedReview(**data)
    assert review.repo_id == "test-repo-pipeline"
    assert review.status == "completed"
    assert review.total_files_reviewed == 2
    assert review.total_chunks_reviewed == 2

    # Advisory safety verification (REQ-11)
    assert review.advisory_disclaimer == STANDARD_ADVISORY_DISCLAIMER
    assert all(mf.finding.is_advisory_only for mf in review.findings)

    # Deduplication verification: SEC-001 and ARCH-001 merged into 1
    assert len(review.findings) == 2

    # Prioritization check: Findings must be sorted in descending order of risk score
    top_mf = review.findings[0]
    second_mf = review.findings[1]
    assert top_mf.priority_rank == 1
    assert second_mf.priority_rank == 2
    assert top_mf.risk_score >= second_mf.risk_score

    # Arbitration check: Security precedence applied
    assert top_mf.finding.id == "SEC-001"
    assert top_mf.is_deduplicated is True
    assert set(top_mf.sources) == {AgentRoleEnum.SECURITY_AUDITOR, AgentRoleEnum.SOFTWARE_ARCHITECT}
    assert top_mf.arbitration_notes is not None
    assert "Security Auditor recommendation takes precedence" in top_mf.arbitration_notes

    # Standalone finding check
    assert second_mf.finding.id == "ARCH-002"
    assert second_mf.is_deduplicated is False
    assert second_mf.sources == [AgentRoleEnum.SOFTWARE_ARCHITECT]

    # Metrics and risk summary check
    assert review.risk_summary["total_findings"] == 2
    assert review.risk_summary["deduplicated_count"] == 1
    assert review.risk_summary["critical_count"] == 1
    assert review.agent_metrics["total_agent_calls"] == 3
    assert review.agent_metrics["total_tokens_used"] == 370


def test_review_moderate_endpoint_direct():
    """Verify POST /api/v1/review/moderate endpoint directly with pre-computed agent results."""
    finding_sec = make_test_finding(
        id="SEC-002",
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        file_path="src/auth.py",
        start_line=5,
        end_line=10,
        title="Hardcoded Secret Key Detected",
        category="OWASP A07:2021-Identification and Authentication Failures",
        cwe_id="CWE-798",
        severity=SeverityEnum.HIGH,
        confidence=ConfidenceEnum.HIGH,
    )
    result = AgentResult(
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        chunk_id="chunk-auth-1",
        file_path="src/auth.py",
        execution_time_ms=50.0,
        success=True,
        findings=[finding_sec],
        tokens_used=80,
    )

    payload = {
        "repo_id": "moderate-test-repo",
        "agent_results": [result.model_dump()],
        "total_files": 1,
        "total_chunks": 1,
    }

    response = client.post("/api/v1/review/moderate", json=payload)
    assert response.status_code == 200

    data = response.json()
    review = ConsolidatedReview(**data)
    assert review.repo_id == "moderate-test-repo"
    assert len(review.findings) == 1
    assert review.findings[0].finding.id == "SEC-002"
    assert review.findings[0].priority_rank == 1
    assert review.findings[0].risk_score == 8.0  # High (7.5) * High (1.0) + 0.5 = 8.0
    assert review.findings[0].finding.is_advisory_only is True
    assert review.severity_distribution["HIGH"] == 1


def test_zero_route_collisions_and_registry():
    """Confirm all expected review endpoints are registered without collisions."""
    route_paths = [getattr(r, "path", "") for r in client._get_all_routes()]
    assert "/api/v1/review/run" in route_paths
    assert "/api/v1/review/moderate" in route_paths
    assert "/api/v1/ingest/local" in route_paths
    assert "/api/v1/context/prepare" in route_paths
    assert "/health" in route_paths
