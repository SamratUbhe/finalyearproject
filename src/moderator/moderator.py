"""Review Moderator Agent performing deduplication, conflict arbitration, and risk prioritization."""

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from src.core.models import (
    AgentResult,
    AgentRoleEnum,
    ConfidenceEnum,
    ConsolidatedReview,
    Finding,
    ModeratedFinding,
    SeverityEnum,
)

logger = logging.getLogger(__name__)

DEFAULT_SEVERITY_WEIGHTS: Dict[SeverityEnum, float] = {
    SeverityEnum.CRITICAL: 10.0,
    SeverityEnum.HIGH: 7.5,
    SeverityEnum.MEDIUM: 5.0,
    SeverityEnum.LOW: 2.5,
    SeverityEnum.INFO: 1.0,
}

DEFAULT_CONFIDENCE_MULTIPLIERS: Dict[ConfidenceEnum, float] = {
    ConfidenceEnum.HIGH: 1.0,
    ConfidenceEnum.MEDIUM: 0.75,
    ConfidenceEnum.LOW: 0.5,
}

STANDARD_ADVISORY_DISCLAIMER: str = (
    "This review report contains purely advisory recommendations for developer "
    "evaluation. No source code modifications have been applied automatically."
)


class ReviewModeratorAgent:
    """Consolidates raw observations from specialist agents into a prioritized, arbitrated review."""

    def __init__(
        self,
        severity_weights: Optional[Dict[SeverityEnum, float]] = None,
        confidence_multipliers: Optional[Dict[ConfidenceEnum, float]] = None,
    ) -> None:
        self.severity_weights = severity_weights or dict(DEFAULT_SEVERITY_WEIGHTS)
        self.confidence_multipliers = confidence_multipliers or dict(
            DEFAULT_CONFIDENCE_MULTIPLIERS
        )

    def calculate_risk_score(
        self,
        severity: SeverityEnum,
        confidence: ConfidenceEnum,
        has_evidence: bool = True,
    ) -> float:
        """Calculate quantitative risk score: Severity * Confidence + Evidence fidelity bonus (capped at 10.0)."""
        weight = self.severity_weights.get(severity, 5.0)
        multiplier = self.confidence_multipliers.get(confidence, 0.75)
        base = weight * multiplier

        if has_evidence:
            base += 0.5

        base = min(base, 10.0)
        return round(base, 1)

    def are_findings_duplicate(self, f1: Finding, f2: Finding) -> bool:
        """Determine whether two findings refer to the same defect via path, line span overlap, and semantics."""
        # 1. Matching file path
        p1 = os.path.normpath(f1.evidence.file_path).replace("\\", "/").lower()
        p2 = os.path.normpath(f2.evidence.file_path).replace("\\", "/").lower()
        if p1 != p2:
            return False

        # 2. Overlapping or adjacent line spans (+3 lines buffer)
        start_overlap = max(f1.evidence.start_line, f2.evidence.start_line)
        end_overlap = min(f1.evidence.end_line, f2.evidence.end_line) + 3
        if start_overlap > end_overlap:
            return False

        # 3. Matching CWE (if both specified) or Jaccard semantic similarity
        if f1.cwe_id and f2.cwe_id:
            cwe1 = f1.cwe_id.strip().upper()
            cwe2 = f2.cwe_id.strip().upper()
            if cwe1 == cwe2:
                return True
            # Different explicit CWEs indicate distinct issues on the same lines
            return False

        # Semantic token similarity on title and/or title+category
        words_title1 = set(re.findall(r"\w+", f1.title.lower()))
        words_title2 = set(re.findall(r"\w+", f2.title.lower()))
        words_combined1 = set(re.findall(r"\w+", f"{f1.title} {f1.category}".lower()))
        words_combined2 = set(re.findall(r"\w+", f"{f2.title} {f2.category}".lower()))

        def _jaccard(s1: Set[str], s2: Set[str]) -> float:
            if not s1 or not s2:
                return 0.0
            union_len = len(s1 | s2)
            return len(s1 & s2) / union_len if union_len > 0 else 0.0

        sim_title = _jaccard(words_title1, words_title2)
        sim_combined = _jaccard(words_combined1, words_combined2)

        return max(sim_title, sim_combined) > 0.3

    def arbitrate_conflict(
        self, findings: List[Finding]
    ) -> Tuple[Finding, List[AgentRoleEnum], Optional[str]]:
        """Arbitrate between conflicting or duplicate findings, giving precedence to security over style/architecture."""
        if not findings:
            raise ValueError("Cannot arbitrate empty findings list")

        # Extract unique contributing agent roles preserving priority order
        sources: List[AgentRoleEnum] = []
        for f in findings:
            if f.agent_role not in sources:
                sources.append(f.agent_role)

        has_security = AgentRoleEnum.SECURITY_AUDITOR in sources
        has_architect = AgentRoleEnum.SOFTWARE_ARCHITECT in sources

        if has_security and has_architect:
            # Security Precedence Rule: The security finding takes precedence
            security_findings = [
                f for f in findings if f.agent_role == AgentRoleEnum.SECURITY_AUDITOR
            ]
            security_findings.sort(
                key=lambda f: (
                    self.severity_weights.get(f.severity, 0.0),
                    self.confidence_multipliers.get(f.confidence, 0.0),
                ),
                reverse=True,
            )
            selected = security_findings[0]
            arbitration_notes = (
                "Security Auditor recommendation takes precedence over Software Architect "
                "simplification/refactoring."
            )
        else:
            # Select finding with highest severity, then confidence
            sorted_findings = sorted(
                findings,
                key=lambda f: (
                    self.severity_weights.get(f.severity, 0.0),
                    self.confidence_multipliers.get(f.confidence, 0.0),
                ),
                reverse=True,
            )
            selected = sorted_findings[0]
            arbitration_notes = (
                f"Consolidated {len(findings)} findings from {', '.join(r.value for r in sources)}."
                if len(findings) > 1
                else None
            )

        return selected, sources, arbitration_notes

    def deduplicate_and_arbitrate(
        self, findings: List[Finding]
    ) -> List[Tuple[Finding, List[AgentRoleEnum], bool, Optional[str]]]:
        """Group duplicate findings and apply deterministic arbitration to each group."""
        if not findings:
            return []

        n = len(findings)
        # Disjoint-set union (DSU) for grouping duplicate findings
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_j] = root_i

        for i in range(n):
            for j in range(i + 1, n):
                if self.are_findings_duplicate(findings[i], findings[j]):
                    union(i, j)

        groups_dict: Dict[int, List[Finding]] = {}
        for idx, finding in enumerate(findings):
            root = find(idx)
            groups_dict.setdefault(root, []).append(finding)

        results: List[Tuple[Finding, List[AgentRoleEnum], bool, Optional[str]]] = []
        for group in groups_dict.values():
            if len(group) == 1:
                item = group[0]
                results.append((item, [item.agent_role], False, None))
            else:
                selected, sources, notes = self.arbitrate_conflict(group)
                results.append((selected, sources, True, notes))

        return results

    def moderate_review(
        self,
        repo_id: str,
        agent_results: List[AgentResult],
        total_files: int = 0,
        total_chunks: int = 0,
    ) -> ConsolidatedReview:
        """Consolidate agent results into a finalized, prioritized ConsolidatedReview."""
        # 1. Collect all findings from successful agent analyses
        raw_findings: List[Finding] = []
        for ar in agent_results:
            if ar.success:
                raw_findings.extend(ar.findings)

        # 2. Deduplicate and arbitrate
        arbitrated = self.deduplicate_and_arbitrate(raw_findings)

        # 3. Score risk and wrap in ModeratedFinding
        moderated_items: List[ModeratedFinding] = []
        for finding, sources, is_dedup, notes in arbitrated:
            has_ev = bool(finding.evidence and finding.evidence.code_snippet)
            score = self.calculate_risk_score(
                severity=finding.severity,
                confidence=finding.confidence,
                has_evidence=has_ev,
            )
            # Advisory safety guarantee (REQ-11)
            finding.is_advisory_only = True
            finding.raw_risk_score = score

            moderated_items.append(
                ModeratedFinding(
                    finding=finding,
                    risk_score=score,
                    priority_rank=0,
                    is_deduplicated=is_dedup,
                    sources=sources,
                    arbitration_notes=notes,
                )
            )

        # 4. Sort descending by risk_score (tie breaker: severity weight)
        moderated_items.sort(
            key=lambda mf: (
                mf.risk_score,
                self.severity_weights.get(mf.finding.severity, 0.0),
            ),
            reverse=True,
        )

        # 5. Assign sequential priority rank
        for idx, item in enumerate(moderated_items, start=1):
            item.priority_rank = idx

        # 6. Compute severity distribution
        severity_distribution: Dict[str, int] = {
            SeverityEnum.CRITICAL.value: 0,
            SeverityEnum.HIGH.value: 0,
            SeverityEnum.MEDIUM.value: 0,
            SeverityEnum.LOW.value: 0,
            SeverityEnum.INFO.value: 0,
        }
        for item in moderated_items:
            sev_key = item.finding.severity.value
            severity_distribution[sev_key] = severity_distribution.get(sev_key, 0) + 1

        # 7. Compute risk summary
        total_findings = len(moderated_items)
        avg_score = (
            round(sum(mf.risk_score for mf in moderated_items) / total_findings, 2)
            if total_findings > 0
            else 0.0
        )
        max_score = max((mf.risk_score for mf in moderated_items), default=0.0)
        dedup_count = sum(1 for mf in moderated_items if mf.is_deduplicated)

        risk_summary: Dict[str, Any] = {
            "total_findings": total_findings,
            "average_risk_score": avg_score,
            "max_risk_score": max_score,
            "critical_count": severity_distribution.get(SeverityEnum.CRITICAL.value, 0),
            "high_count": severity_distribution.get(SeverityEnum.HIGH.value, 0),
            "deduplicated_count": dedup_count,
        }

        # 8. Compute agent execution metrics
        total_exec_time = sum(ar.execution_time_ms for ar in agent_results)
        total_tokens = sum(ar.tokens_used or 0 for ar in agent_results)
        successful_calls = sum(1 for ar in agent_results if ar.success)
        failed_calls = sum(1 for ar in agent_results if not ar.success)

        by_role: Dict[str, Any] = {}
        for ar in agent_results:
            r_name = ar.agent_role.value
            if r_name not in by_role:
                by_role[r_name] = {
                    "calls": 0,
                    "success": 0,
                    "failed": 0,
                    "execution_time_ms": 0.0,
                    "findings_count": 0,
                    "tokens_used": 0,
                }
            by_role[r_name]["calls"] += 1
            if ar.success:
                by_role[r_name]["success"] += 1
                by_role[r_name]["findings_count"] += len(ar.findings)
            else:
                by_role[r_name]["failed"] += 1
            by_role[r_name]["execution_time_ms"] += ar.execution_time_ms
            by_role[r_name]["tokens_used"] += ar.tokens_used or 0

        agent_metrics: Dict[str, Any] = {
            "total_agent_calls": len(agent_results),
            "successful_agent_calls": successful_calls,
            "failed_agent_calls": failed_calls,
            "total_execution_time_ms": round(total_exec_time, 2),
            "total_tokens_used": total_tokens,
            "by_role": by_role,
        }

        review_id = f"rev-{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat()

        return ConsolidatedReview(
            review_id=review_id,
            repo_id=repo_id,
            created_at=created_at,
            status="completed",
            total_files_reviewed=total_files,
            total_chunks_reviewed=total_chunks,
            findings=moderated_items,
            severity_distribution=severity_distribution,
            risk_summary=risk_summary,
            agent_metrics=agent_metrics,
            advisory_disclaimer=STANDARD_ADVISORY_DISCLAIMER,
        )
