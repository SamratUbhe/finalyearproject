"""API endpoints for multi-agent code vulnerability review and moderation."""

import logging
from typing import List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.core.models import (
    AgentResult,
    ConsolidatedReview,
    ReviewContext,
)
from src.moderator.moderator import ReviewModeratorAgent
from src.orchestrator.runner import ReviewOrchestrator
from src.storage.history import ReviewHistoryStorage

logger = logging.getLogger("reviewer.api.review")

router = APIRouter(prefix="/api/v1/review", tags=["Review & Moderation"])


class ModerationRequest(BaseModel):
    """Request payload for moderating a collection of agent results."""

    repo_id: str
    agent_results: List[AgentResult] = Field(default_factory=list)
    total_files: int = 0
    total_chunks: int = 0


@router.post(
    "/run",
    response_model=ConsolidatedReview,
    status_code=status.HTTP_200_OK,
    summary="Run full parallel multi-agent review and moderation pipeline",
)
async def run_review_endpoint(context: ReviewContext) -> ConsolidatedReview:
    """Execute Security and Architect agents across all code chunks and moderate findings."""
    try:
        orchestrator = ReviewOrchestrator()
        moderator = ReviewModeratorAgent()

        agent_results = await orchestrator.run_review(context)
        total_files = (
            len(context.summary.files)
            if context.summary and context.summary.files
            else 0
        )
        total_chunks = context.total_chunks or len(context.chunks)

        review = moderator.moderate_review(
            repo_id=context.repo_id,
            agent_results=agent_results,
            total_files=total_files,
            total_chunks=total_chunks,
        )

        try:
            storage = ReviewHistoryStorage()
            storage.save_review(review)
            logger.info("Automatically saved review %s to history", review.review_id)
        except Exception as save_err:
            logger.warning("Failed to auto-save review %s to history: %s", review.review_id, save_err)

        return review
    except Exception as exc:
        logger.exception("Full review pipeline execution failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Review pipeline execution failed: {exc}",
        ) from exc


@router.post(
    "/moderate",
    response_model=ConsolidatedReview,
    status_code=status.HTTP_200_OK,
    summary="Moderate and prioritize pre-computed agent results",
)
async def moderate_review_endpoint(request: ModerationRequest) -> ConsolidatedReview:
    """Deduplicate, arbitrate, and prioritize a pre-computed collection of agent results."""
    try:
        moderator = ReviewModeratorAgent()
        review = moderator.moderate_review(
            repo_id=request.repo_id,
            agent_results=request.agent_results,
            total_files=request.total_files,
            total_chunks=request.total_chunks,
        )
        return review
    except Exception as exc:
        logger.exception("Moderation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Moderation failed: {exc}",
        ) from exc

