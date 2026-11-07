"""Local directory traversal scanner with path filtering, gitignore support, and file safety checks."""

import logging
import os
from pathlib import Path
from typing import List, Optional, Set, Union

import pathspec

from src.core.models import IngestedFile, LanguageEnum

logger = logging.getLogger("reviewer.ingestion.local")

DEFAULT_IGNORE_DIRS: Set[str] = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".idea",
    ".vscode",
}

DEFAULT_BINARY_EXTENSIONS: Set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".lock",
}

LANGUAGE_EXTENSION_MAP = {
    ".py": LanguageEnum.python,
    ".js": LanguageEnum.javascript,
    ".jsx": LanguageEnum.javascript,
    ".mjs": LanguageEnum.javascript,
    ".cjs": LanguageEnum.javascript,
    ".ts": LanguageEnum.typescript,
    ".tsx": LanguageEnum.typescript,
    ".mts": LanguageEnum.typescript,
    ".cts": LanguageEnum.typescript,
}


def is_binary_file(file_path: Union[str, Path]) -> bool:
    """Check if a file is binary using its extension and first 1024 bytes for null bytes.

    Args:
        file_path: Absolute or relative Path to inspect.

    Returns:
        True if the file is determined to be binary, False otherwise.
    """
    path = Path(file_path)
    if path.suffix.lower() in DEFAULT_BINARY_EXTENSIONS:
        return True

    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
    except (OSError, IOError) as exc:
        logger.debug("Failed to read header bytes for %s: %s", path, exc)
        return True

    return False


class LocalScanner:
    """Traverses local directories safely, respecting ignore rules and size limits."""

    def __init__(
        self,
        base_path: Union[str, Path],
        max_file_size: int = 1048576,  # 1 MB default
        extra_ignores: Optional[List[str]] = None,
    ):
        self.base_path = Path(base_path).resolve()
        if not self.base_path.exists():
            raise FileNotFoundError(f"Target directory does not exist: {self.base_path}")
        if not self.base_path.is_dir():
            raise ValueError(f"Target path is not a directory: {self.base_path}")

        self.max_file_size = max_file_size
        self.extra_ignores = extra_ignores or []

        patterns: List[str] = []
        for d in DEFAULT_IGNORE_DIRS:
            patterns.append(f"{d}/")
            patterns.append(f"**/{d}/**")

        gitignore_path = self.base_path / ".gitignore"
        if gitignore_path.is_file():
            try:
                with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                    patterns.extend(f.readlines())
            except OSError as exc:
                logger.warning("Could not read .gitignore at %s: %s", gitignore_path, exc)

        patterns.extend(self.extra_ignores)
        self.spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def is_ignored(self, rel_path_str: str, is_dir: bool = False) -> bool:
        """Check if relative path matches ignore patterns."""
        normalized = rel_path_str.replace("\\", "/")
        if is_dir and not normalized.endswith("/"):
            normalized += "/"
        return self.spec.match_file(normalized)

    def scan(self) -> List[IngestedFile]:
        """Traverse directory and return list of valid IngestedFile objects."""
        ingested_files: List[IngestedFile] = []

        for root, dirs, files in os.walk(self.base_path):
            current_dir = Path(root)

            # Compute relative path from base_path
            try:
                rel_dir = current_dir.relative_to(self.base_path)
            except ValueError:
                continue

            # In-place modify dirs to avoid traversing into ignored directories
            filtered_dirs = []
            for d in dirs:
                if d in DEFAULT_IGNORE_DIRS:
                    continue
                rel_d_path = (rel_dir / d).as_posix()
                if self.is_ignored(rel_d_path, is_dir=True):
                    continue
                filtered_dirs.append(d)
            dirs[:] = filtered_dirs

            # Process files
            for file_name in files:
                file_path = current_dir / file_name
                rel_file_path = (rel_dir / file_name).as_posix()

                # Filter by ignore patterns
                if self.is_ignored(rel_file_path, is_dir=False):
                    continue

                # Check file size
                try:
                    stat = file_path.stat()
                except OSError:
                    continue

                if stat.st_size > self.max_file_size:
                    logger.debug("Skipping %s due to size cap (%d bytes)", rel_file_path, stat.st_size)
                    continue

                # Check binary file
                if is_binary_file(file_path):
                    continue

                # Read text content
                try:
                    content = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    try:
                        content = file_path.read_text(encoding="latin-1")
                    except Exception as exc:
                        logger.warning("Failed to decode text file %s: %s", rel_file_path, exc)
                        continue
                except OSError as exc:
                    logger.warning("Could not read file %s: %s", rel_file_path, exc)
                    continue

                ext = file_path.suffix.lower()
                language = LANGUAGE_EXTENSION_MAP.get(ext, LanguageEnum.unknown)
                line_count = len(content.splitlines())

                ingested_files.append(
                    IngestedFile(
                        file_path=str(file_path.resolve()),
                        relative_path=rel_file_path,
                        language=language,
                        content=content,
                        line_count=line_count,
                        size_bytes=stat.st_size,
                    )
                )

        return ingested_files


def scan_local_directory(
    path: Union[str, Path],
    max_file_size: int = 1048576,
    extra_ignores: Optional[List[str]] = None,
) -> List[IngestedFile]:
    """Convenience helper to scan a local directory and return IngestedFiles."""
    scanner = LocalScanner(path, max_file_size=max_file_size, extra_ignores=extra_ignores)
    return scanner.scan()

