"""Ingestion module for scanning local workspaces and remote repositories."""

from src.ingestion.local import LocalScanner, is_binary_file, scan_local_directory
from src.ingestion.github import GitHubIngestionService, ingest_github_repo, parse_github_url
from src.ingestion.detector import (
    create_repository_summary,
    detect_repository_languages,
    parse_dependency_manifests,
)

__all__ = [
    "LocalScanner",
    "is_binary_file",
    "scan_local_directory",
    "GitHubIngestionService",
    "ingest_github_repo",
    "parse_github_url",
    "create_repository_summary",
    "detect_repository_languages",
    "parse_dependency_manifests",
]
