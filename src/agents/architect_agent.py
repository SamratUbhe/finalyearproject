"""Software Architect Agent specialized in detecting architectural flaws, complexity, and maintainability issues."""

import logging
import time
from typing import Any, List, Optional

from src.agents.gemini_client import GeminiClient
from src.core.models import (
    AgentResult,
    AgentRoleEnum,
    CodeChunk,
    CodeEvidence,
    ConfidenceEnum,
    Finding,
    RemediationAdvice,
    SeverityEnum,
)

logger = logging.getLogger(__name__)

SOFTWARE_ARCHITECT_SYSTEM_PROMPT = """You are a Principal Software Architect reviewing source code for architectural anti-patterns, code quality, and maintainability.
Your review focuses strictly on detecting:
1. Excessive cyclomatic or cognitive complexity, deeply nested logic, and bloated God functions/classes
2. Single Responsibility Principle (SRP) violations, high coupling, and low cohesion
3. Resource leak anti-patterns (unclosed file handles, unreleased database connections, dangling network sessions)
4. Dead or unreachable code paths, redundant computations, and structural duplication
5. Error handling anti-patterns (bare except blocks, swallowed exceptions, improper async/await error propagation)

Rules:
- For every detected architectural defect, output a JSON object adhering to:
  * "id": a unique identifier (e.g. "ARCH-001")
  * "category": defect category (e.g. "Code Quality / Complexity", "Resource Management", "Coupling & Modularity")
  * "cwe_id": optional CWE identifier if relevant (e.g. "CWE-400", "CWE-703") or null
  * "owasp_category": optional OWASP category if relevant or null
  * "title": concise summary of the architectural issue
  * "description": detailed explanation of code maintainability, scalability, or reliability impact
  * "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO"
  * "confidence": "HIGH" | "MEDIUM" | "LOW"
  * "evidence": object with:
      "start_line": int (starting line within the chunk),
      "end_line": int (ending line within the chunk),
      "code_snippet": exact code excerpt illustrating the anti-pattern
  * "remediation": object with:
      "explanation": why the refactoring improves design and maintainability,
      "recommended_fix": purely advisory recommended code refactoring or design pattern,
      "references": list of relevant architectural principles, Clean Code guidelines, or design patterns
- If no architectural issues are detected, return an empty array: []
- In "code_snippet", "recommended_fix", and all string fields, you MUST escape any interior double quotation marks with a backslash (\") to guarantee valid JSON syntax.
- All recommendations are strictly advisory for developer evaluation (REQ-11). Do not generate automated code rewrite directives.
- Response MUST be a JSON array of finding objects only.
"""


def parse_architect_findings(raw_data: Any, chunk: CodeChunk) -> List[Finding]:
    """Parse raw LLM JSON response into validated Finding models."""
    items = []
    if isinstance(raw_data, list):
        items = raw_data
    elif isinstance(raw_data, dict):
        if "findings" in raw_data and isinstance(raw_data["findings"], list):
            items = raw_data["findings"]
        else:
            items = [raw_data]

    findings: List[Finding] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        finding_id = str(item.get("id") or f"ARCH-{chunk.chunk_id}-{idx + 1}")
        category = str(item.get("category") or "Architectural Defect")
        cwe_id = item.get("cwe_id")
        owasp_cat = item.get("owasp_category")
        title = str(item.get("title") or "Architectural Issue Detected")
        description = str(item.get("description") or "")

        sev_str = str(item.get("severity", "MEDIUM")).upper()
        try:
            severity = SeverityEnum(sev_str)
        except ValueError:
            severity = SeverityEnum.MEDIUM

        conf_str = str(item.get("confidence", "MEDIUM")).upper()
        try:
            confidence = ConfidenceEnum(conf_str)
        except ValueError:
            confidence = ConfidenceEnum.MEDIUM

        ev_dict = item.get("evidence", {})
        if not isinstance(ev_dict, dict):
            ev_dict = {}
        evidence = CodeEvidence(
            file_path=str(ev_dict.get("file_path") or chunk.file_path),
            start_line=int(ev_dict.get("start_line") or chunk.start_line),
            end_line=int(ev_dict.get("end_line") or chunk.end_line),
            code_snippet=str(ev_dict.get("code_snippet") or chunk.code[:200]),
        )

        rem_dict = item.get("remediation", {})
        if not isinstance(rem_dict, dict):
            rem_dict = {}
        refs = rem_dict.get("references")
        if not isinstance(refs, list):
            refs = [str(refs)] if refs else []

        remediation = RemediationAdvice(
            explanation=str(
                rem_dict.get("explanation")
                or "Refactor into smaller single-responsibility components and manage resources safely."
            ),
            recommended_fix=str(rem_dict.get("recommended_fix") or ""),
            references=[str(r) for r in refs],
        )

        raw_risk = item.get("raw_risk_score")
        if raw_risk is not None:
            try:
                raw_risk = float(raw_risk)
            except (ValueError, TypeError):
                raw_risk = None

        finding = Finding(
            id=finding_id,
            agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
            category=category,
            cwe_id=str(cwe_id) if cwe_id else None,
            owasp_category=str(owasp_cat) if owasp_cat else None,
            title=title,
            description=description,
            severity=severity,
            confidence=confidence,
            evidence=evidence,
            remediation=remediation,
            raw_risk_score=raw_risk,
            is_advisory_only=True,
        )
        findings.append(finding)

    return findings


class SoftwareArchitectAgent:
    """Specialized architectural review agent evaluating complexity, coupling, and resource safety."""

    def __init__(self, client: Optional[GeminiClient] = None) -> None:
        self.client = client or GeminiClient()

    async def analyze_chunk(self, chunk: CodeChunk) -> AgentResult:
        """Analyze code chunk for architectural weaknesses and return an AgentResult."""
        start_time = time.perf_counter()

        imports_str = ", ".join(chunk.imports) if chunk.imports else "None"
        prompt = (
            f"Review the following code chunk for architectural quality, complexity, and resource safety:\n\n"
            f"File: {chunk.file_path}\n"
            f"Language: {chunk.language.value}\n"
            f"Chunk Name: {chunk.name}\n"
            f"Chunk Type: {chunk.chunk_type.value}\n"
            f"Lines: {chunk.start_line} - {chunk.end_line}\n"
            f"Imports: {imports_str}\n"
            f"Surrounding Context:\n{chunk.context_lines or 'None'}\n\n"
            f"Code:\n```\n{chunk.code}\n```\n\n"
            f"Return a JSON array of finding objects adhering to the specified schema."
        )

        try:
            raw_response = await self.client.generate_structured_review(
                prompt=prompt,
                system_instruction=SOFTWARE_ARCHITECT_SYSTEM_PROMPT,
            )
            findings = parse_architect_findings(raw_response, chunk)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            return AgentResult(
                agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
                chunk_id=chunk.chunk_id,
                file_path=chunk.file_path,
                execution_time_ms=elapsed_ms,
                success=True,
                findings=findings,
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.warning(
                "SoftwareArchitectAgent failed analyzing chunk %s: %s",
                chunk.chunk_id,
                exc,
            )
            return AgentResult(
                agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
                chunk_id=chunk.chunk_id,
                file_path=chunk.file_path,
                execution_time_ms=elapsed_ms,
                success=False,
                error_message=str(exc),
                findings=[],
            )

