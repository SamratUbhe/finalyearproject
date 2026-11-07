"""Scan execution runner coordinating repository ingestion, AST chunking, multi-agent analysis, and moderation."""

import inspect
import logging
import os
from pathlib import Path
import shutil
from typing import Any, Callable, Dict, List, Optional

from src.core.models import (
    ConsolidatedReview,
    IngestionSourceType,
    RepositorySummary,
)
from src.ingestion.detector import create_repository_summary
from src.ingestion.github import ingest_github_repo
from src.ingestion.local import scan_local_directory
from src.moderator.moderator import ReviewModeratorAgent
from src.orchestrator.runner import ReviewOrchestrator
from src.parser.chunker import ContextPreparationEngine

logger = logging.getLogger("reviewer.cli.runner")


class CLIScanRunner:
    """Coordinates end-to-end repository scan workflows for CLI and programmatic callers."""

    def __init__(
        self,
        orchestrator: Optional[ReviewOrchestrator] = None,
        moderator: Optional[ReviewModeratorAgent] = None,
        context_engine: Optional[ContextPreparationEngine] = None,
    ) -> None:
        """Initialize runner with optional component overrides."""
        self.orchestrator = orchestrator or ReviewOrchestrator()
        self.moderator = moderator or ReviewModeratorAgent()
        self.context_engine = context_engine or ContextPreparationEngine()

    async def run_scan(
        self,
        target: str,
        is_github: bool = False,
        ref: Optional[str] = None,
        token: Optional[str] = None,
        pr_number: Optional[int] = None,
        max_file_size: Optional[int] = None,
        on_progress: Optional[Callable] = None,
        on_stage: Optional[Callable[[str, str], None]] = None,
    ) -> ConsolidatedReview:
        """Execute complete automated code review pipeline.

        Stages:
        1. Ingestion: scan local directory or stream GitHub repository archive.
        2. Context Preparation: parse AST chunks, enrich scopes and token metrics.
        3. Parallel Agent Review: execute Security and Software Architect reviews.
        4. Review Moderation: deduplicate, arbitrate, and compute risk prioritization scores.

        Args:
            target: Local directory path or GitHub repository URL.
            is_github: Whether the target is a remote GitHub repository.
            ref: Git branch, tag, or commit reference for GitHub ingestion.
            token: Optional GitHub personal access token.
            pr_number: Optional pull request number for GitHub ingestion.
            max_file_size: Maximum file size limit in bytes (default: 1MB).
            on_progress: Progress callback hook invoked per chunk analysis.
            on_stage: Callback hook invoked when transitioning pipeline stages.

        Returns:
            Completed ConsolidatedReview report.
        """
        temp_extracted_dir: Optional[Path] = None

        def _notify_stage(stage_name: str, message: str) -> None:
            logger.info("[Scan Stage: %s] %s", stage_name.upper(), message)
            if on_stage:
                try:
                    on_stage(stage_name, message)
                except Exception as exc:
                    logger.debug("on_stage callback exception: %s", exc)

        try:
            # Stage 1: Ingestion
            is_remote_url = (
                is_github
                or target.startswith("http://")
                or target.startswith("https://")
                or target.startswith("git@github.com:")
                or ("github.com" in target and not Path(target).exists())
            )

            if is_remote_url:
                _notify_stage("ingestion", f"Downloading and ingesting remote repository: {target}...")
                github_token = token or os.getenv("GITHUB_TOKEN")
                root_path, files = await ingest_github_repo(
                    repo_url=target,
                    ref=ref,
                    pr_number=pr_number,
                    token=github_token,
                    max_file_size=max_file_size or 1048576,
                )

                # Locate enclosing temp directory created by GitHubIngestionService for cleanup
                p = Path(root_path).resolve()
                while p != p.parent:
                    if "gsd_github_" in p.name:
                        temp_extracted_dir = p
                        break
                    p = p.parent

                summary = create_repository_summary(
                    source_type=IngestionSourceType.github,
                    source_path_or_url=target,
                    files=files,
                    base_path=root_path,
                )
            else:
                target_path = Path(target).resolve()
                if not target_path.exists():
                    raise FileNotFoundError(f"Local target path does not exist: {target}")
                if not target_path.is_dir():
                    raise ValueError(f"Local target path is not a directory: {target}")

                _notify_stage("ingestion", f"Scanning local directory {target_path}...")
                files = scan_local_directory(
                    path=target_path,
                    max_file_size=max_file_size or 1048576,
                )
                summary = create_repository_summary(
                    source_type=IngestionSourceType.local,
                    source_path_or_url=str(target_path),
                    files=files,
                    base_path=target_path,
                )

            # Stage 2: Context Preparation
            _notify_stage("context", f"Extracting AST chunks across {len(summary.files)} files...")
            context = self.context_engine.prepare_repository_context(summary)

            # Stage 3: Multi-Agent Parallel Review
            _notify_stage(
                "analysis",
                f"Analyzing {context.total_chunks} code chunks with Security & Architect agents...",
            )

            chunk_counter = 0
            async def _chunk_callback(chunk: Any, results: Optional[Any] = None) -> None:
                nonlocal chunk_counter
                chunk_counter += 1
                findings_count = sum(len(r.findings) for r in results if getattr(r, "success", False)) if results else 0
                logger.info(
                    "  ↳ [%d/%d] Chunk reviewed: %s (Findings: %d)",
                    chunk_counter,
                    context.total_chunks,
                    getattr(chunk, "name", "chunk"),
                    findings_count,
                )
                if on_progress:
                    try:
                        if inspect.iscoroutinefunction(on_progress):
                            try:
                                await on_progress(chunk, results)
                            except TypeError:
                                await on_progress(chunk)
                        else:
                            try:
                                on_progress(chunk, results)
                            except TypeError:
                                on_progress(chunk)
                    except Exception as err:
                        logger.debug("Progress callback exception: %s", err)

            agent_results = await self.orchestrator.run_review(
                context=context,
                progress_callback=_chunk_callback,
            )

            # Stage 4: Review Moderation & Risk Scoring
            _notify_stage("moderation", "Moderating findings, resolving conflicts, and computing risk scores...")
            consolidated_review = self.moderator.moderate_review(
                repo_id=context.repo_id,
                agent_results=agent_results,
                total_files=len(summary.files),
                total_chunks=context.total_chunks,
            )

            return consolidated_review

        finally:
            if temp_extracted_dir and temp_extracted_dir.exists():
                try:
                    shutil.rmtree(temp_extracted_dir, ignore_errors=True)
                except Exception as exc:
                    logger.debug("Failed to clean up temp dir %s: %s", temp_extracted_dir, exc)

