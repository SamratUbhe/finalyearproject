"""Unit tests for ReviewModeratorAgent deduplication, arbitration, and risk scoring."""

import pytest
from src.core.models import (
    AgentResult,
    AgentRoleEnum,
    CodeEvidence,
    ConfidenceEnum,
    ConsolidatedReview,
    Finding,
    RemediationAdvice,
    SeverityEnum,
)
from src.moderator.moderator import ReviewModeratorAgent, STANDARD_ADVISORY_DISCLAIMER


def create_dummy_finding(
    id: str,
    agent_role: AgentRoleEnum,
    file_path: str = "src/app.py",
    start_line: int = 10,
    end_line: int = 15,
    title: str = "SQL Injection in User Query",
    category: str = "OWASP A03:2021-Injection",
    cwe_id: str = "CWE-89",
    severity: SeverityEnum = SeverityEnum.HIGH,
    confidence: ConfidenceEnum = ConfidenceEnum.HIGH,
) -> Finding:
    """Helper to construct dummy Finding models for testing."""
    return Finding(
        id=id,
        agent_role=agent_role,
        category=category,
        cwe_id=cwe_id,
        title=title,
        description="Detailed test description",
        severity=severity,
        confidence=confidence,
        evidence=CodeEvidence(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            code_snippet="cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')",
        ),
        remediation=RemediationAdvice(
            explanation="Use parameterized queries",
            recommended_fix="cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
        ),
    )


def test_calculate_risk_score():
    moderator = ReviewModeratorAgent()

    # Critical (10.0) * High (1.0) + 0.5 bonus = 10.5 -> capped at 10.0
    score = moderator.calculate_risk_score(SeverityEnum.CRITICAL, ConfidenceEnum.HIGH, has_evidence=True)
    assert score == 10.0

    # High (7.5) * Medium (0.75) = 5.625 + 0.5 = 6.125 -> rounded to 6.1
    score = moderator.calculate_risk_score(SeverityEnum.HIGH, ConfidenceEnum.MEDIUM, has_evidence=True)
    assert score == 6.1

    # Medium (5.0) * Low (0.5) = 2.5 + 0.5 = 3.0
    score = moderator.calculate_risk_score(SeverityEnum.MEDIUM, ConfidenceEnum.LOW, has_evidence=True)
    assert score == 3.0

    # Low (2.5) * High (1.0) = 2.5 without evidence bonus = 2.5
    score = moderator.calculate_risk_score(SeverityEnum.LOW, ConfidenceEnum.HIGH, has_evidence=False)
    assert score == 2.5


def test_are_findings_duplicate_cwe_and_span():
    moderator = ReviewModeratorAgent()

    f1 = create_dummy_finding(
        id="SEC-1",
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        start_line=10,
        end_line=15,
        cwe_id="CWE-89",
    )
    f2 = create_dummy_finding(
        id="SEC-2",
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        start_line=13,
        end_line=18,
        cwe_id="CWE-89",
    )
    assert moderator.are_findings_duplicate(f1, f2) is True


def test_are_findings_duplicate_jaccard_similarity():
    moderator = ReviewModeratorAgent()

    # Security finding has CWE, Architect finding has no CWE, but semantic words overlap
    f_sec = create_dummy_finding(
        id="SEC-1",
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        start_line=10,
        end_line=15,
        title="SQL Injection Vulnerability in Database Query",
        category="OWASP Injection",
        cwe_id="CWE-89",
    )
    f_arch = create_dummy_finding(
        id="ARCH-1",
        agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
        start_line=12,
        end_line=16,
        title="Unsafe SQL Database Query Execution Pattern",
        category="Architecture Defect",
        cwe_id=None,
    )
    assert moderator.are_findings_duplicate(f_sec, f_arch) is True


def test_are_findings_duplicate_different_files_or_far_lines():
    moderator = ReviewModeratorAgent()

    f1 = create_dummy_finding(id="1", agent_role=AgentRoleEnum.SECURITY_AUDITOR, file_path="src/a.py", start_line=10, end_line=15)
    f2 = create_dummy_finding(id="2", agent_role=AgentRoleEnum.SECURITY_AUDITOR, file_path="src/b.py", start_line=10, end_line=15)
    assert moderator.are_findings_duplicate(f1, f2) is False

    # Lines too far apart
    f3 = create_dummy_finding(id="3", agent_role=AgentRoleEnum.SECURITY_AUDITOR, file_path="src/a.py", start_line=100, end_line=110)
    assert moderator.are_findings_duplicate(f1, f3) is False


def test_security_precedence_arbitration():
    moderator = ReviewModeratorAgent()

    sec_finding = create_dummy_finding(
        id="SEC-1",
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        title="SQL Injection Flaw",
        category="Injection",
        cwe_id="CWE-89",
        severity=SeverityEnum.CRITICAL,
    )
    arch_finding = create_dummy_finding(
        id="ARCH-1",
        agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
        title="Simplify SQL Query String Formatting",
        category="Code Maintainability",
        cwe_id=None,
        severity=SeverityEnum.LOW,
    )

    selected, sources, notes = moderator.arbitrate_conflict([arch_finding, sec_finding])

    assert selected.id == "SEC-1"
    assert selected.agent_role == AgentRoleEnum.SECURITY_AUDITOR
    assert AgentRoleEnum.SECURITY_AUDITOR in sources
    assert AgentRoleEnum.SOFTWARE_ARCHITECT in sources
    assert notes is not None
    assert "Security Auditor recommendation takes precedence" in notes


def test_moderate_review_full_workflow():
    moderator = ReviewModeratorAgent()

    f_sec = create_dummy_finding(
        id="SEC-1",
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        start_line=10,
        end_line=15,
        cwe_id="CWE-89",
        severity=SeverityEnum.CRITICAL,
        confidence=ConfidenceEnum.HIGH,
    )
    f_arch_dup = create_dummy_finding(
        id="ARCH-1",
        agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
        start_line=11,
        end_line=16,
        cwe_id=None,
        title="SQL Injection in User Query",
        category="OWASP A03:2021-Injection",
        severity=SeverityEnum.MEDIUM,
        confidence=ConfidenceEnum.MEDIUM,
    )
    f_arch_distinct = create_dummy_finding(
        id="ARCH-2",
        agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
        file_path="src/service.py",
        start_line=50,
        end_line=80,
        cwe_id=None,
        title="High Cyclomatic Complexity in Dispatcher",
        category="Complexity Defect",
        severity=SeverityEnum.MEDIUM,
        confidence=ConfidenceEnum.HIGH,
    )

    result_sec = AgentResult(
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        chunk_id="chunk-1",
        file_path="src/app.py",
        execution_time_ms=120.0,
        success=True,
        findings=[f_sec],
        tokens_used=150,
    )
    result_arch = AgentResult(
        agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
        chunk_id="chunk-1",
        file_path="src/app.py",
        execution_time_ms=110.0,
        success=True,
        findings=[f_arch_dup, f_arch_distinct],
        tokens_used=220,
    )

    review: ConsolidatedReview = moderator.moderate_review(
        repo_id="test-repo",
        agent_results=[result_sec, result_arch],
        total_files=2,
        total_chunks=2,
    )

    # SEC-1 and ARCH-1 are merged into one moderated finding
    # ARCH-2 is standalone
    assert len(review.findings) == 2
    assert review.repo_id == "test-repo"
    assert review.status == "completed"
    assert review.total_files_reviewed == 2
    assert review.total_chunks_reviewed == 2
    assert review.advisory_disclaimer == STANDARD_ADVISORY_DISCLAIMER

    # Top ranked finding must be the Critical Security finding (due to higher risk score)
    top_finding = review.findings[0]
    assert top_finding.priority_rank == 1
    assert top_finding.finding.id == "SEC-1"
    assert top_finding.is_deduplicated is True
    assert set(top_finding.sources) == {AgentRoleEnum.SECURITY_AUDITOR, AgentRoleEnum.SOFTWARE_ARCHITECT}
    assert top_finding.arbitration_notes is not None
    assert top_finding.risk_score == 10.0
    assert top_finding.finding.is_advisory_only is True

    # Second finding must be the distinct architectural finding
    second_finding = review.findings[1]
    assert second_finding.priority_rank == 2
    assert second_finding.finding.id == "ARCH-2"
    assert second_finding.is_deduplicated is False
    assert second_finding.sources == [AgentRoleEnum.SOFTWARE_ARCHITECT]

    # Check risk summary
    assert review.risk_summary["total_findings"] == 2
    assert review.risk_summary["deduplicated_count"] == 1
    assert review.risk_summary["critical_count"] == 1
    assert review.risk_summary["max_risk_score"] == 10.0

    # Check agent metrics
    assert review.agent_metrics["total_agent_calls"] == 2
    assert review.agent_metrics["successful_agent_calls"] == 2
    assert review.agent_metrics["failed_agent_calls"] == 0
    assert review.agent_metrics["total_tokens_used"] == 370

