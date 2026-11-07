"""API endpoints for repository ingestion (local workspaces and GitHub)."""

import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, status

from src.core.models import (
    GitHubIngestRequest,
    IngestionSourceType,
    LocalIngestRequest,
    RepositorySummary,
)
from src.ingestion.detector import create_repository_summary
from src.ingestion.github import GitHubIngestionService, ingest_github_repo
from src.ingestion.local import scan_local_directory

logger = logging.getLogger("reviewer.api.ingest")

router = APIRouter(prefix="/api/v1/ingest", tags=["Ingestion"])


@router.post(
    "/local",
    response_model=RepositorySummary,
    status_code=status.HTTP_200_OK,
    summary="Ingest local repository directory",
)
async def ingest_local_endpoint(request: LocalIngestRequest) -> RepositorySummary:
    """Scan local directory path, filtering ignored files and extracting metadata."""
    try:
        files = scan_local_directory(
            path=request.path,
            max_file_size=request.max_file_size,
            extra_ignores=request.extra_ignores,
        )
        return create_repository_summary(
            source_type=IngestionSourceType.local,
            source_path_or_url=request.path,
            files=files,
            base_path=request.path,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error during local ingestion: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Local ingestion failed: {exc}",
        ) from exc


@router.post(
    "/github",
    response_model=RepositorySummary,
    status_code=status.HTTP_200_OK,
    summary="Ingest remote GitHub repository",
)
async def ingest_github_endpoint(request: GitHubIngestRequest) -> RepositorySummary:
    """Download remote GitHub archive stream and extract repository files."""
    extracted_path = None
    try:
        extracted_path, files = await ingest_github_repo(
            repo_url=request.repo_url,
            ref=request.ref,
            pr_number=request.pr_number,
            token=request.token,
            max_file_size=request.max_file_size,
        )
        summary = create_repository_summary(
            source_type=IngestionSourceType.github,
            source_path_or_url=request.repo_url,
            files=files,
            base_path=extracted_path,
        )
        return summary
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error during GitHub ingestion: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"GitHub ingestion failed: {exc}",
        ) from exc
    finally:
        if extracted_path:
            # Clean up the parent temporary directory
            parent_temp = Path(extracted_path).parent
            GitHubIngestionService.cleanup_temp_dir(parent_temp)

