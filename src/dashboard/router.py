"""FastAPI router for Local Web Dashboard serving and scan execution."""

import logging
from pathlib import Path
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.cli.runner import CLIScanRunner
from src.core.models import ConsolidatedReview
from src.storage.history import ReviewHistoryStorage

logger = logging.getLogger("reviewer.dashboard")

router = APIRouter(tags=["Dashboard"])

STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"


def get_scan_runner() -> CLIScanRunner:
    """Dependency provider for CLIScanRunner."""
    return CLIScanRunner()


def get_history_storage() -> ReviewHistoryStorage:
    """Dependency provider for ReviewHistoryStorage."""
    return ReviewHistoryStorage()


class DashboardScanRequest(BaseModel):
    """Payload for starting a vulnerability scan from the dashboard."""

    source_type: str = Field(default="local", description="'local' or 'github'")
    path_or_url: str = Field(..., description="Local folder path or GitHub repository URL")
    ref: Optional[str] = Field(default=None, description="Branch, tag, or commit reference")
    token: Optional[str] = Field(default=None, description="Optional GitHub personal access token")
    pr_number: Optional[int] = Field(default=None, description="Optional pull request number")


@router.get("/dashboard", response_class=FileResponse, summary="Serve Web Dashboard single-page application")
async def get_dashboard() -> FileResponse:
    """Serve the single-page dashboard HTML interface."""
    if not INDEX_HTML.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard index.html not found.",
        )
    return FileResponse(str(INDEX_HTML), media_type="text/html")


@router.post(
    "/api/v1/dashboard/scan",
    response_model=ConsolidatedReview,
    status_code=status.HTTP_200_OK,
    summary="Execute code vulnerability review from Web Dashboard",
)
async def run_dashboard_scan(
    request: DashboardScanRequest,
    runner: CLIScanRunner = Depends(get_scan_runner),
    storage: ReviewHistoryStorage = Depends(get_history_storage),
) -> ConsolidatedReview:
    """Execute end-to-end multi-agent scan on specified repository target and persist report."""
    from src.core.config import get_settings, reload_settings
    if not get_settings().gemini_api_key:
        reload_settings()

    target = request.path_or_url.strip() if request.path_or_url else ""
    if not target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository path or URL must not be empty.",
        )

    is_github = request.source_type.lower() == "github"

    # Local path validation
    if not is_github and not (target.startswith("http://") or target.startswith("https://")):
        local_p = Path(target)
        if not local_p.exists() or not local_p.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Local target path does not exist or is not a directory: '{target}'",
            )

    try:
        review = await runner.run_scan(
            target=target,
            is_github=is_github,
            ref=request.ref,
            token=request.token,
            pr_number=request.pr_number,
        )

        try:
            storage.save_review(review)
        except Exception as save_err:
            logger.warning("Failed to persist dashboard review to history: %s", save_err)

        return review
    except HTTPException:
        raise
    except FileNotFoundError as fnf_err:
        logger.error("Scan target not found: %s", fnf_err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(fnf_err),
        )
    except ValueError as val_err:
        logger.error("Invalid scan arguments: %s", val_err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.exception("Dashboard scan failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vulnerability review scan failed: {str(exc)}",
        )

