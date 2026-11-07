"""FastAPI router for review history persistence and revision comparison."""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.core.models import ConsolidatedReview, ModeratedFinding
from src.storage.history import ReviewHistoryStorage

logger = logging.getLogger("reviewer.api.history")

router = APIRouter(prefix="/api/v1/history", tags=["Review History"])


def get_history_storage() -> ReviewHistoryStorage:
    """Dependency provider for ReviewHistoryStorage."""
    return ReviewHistoryStorage()


class ReviewSummaryItem(BaseModel):
    """Summary metadata record for a historical review scan."""

    review_id: str
    repo_id: str
    created_at: str
    status: str
    total_files: int
    total_chunks: int
    total_findings: int
    severity_distribution: Dict[str, int] = Field(default_factory=dict)
    max_risk_score: float = 0.0


class CompareReviewsRequest(BaseModel):
    """Payload for comparing two review scan reports."""

    base_review_id: str
    target_review_id: str


class CompareSummary(BaseModel):
    """Aggregate numerical metrics comparing base and target reviews."""

    base_review_id: str
    target_review_id: str
    base_total: int
    target_total: int
    new_count: int
    resolved_count: int
    persistent_count: int
    risk_score_delta: float
    critical_delta: int


class CompareReviewsResponse(BaseModel):
    """Categorized finding delta between base and target reviews."""

    base_review_id: str
    target_review_id: str
    base_total: int
    target_total: int
    new_count: int
    resolved_count: int
    persistent_count: int
    risk_score_delta: float
    critical_delta: int
    new_findings: List[ModeratedFinding] = Field(default_factory=list)
    resolved_findings: List[ModeratedFinding] = Field(default_factory=list)
    persistent_findings: List[ModeratedFinding] = Field(default_factory=list)
    summary: CompareSummary


@router.get("", response_model=List[ReviewSummaryItem], summary="List historical review scans")
@router.get("/", response_model=List[ReviewSummaryItem], include_in_schema=False)
def list_history(
    repo_id: Optional[str] = Query(None, description="Filter by repository ID"),
    limit: int = Query(50, ge=1, le=500, description="Maximum entries to return"),
    storage: ReviewHistoryStorage = Depends(get_history_storage),
) -> List[ReviewSummaryItem]:
    """Retrieve chronological list of past review scans with high-level metrics."""
    records = storage.list_reviews(repo_id=repo_id, limit=limit)
    return [ReviewSummaryItem(**item) for item in records]


@router.get(
    "/{review_id}",
    response_model=ConsolidatedReview,
    summary="Get detailed review scan report by ID",
)
def get_review_by_id(
    review_id: str,
    storage: ReviewHistoryStorage = Depends(get_history_storage),
) -> ConsolidatedReview:
    """Fetch complete ConsolidatedReview JSON report by review UUID."""
    review = storage.get_review(review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review '{review_id}' not found in history",
        )
    return review


@router.post(
    "/compare",
    response_model=CompareReviewsResponse,
    summary="Compare two review scans to compute finding differences and risk delta",
)
def compare_reviews_endpoint(
    request: CompareReviewsRequest,
    storage: ReviewHistoryStorage = Depends(get_history_storage),
) -> CompareReviewsResponse:
    """Compute new, resolved, and persistent findings between base and target reviews."""
    try:
        diff = storage.compare_reviews(
            base_review_id=request.base_review_id,
            target_review_id=request.target_review_id,
        )
        return CompareReviewsResponse(**diff)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to compare reviews: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Review comparison failed: {exc}",
        ) from exc


@router.delete(
    "/{review_id}",
    summary="Delete a stored review report from history",
)
def delete_review_endpoint(
    review_id: str,
    storage: ReviewHistoryStorage = Depends(get_history_storage),
) -> Dict[str, str]:
    """Delete a review report from disk and purge its metadata entry."""
    storage.delete_review(review_id)
    return {"status": "deleted", "review_id": review_id}

