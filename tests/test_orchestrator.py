"""Unit and resilience tests for ReviewOrchestrator."""

import asyncio
from typing import List
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.core.models import (
    AgentResult,
    AgentRoleEnum,
    ChunkType,
    CodeChunk,
    CodeEvidence,
    ConfidenceEnum,
    Finding,
    IngestionSourceType,
    LanguageEnum,
    RemediationAdvice,
    RepositorySummary,
    ReviewContext,
    SeverityEnum,
)
from src.orchestrator.runner import ReviewOrchestrator


def make_dummy_chunk(chunk_id: str, file_path: str = "src/main.py") -> CodeChunk:
    return CodeChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        relative_path=file_path.split("/")[-1],
        language=LanguageEnum.python,
        chunk_type=ChunkType.function,
        name=f"func_{chunk_id.replace('-', '_')}",
        start_line=1,
        end_line=15,
        code="def demo():\n    return 42\n",
    )


def make_dummy_context(chunks: List[CodeChunk]) -> ReviewContext:
    summary = RepositorySummary(
        source_type=IngestionSourceType.local,
        source_path_or_url="/fake/repo",
        total_files=len(chunks),
        total_lines=100,
    )
    return ReviewContext(
        repo_id="test-repo-123",
        summary=summary,
        chunks=chunks,
        total_chunks=len(chunks),
    )


@pytest.fixture
def sample_finding() -> Finding:
    return Finding(
        id="SEC-001",
        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
        category="OWASP A03:2021-Injection",
        cwe_id="CWE-89",
        title="Test SQL Injection",
        description="Raw SQL query concatenation detected.",
        severity=SeverityEnum.CRITICAL,
        confidence=ConfidenceEnum.HIGH,
        evidence=CodeEvidence(
            file_path="src/main.py",
            start_line=5,
            end_line=6,
            code_snippet="db.execute(sql)",
        ),
        remediation=RemediationAdvice(
            explanation="Use query parameters",
            recommended_fix="db.execute('SELECT ?', (arg,))",
        ),
    )


@pytest.mark.asyncio
async def test_empty_chunks_returns_empty_list():
    context = make_dummy_context([])
    orchestrator = ReviewOrchestrator()
    results = await orchestrator.run_review(context)
    assert results == []


@pytest.mark.asyncio
async def test_parallel_dispatch_on_multiple_chunks(sample_finding):
    chunk1 = make_dummy_chunk("chunk-1")
    chunk2 = make_dummy_chunk("chunk-2")
    chunk3 = make_dummy_chunk("chunk-3")
    context = make_dummy_context([chunk1, chunk2, chunk3])

    mock_sec = MagicMock()
    mock_arch = MagicMock()

    async def sec_analyze(chunk: CodeChunk) -> AgentResult:
        return AgentResult(
            agent_role=AgentRoleEnum.SECURITY_AUDITOR,
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            execution_time_ms=10.0,
            success=True,
            findings=[sample_finding],
        )

    async def arch_analyze(chunk: CodeChunk) -> AgentResult:
        return AgentResult(
            agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            execution_time_ms=15.0,
            success=True,
            findings=[],
        )

    mock_sec.analyze_chunk = AsyncMock(side_effect=sec_analyze)
    mock_arch.analyze_chunk = AsyncMock(side_effect=arch_analyze)

    orchestrator = ReviewOrchestrator(
        security_agent=mock_sec,
        architect_agent=mock_arch,
        max_concurrency=4,
        timeout_seconds=5.0,
    )

    results = await orchestrator.run_review(context)

    # 3 chunks * 2 agents = 6 results
    assert len(results) == 6
    assert mock_sec.analyze_chunk.call_count == 3
    assert mock_arch.analyze_chunk.call_count == 3

    sec_results = [r for r in results if r.agent_role == AgentRoleEnum.SECURITY_AUDITOR]
    arch_results = [r for r in results if r.agent_role == AgentRoleEnum.SOFTWARE_ARCHITECT]

    assert len(sec_results) == 3
    assert len(arch_results) == 3
    assert all(r.success for r in results)
    assert all(len(r.findings) == 1 for r in sec_results)


@pytest.mark.asyncio
async def test_concurrency_limiting_with_semaphore():
    chunks = [make_dummy_chunk(f"chunk-{i}") for i in range(6)]
    context = make_dummy_context(chunks)

    current_concurrency = 0
    max_observed_concurrency = 0
    lock = asyncio.Lock()

    mock_sec = MagicMock()
    mock_arch = MagicMock()

    async def slow_sec_analyze(chunk: CodeChunk) -> AgentResult:
        nonlocal current_concurrency, max_observed_concurrency
        async with lock:
            current_concurrency += 1
            if current_concurrency > max_observed_concurrency:
                max_observed_concurrency = current_concurrency

        await asyncio.sleep(0.04)

        async with lock:
            current_concurrency -= 1

        return AgentResult(
            agent_role=AgentRoleEnum.SECURITY_AUDITOR,
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            success=True,
        )

    async def fast_arch_analyze(chunk: CodeChunk) -> AgentResult:
        return AgentResult(
            agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            success=True,
        )

    mock_sec.analyze_chunk = AsyncMock(side_effect=slow_sec_analyze)
    mock_arch.analyze_chunk = AsyncMock(side_effect=fast_arch_analyze)

    orchestrator = ReviewOrchestrator(
        security_agent=mock_sec,
        architect_agent=mock_arch,
        max_concurrency=2,
        timeout_seconds=5.0,
    )

    results = await orchestrator.run_review(context)

    assert len(results) == 12
    # Active chunk analysis tasks constrained by semaphore=2
    assert max_observed_concurrency <= 2


@pytest.mark.asyncio
async def test_timeout_resilience_per_chunk():
    chunk1 = make_dummy_chunk("chunk-timeout")
    context = make_dummy_context([chunk1])

    mock_sec = MagicMock()
    mock_arch = MagicMock()

    async def hanging_sec(chunk: CodeChunk) -> AgentResult:
        await asyncio.sleep(1.0)
        return AgentResult(
            agent_role=AgentRoleEnum.SECURITY_AUDITOR,
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            success=True,
        )

    async def hanging_arch(chunk: CodeChunk) -> AgentResult:
        await asyncio.sleep(1.0)
        return AgentResult(
            agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            success=True,
        )

    mock_sec.analyze_chunk = AsyncMock(side_effect=hanging_sec)
    mock_arch.analyze_chunk = AsyncMock(side_effect=hanging_arch)

    orchestrator = ReviewOrchestrator(
        security_agent=mock_sec,
        architect_agent=mock_arch,
        max_concurrency=2,
        timeout_seconds=0.08,
    )

    results = await orchestrator.run_review(context)

    assert len(results) == 2
    for r in results:
        assert not r.success
        assert "timed out after 0.08s" in r.error_message


@pytest.mark.asyncio
async def test_exception_isolation_between_chunks_and_agents():
    chunk1 = make_dummy_chunk("chunk-failing")
    chunk2 = make_dummy_chunk("chunk-ok")
    context = make_dummy_context([chunk1, chunk2])

    mock_sec = MagicMock()
    mock_arch = MagicMock()

    async def failing_sec_on_chunk1(chunk: CodeChunk) -> AgentResult:
        if chunk.chunk_id == "chunk-failing":
            raise RuntimeError("LLM connection severed")
        return AgentResult(
            agent_role=AgentRoleEnum.SECURITY_AUDITOR,
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            success=True,
        )

    async def always_ok_arch(chunk: CodeChunk) -> AgentResult:
        return AgentResult(
            agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            success=True,
        )

    mock_sec.analyze_chunk = AsyncMock(side_effect=failing_sec_on_chunk1)
    mock_arch.analyze_chunk = AsyncMock(side_effect=always_ok_arch)

    orchestrator = ReviewOrchestrator(
        security_agent=mock_sec,
        architect_agent=mock_arch,
        max_concurrency=2,
        timeout_seconds=5.0,
    )

    results = await orchestrator.run_review(context)

    assert len(results) == 4

    c1_sec = next(r for r in results if r.chunk_id == "chunk-failing" and r.agent_role == AgentRoleEnum.SECURITY_AUDITOR)
    c1_arch = next(r for r in results if r.chunk_id == "chunk-failing" and r.agent_role == AgentRoleEnum.SOFTWARE_ARCHITECT)
    c2_sec = next(r for r in results if r.chunk_id == "chunk-ok" and r.agent_role == AgentRoleEnum.SECURITY_AUDITOR)
    c2_arch = next(r for r in results if r.chunk_id == "chunk-ok" and r.agent_role == AgentRoleEnum.SOFTWARE_ARCHITECT)

    # Chunk 1 security agent failed gracefully
    assert not c1_sec.success
    assert "LLM connection severed" in c1_sec.error_message

    # Chunk 1 architect agent succeeded
    assert c1_arch.success

    # Chunk 2 succeeded for both
    assert c2_sec.success
    assert c2_arch.success


@pytest.mark.asyncio
async def test_progress_callback_synchronous_and_asynchronous():
    chunk1 = make_dummy_chunk("chunk-cb-1")
    chunk2 = make_dummy_chunk("chunk-cb-2")
    context = make_dummy_context([chunk1, chunk2])

    mock_sec = MagicMock()
    mock_arch = MagicMock()
    mock_sec.analyze_chunk = AsyncMock(
        return_value=AgentResult(
            agent_role=AgentRoleEnum.SECURITY_AUDITOR,
            file_path="src/main.py",
            success=True,
        )
    )
    mock_arch.analyze_chunk = AsyncMock(
        return_value=AgentResult(
            agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
            file_path="src/main.py",
            success=True,
        )
    )

    orchestrator = ReviewOrchestrator(
        security_agent=mock_sec,
        architect_agent=mock_arch,
    )

    # Test sync callback with 2 args (chunk, results)
    sync_called = []
    def sync_cb(chunk, results):
        sync_called.append((chunk.chunk_id, len(results)))

    await orchestrator.run_review(context, progress_callback=sync_cb)
    assert len(sync_called) == 2
    assert sync_called[0][1] == 2
    assert sync_called[1][1] == 2

    # Test async callback with 1 arg (chunk)
    async_called = []
    async def async_cb(chunk):
        async_called.append(chunk.chunk_id)

    await orchestrator.run_review(context, progress_callback=async_cb)
    assert len(async_called) == 2

    # Test callback error does not break review execution
    def failing_cb(chunk, results):
        raise ValueError("Callback crash")

    results = await orchestrator.run_review(context, progress_callback=failing_cb)
    assert len(results) == 4
