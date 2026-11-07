"""FastAPI router for generating and exporting audit reports."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from src.core.models import ConsolidatedReview
from src.reports.html_generator import HTMLReportGenerator
from src.storage.history import ReviewHistoryStorage

logger = logging.getLogger("reviewer.api.reports")

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


def get_history_storage() -> ReviewHistoryStorage:
    """Dependency provider for ReviewHistoryStorage."""
    return ReviewHistoryStorage()


@router.get("/html/{review_id}", response_class=HTMLResponse)
async def get_html_report(
    review_id: str,
    download: bool = Query(
        default=False,
        description="Whether to trigger file download attachment disposition",
    ),
    storage: ReviewHistoryStorage = Depends(get_history_storage),
) -> HTMLResponse:
    """Retrieve and render the standalone HTML report for a historical review scan.

    Args:
        review_id: Identifier of the review scan.
        download: If True, sets Content-Disposition to attachment to trigger download.
        storage: Review history storage dependency.

    Returns:
        HTMLResponse containing standalone, self-contained HTML report.
    """
    review = storage.get_review(review_id)
    if not review:
        logger.warning("Report request failed: review '%s' not found", review_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review '{review_id}' not found in storage.",
        )

    try:
        generator = HTMLReportGenerator()
        html_content = generator.generate(review)
    except Exception as exc:
        logger.error("Failed to generate HTML report for review '%s': %s", review_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate HTML report: {exc}",
        )

    disposition = "attachment" if download else "inline"
    filename = f"review-{review_id}.html"

    return HTMLResponse(
        content=html_content,
        status_code=status.HTTP_200_OK,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )

