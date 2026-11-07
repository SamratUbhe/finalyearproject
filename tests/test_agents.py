"""Unit tests for SecurityAuditorAgent and SoftwareArchitectAgent."""

from unittest.mock import AsyncMock
import pytest

from src.agents.architect_agent import SoftwareArchitectAgent
from src.agents.gemini_client import GeminiClient
from src.agents.security_agent import SecurityAuditorAgent
from src.core.models import (
    AgentRoleEnum,
    ChunkType,
    CodeChunk,
    ConfidenceEnum,
    Finding,
    LanguageEnum,
    SeverityEnum,
)


@pytest.fixture
def sample_chunk() -> CodeChunk:
    return CodeChunk(
        chunk_id="chunk-test-1",
        file_path="src/database/query.py",
        relative_path="query.py",
        language=LanguageEnum.python,
        chunk_type=ChunkType.function,
        name="get_user_records",
        start_line=10,
        end_line=25,
        code='def get_user_records(user_input):\n    query = "SELECT * FROM users WHERE name = \'" + user_input + "\'"\n    return db.execute(query)\n',
        imports=["import db"],
        context_lines="import db\n",
    )


@pytest.mark.asyncio
async def test_security_auditor_agent_detects_sqli(sample_chunk):
    mock_findings_payload = [
        {
            "id": "SEC-001",
            "category": "OWASP A03:2021-Injection",
            "cwe_id": "CWE-89",
            "owasp_category": "A03:2021-Injection",
            "title": "SQL Injection in User Lookup",
            "description": "User input is directly concatenated into a raw SQL query string without sanitization.",
            "severity": "CRITICAL",
            "confidence": "HIGH",
            "evidence": {
                "file_path": "src/database/query.py",
                "start_line": 11,
                "end_line": 12,
                "code_snippet": "query = \"SELECT * FROM users WHERE name = '\" + user_input + \"'\"",
            },
            "remediation": {
                "explanation": "Use parameterized queries or prepared statements to prevent injection.",
                "recommended_fix": 'db.execute("SELECT * FROM users WHERE name = %s", (user_input,))',
                "references": ["https://owasp.org/Top10/A03_2021-Injection/"],
            },
        }
    ]

    mock_client = AsyncMock(spec=GeminiClient)
    mock_client.generate_structured_review.return_value = mock_findings_payload

    agent = SecurityAuditorAgent(client=mock_client)
    result = await agent.analyze_chunk(sample_chunk)

    assert result.success is True
    assert result.agent_role == AgentRoleEnum.SECURITY_AUDITOR
    assert result.chunk_id == "chunk-test-1"
    assert result.file_path == "src/database/query.py"
    assert result.execution_time_ms >= 0.0
    assert len(result.findings) == 1

    finding = result.findings[0]
    assert finding.id == "SEC-001"
    assert finding.agent_role == AgentRoleEnum.SECURITY_AUDITOR
    assert finding.cwe_id == "CWE-89"
    assert finding.owasp_category == "A03:2021-Injection"
    assert finding.severity == SeverityEnum.CRITICAL
    assert finding.confidence == ConfidenceEnum.HIGH
    assert finding.is_advisory_only is True
    assert finding.evidence.start_line == 11
    assert "parameterized queries" in finding.remediation.explanation


@pytest.mark.asyncio
async def test_software_architect_agent_detects_complexity(sample_chunk):
    mock_findings_payload = [
        {
            "id": "ARCH-001",
            "category": "Code Quality / Complexity",
            "cwe_id": "CWE-400",
            "title": "High Cyclomatic Complexity and Monolithic Function",
            "description": "Function performs unhandled database query operations without connection management.",
            "severity": "MEDIUM",
            "confidence": "HIGH",
            "evidence": {
                "file_path": "src/database/query.py",
                "start_line": 10,
                "end_line": 13,
                "code_snippet": "def get_user_records(user_input):\n    ...",
            },
            "remediation": {
                "explanation": "Encapsulate data access within a repository pattern using a managed connection context.",
                "recommended_fix": "with db.get_connection() as conn:\n    ...",
                "references": ["https://refactoring.guru/design-patterns/repository"],
            },
        }
    ]

    mock_client = AsyncMock(spec=GeminiClient)
    mock_client.generate_structured_review.return_value = mock_findings_payload

    agent = SoftwareArchitectAgent(client=mock_client)
    result = await agent.analyze_chunk(sample_chunk)

    assert result.success is True
    assert result.agent_role == AgentRoleEnum.SOFTWARE_ARCHITECT
    assert result.chunk_id == "chunk-test-1"
    assert len(result.findings) == 1

    finding = result.findings[0]
    assert finding.id == "ARCH-001"
    assert finding.agent_role == AgentRoleEnum.SOFTWARE_ARCHITECT
    assert finding.severity == SeverityEnum.MEDIUM
    assert finding.confidence == ConfidenceEnum.HIGH
    assert finding.is_advisory_only is True
    assert "repository" in finding.remediation.explanation.lower()


@pytest.mark.asyncio
async def test_security_auditor_agent_handles_llm_exception(sample_chunk):
    mock_client = AsyncMock(spec=GeminiClient)
    mock_client.generate_structured_review.side_effect = RuntimeError("Gemini API connection error")

    agent = SecurityAuditorAgent(client=mock_client)
    result = await agent.analyze_chunk(sample_chunk)

    assert result.success is False
    assert result.agent_role == AgentRoleEnum.SECURITY_AUDITOR
    assert result.error_message == "Gemini API connection error"
    assert result.findings == []


@pytest.mark.asyncio
async def test_software_architect_agent_handles_llm_exception(sample_chunk):
    mock_client = AsyncMock(spec=GeminiClient)
    mock_client.generate_structured_review.side_effect = ValueError("Invalid API key")

    agent = SoftwareArchitectAgent(client=mock_client)
    result = await agent.analyze_chunk(sample_chunk)

    assert result.success is False
    assert result.agent_role == AgentRoleEnum.SOFTWARE_ARCHITECT
    assert "Invalid API key" in str(result.error_message)
    assert result.findings == []


@pytest.mark.asyncio
async def test_agents_handle_empty_findings(sample_chunk):
    mock_client = AsyncMock(spec=GeminiClient)
    mock_client.generate_structured_review.return_value = []

    sec_agent = SecurityAuditorAgent(client=mock_client)
    sec_result = await sec_agent.analyze_chunk(sample_chunk)
    assert sec_result.success is True
    assert sec_result.findings == []

    arch_agent = SoftwareArchitectAgent(client=mock_client)
    arch_result = await arch_agent.analyze_chunk(sample_chunk)
    assert arch_result.success is True
    assert arch_result.findings == []


@pytest.mark.asyncio
async def test_agents_handle_wrapped_dict_findings(sample_chunk):
    wrapped_payload = {
        "findings": [
            {
                "id": "SEC-WRAP-1",
                "title": "Hardcoded Token",
                "severity": "HIGH",
            }
        ]
    }
    mock_client = AsyncMock(spec=GeminiClient)
    mock_client.generate_structured_review.return_value = wrapped_payload

    agent = SecurityAuditorAgent(client=mock_client)
    result = await agent.analyze_chunk(sample_chunk)

    assert result.success is True
    assert len(result.findings) == 1
    assert result.findings[0].id == "SEC-WRAP-1"
    assert result.findings[0].severity == SeverityEnum.HIGH

