"""API endpoints for syntax-aware context preparation and chunking."""

import logging
from fastapi import APIRouter, HTTPException, status

from src.core.models import RepositorySummary, ReviewContext
from src.parser.chunker import ContextPreparationEngine

logger = logging.getLogger("reviewer.api.context")

router = APIRouter(prefix="/api/v1/context", tags=["Context Preparation"])


@router.post(
    "/prepare",
    response_model=ReviewContext,
    status_code=status.HTTP_200_OK,
    summary="Prepare enriched syntax-aware review context from repository summary",
)
async def prepare_context_endpoint(summary: RepositorySummary) -> ReviewContext:
    """Transform repository summary and files into structured ReviewContext with AST chunks."""
    try:
        engine = ContextPreparationEngine()
        review_context = engine.prepare_repository_context(summary)
        return review_context
    except Exception as exc:
        logger.exception("Context preparation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context preparation failed: {exc}",
        ) from exc

