"""Remote GitHub repository ingestion engine with archive streaming and safe extraction."""

import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse
import zipfile

import httpx

from src.core.config import get_settings
from src.core.models import IngestedFile
from src.ingestion.local import LocalScanner

logger = logging.getLogger("reviewer.ingestion.github")


def parse_github_url(url: str) -> Dict[str, Any]:
    """Parse GitHub URL into owner, repo, ref (branch/commit), and PR number.

    Args:
        url: GitHub repository, branch, commit, or pull request URL.

    Returns:
        Dict with keys: owner, repo, ref, pr_number.
    """
    clean_url = url.strip()
    if clean_url.startswith("git@github.com:"):
        path_part = clean_url[len("git@github.com:") :]
        clean_url = f"https://github.com/{path_part}"

    parsed = urlparse(clean_url)
    path = parsed.path.strip("/")
    parts = path.split("/")

    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid GitHub repository URL: {url}")

    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    ref: Optional[str] = None
    pr_number: Optional[int] = None

    if len(parts) >= 4 and parts[2] == "tree":
        ref = "/".join(parts[3:])
    elif len(parts) >= 4 and parts[2] == "commit":
        ref = parts[3]
    elif len(parts) >= 4 and parts[2] == "pull":
        try:
            pr_number = int(parts[3])
        except ValueError:
            pass

    return {
        "owner": owner,
        "repo": repo,
        "ref": ref,
        "pr_number": pr_number,
    }


class GitHubIngestionService:
    """Service to fetch and unpack remote GitHub repositories via zipball archive streaming."""

    def __init__(self, token: Optional[str] = None, timeout: float = 30.0):
        self.settings = get_settings()
        self.token = token or self.settings.github_token
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": "Automated-Code-Vulnerability-Reviewer/1.0",
            "Accept": "application/vnd.github.v3+json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @staticmethod
    def cleanup_temp_dir(path: Union[str, Path]) -> None:
        """Safely remove a temporary extraction directory."""
        try:
            target = Path(path)
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                logger.debug("Cleaned up temp directory: %s", target)
        except Exception as exc:
            logger.warning("Error cleaning up temp directory %s: %s", path, exc)

    @staticmethod
    def _safe_extract_zip(zip_path: Path, extract_to: Path) -> Path:
        """Extract a zip archive safely preventing Zip Slip directory traversal."""
        extract_to_resolved = extract_to.resolve()
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                member_target = (extract_to / member.filename).resolve()
                if not str(member_target).startswith(str(extract_to_resolved)):
                    raise ValueError(f"Zip Slip security vulnerability detected: {member.filename}")
            zf.extractall(extract_to)

        # GitHub archives place content inside a single root directory: {owner}-{repo}-{hash}
        entries = [p for p in extract_to.iterdir() if p.is_dir()]
        return entries[0] if entries else extract_to

    async def ingest(
        self,
        repo_url: str,
        ref: Optional[str] = None,
        pr_number: Optional[int] = None,
        max_file_size: int = 1048576,
    ) -> Tuple[str, List[IngestedFile]]:
        """Fetch remote repository archive and scan files.

        Args:
            repo_url: GitHub repository URL.
            ref: Branch or commit SHA override.
            pr_number: Pull request number override.
            max_file_size: Maximum file size cap in bytes.

        Returns:
            Tuple containing the extracted repository folder path and list of IngestedFiles.
        """
        parsed = parse_github_url(repo_url)
        owner = parsed["owner"]
        repo = parsed["repo"]
        target_ref = ref or parsed["ref"]
        target_pr = pr_number or parsed["pr_number"]

        headers = self._get_headers()

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            # If reviewing a PR, retrieve head commit ref
            if target_pr:
                pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{target_pr}"
                pr_resp = await client.get(pr_url, headers=headers)
                if pr_resp.status_code == 200:
                    pr_data = pr_resp.json()
                    target_ref = pr_data.get("head", {}).get("sha", target_ref)
                    logger.info("Retrieved PR #%d target ref: %s", target_pr, target_ref)
                else:
                    logger.warning("Could not fetch PR #%d details: %d", target_pr, pr_resp.status_code)

            # Determine archive URL
            archive_urls = []
            if target_ref:
                archive_urls.append(f"https://api.github.com/repos/{owner}/{repo}/zipball/{target_ref}")
            else:
                archive_urls.append(f"https://api.github.com/repos/{owner}/{repo}/zipball")
                archive_urls.append(f"https://api.github.com/repos/{owner}/{repo}/zipball/main")
                archive_urls.append(f"https://api.github.com/repos/{owner}/{repo}/zipball/master")

            # Stream download to temporary file
            temp_dir = Path(tempfile.mkdtemp(prefix="gsd_github_"))
            archive_path = temp_dir / "repo_archive.zip"
            extracted_dir = temp_dir / "unpacked"
            extracted_dir.mkdir(parents=True, exist_ok=True)

            download_success = False
            last_status = None

            for url in archive_urls:
                try:
                    async with client.stream("GET", url, headers=headers) as response:
                        last_status = response.status_code
                        if response.status_code == 200:
                            with open(archive_path, "wb") as f:
                                async for chunk in response.aiter_bytes(chunk_size=65536):
                                    f.write(chunk)
                            download_success = True
                            break
                except httpx.HTTPError as exc:
                    logger.debug("Attempt to fetch %s failed: %s", url, exc)

            if not download_success:
                self.cleanup_temp_dir(temp_dir)
                raise RuntimeError(
                    f"Failed to download repository archive from GitHub for {owner}/{repo}. "
                    f"Last HTTP Status: {last_status}"
                )

            # Safe extraction
            root_unpacked_path = self._safe_extract_zip(archive_path, extracted_dir)

            # Local scanning of extracted files
            scanner = LocalScanner(root_unpacked_path, max_file_size=max_file_size)
            files = scanner.scan()

            return str(root_unpacked_path), files


async def ingest_github_repo(
    repo_url: str,
    ref: Optional[str] = None,
    pr_number: Optional[int] = None,
    token: Optional[str] = None,
    max_file_size: int = 1048576,
) -> Tuple[str, List[IngestedFile]]:
    """Convenience helper to ingest remote GitHub repo into IngestedFiles."""
    service = GitHubIngestionService(token=token)
    return await service.ingest(
        repo_url=repo_url,
        ref=ref,
        pr_number=pr_number,
        max_file_size=max_file_size,
    )

