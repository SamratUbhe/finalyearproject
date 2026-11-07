"""Parallel asynchronous review orchestrator managing concurrent multi-agent executions."""

import asyncio
import inspect
import logging
import time
from typing import Callable, List, Optional

from src.agents.architect_agent import SoftwareArchitectAgent
from src.agents.security_agent import SecurityAuditorAgent
from src.core.config import get_settings
from src.core.models import AgentResult, AgentRoleEnum, CodeChunk, ReviewContext

logger = logging.getLogger(__name__)


class ReviewOrchestrator:
    """Coordinates asynchronous parallel review execution between specialized agents across code chunks."""

    def __init__(
        self,
        security_agent: Optional[SecurityAuditorAgent] = None,
        architect_agent: Optional[SoftwareArchitectAgent] = None,
        max_concurrency: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        settings = get_settings()
        self.security_agent = security_agent or SecurityAuditorAgent()
        self.architect_agent = architect_agent or SoftwareArchitectAgent()
        self.max_concurrency = (
            max_concurrency
            if max_concurrency is not None
            else settings.agent_max_concurrency
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.agent_timeout_seconds
        )

    async def analyze_chunk_with_agents(
        self,
        chunk: CodeChunk,
        semaphore: asyncio.Semaphore,
        progress_callback: Optional[Callable] = None,
    ) -> List[AgentResult]:
        """Execute both Security and Architect agent reviews concurrently on a single code chunk with semaphore & timeout protection."""
        async with semaphore:
            start_time = time.perf_counter()
            try:
                task_sec = self.security_agent.analyze_chunk(chunk)
                task_arch = self.architect_agent.analyze_chunk(chunk)

                raw_results = await asyncio.wait_for(
                    asyncio.gather(task_sec, task_arch, return_exceptions=True),
                    timeout=self.timeout_seconds,
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                results: List[AgentResult] = []
                for res, role in zip(
                    raw_results,
                    [AgentRoleEnum.SECURITY_AUDITOR, AgentRoleEnum.SOFTWARE_ARCHITECT],
                ):
                    if isinstance(res, Exception):
                        results.append(
                            AgentResult(
                                agent_role=role,
                                chunk_id=chunk.chunk_id,
                                file_path=chunk.file_path,
                                execution_time_ms=elapsed_ms,
                                success=False,
                                error_message=str(res),
                                findings=[],
                            )
                        )
                    elif isinstance(res, AgentResult):
                        results.append(res)
                    else:
                        results.append(
                            AgentResult(
                                agent_role=role,
                                chunk_id=chunk.chunk_id,
                                file_path=chunk.file_path,
                                execution_time_ms=elapsed_ms,
                                success=False,
                                error_message=f"Unexpected agent response type: {type(res)}",
                                findings=[],
                            )
                        )

            except asyncio.TimeoutError:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                timeout_msg = f"Chunk analysis timed out after {self.timeout_seconds}s"
                logger.warning(
                    "Chunk %s analysis timed out after %ss",
                    chunk.chunk_id,
                    self.timeout_seconds,
                )
                results = [
                    AgentResult(
                        agent_role=AgentRoleEnum.SECURITY_AUDITOR,
                        chunk_id=chunk.chunk_id,
                        file_path=chunk.file_path,
                        execution_time_ms=elapsed_ms,
                        success=False,
                        error_message=timeout_msg,
                        findings=[],
                    ),
                    AgentResult(
                        agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT,
                        chunk_id=chunk.chunk_id,
                        file_path=chunk.file_path,
                        execution_time_ms=elapsed_ms,
                        success=False,
                        error_message=timeout_msg,
                        findings=[],
                    ),
                ]

            if progress_callback:
                try:
                    if inspect.iscoroutinefunction(progress_callback):
                        try:
                            await progress_callback(chunk, results)
                        except TypeError:
                            await progress_callback(chunk)
                    else:
                        try:
                            progress_callback(chunk, results)
                        except TypeError:
                            progress_callback(chunk)
                except Exception as cb_err:
                    logger.warning(
                        "Progress callback error for chunk %s: %s",
                        chunk.chunk_id,
                        cb_err,
                    )

            return results

    async def run_review(
        self,
        context: ReviewContext,
        progress_callback: Optional[Callable] = None,
    ) -> List[AgentResult]:
        """Run asynchronous parallel review across all code chunks in the ReviewContext."""
        if not context.chunks:
            return []

        logger.info("Starting review on %d code chunks with concurrency=%d...", len(context.chunks), self.max_concurrency)

        semaphore = asyncio.Semaphore(self.max_concurrency)
        tasks = [
            self.analyze_chunk_with_agents(chunk, semaphore, progress_callback)
            for chunk in context.chunks
        ]

        nested_results = await asyncio.gather(*tasks, return_exceptions=True)

        flattened_results: List[AgentResult] = []
        for item in nested_results:
            if isinstance(item, Exception):
                logger.error("Unhandled exception in chunk review task: %s", item)
            elif isinstance(item, list):
                flattened_results.extend(item)

        return flattened_results
