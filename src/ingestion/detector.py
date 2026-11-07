"""Language detection and dependency manifest parsing for code repositories."""

import json
import logging
from pathlib import Path
import re
import tomllib
from typing import Dict, List, Optional, Union

from src.core.models import (
    DependencyManifest,
    IngestedFile,
    IngestionSourceType,
    LanguageEnum,
    RepositorySummary,
)

logger = logging.getLogger("reviewer.ingestion.detector")

REQ_LINE_PATTERN = re.compile(r"^([a-zA-Z0-9_\-\.]+)\s*([=><~!^]=?\s*[^#\s]+)?")


def detect_repository_languages(files: List[IngestedFile]) -> Dict[str, int]:
    """Calculate line count distribution across recognized programming languages.

    Args:
        files: List of ingested repository files.

    Returns:
        Mapping of language name to total code lines.
    """
    distribution: Dict[str, int] = {}
    for file in files:
        if file.language != LanguageEnum.unknown:
            lang_key = file.language.value
            distribution[lang_key] = distribution.get(lang_key, 0) + file.line_count
    return distribution


def _parse_requirements_content(content: str) -> Dict[str, str]:
    """Parse pip requirements.txt content into name -> version specification."""
    deps: Dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-", "--")):
            continue
        # Strip inline comments
        if " #" in line:
            line = line.split(" #", 1)[0].strip()

        match = REQ_LINE_PATTERN.match(line)
        if match:
            pkg_name = match.group(1).lower()
            pkg_version = match.group(2).strip() if match.group(2) else "*"
            deps[pkg_name] = pkg_version
    return deps


def _parse_pyproject_content(content: str) -> Dict[str, str]:
    """Parse pyproject.toml dependencies (PEP 621 and Poetry)."""
    deps: Dict[str, str] = {}
    try:
        data = tomllib.loads(content)
    except Exception as exc:
        logger.warning("Failed to parse pyproject.toml: %s", exc)
        return deps

    # PEP 621 dependencies
    project_deps = data.get("project", {}).get("dependencies", [])
    if isinstance(project_deps, list):
        for item in project_deps:
            if isinstance(item, str):
                match = REQ_LINE_PATTERN.match(item.strip())
                if match:
                    pkg_name = match.group(1).lower()
                    pkg_version = match.group(2).strip() if match.group(2) else "*"
                    deps[pkg_name] = pkg_version

    # Poetry dependencies
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    if isinstance(poetry_deps, dict):
        for pkg, spec in poetry_deps.items():
            if pkg.lower() == "python":
                continue
            if isinstance(spec, str):
                deps[pkg.lower()] = spec
            elif isinstance(spec, dict) and "version" in spec:
                deps[pkg.lower()] = str(spec["version"])
            else:
                deps[pkg.lower()] = "*"

    return deps


def _parse_package_json_content(content: str) -> Dict[str, str]:
    """Parse Node package.json dependencies and devDependencies."""
    deps: Dict[str, str] = {}
    try:
        data = json.loads(content)
    except Exception as exc:
        logger.warning("Failed to parse package.json: %s", exc)
        return deps

    for section in ("dependencies", "devDependencies"):
        section_data = data.get(section, {})
        if isinstance(section_data, dict):
            for pkg, ver in section_data.items():
                deps[pkg] = str(ver)

    return deps


def parse_dependency_manifests(
    base_path: Union[Path, str],
    files: List[IngestedFile],
) -> List[DependencyManifest]:
    """Detect and parse dependency manifests across the repository.

    Args:
        base_path: Root repository directory.
        files: Ingested file list.

    Returns:
        List of parsed DependencyManifest objects.
    """
    manifests: List[DependencyManifest] = []

    # Map file relative path to content from already ingested files
    file_map: Dict[str, str] = {f.relative_path: f.content for f in files}

    # Also scan base_path directory for manifest files that might not have been matched
    manifest_candidates = [
        ("requirements.txt", "pip", _parse_requirements_content),
        ("package.json", "npm", _parse_package_json_content),
        ("pyproject.toml", "poetry_pep621", _parse_pyproject_content),
    ]

    base = Path(base_path) if isinstance(base_path, (str, Path)) else None

    # First check ingested files
    for rel_path, content in file_map.items():
        filename = Path(rel_path).name.lower()
        if "requirements" in filename and filename.endswith((".txt", ".in")):
            deps = _parse_requirements_content(content)
            if deps:
                manifests.append(
                    DependencyManifest(
                        manifest_path=rel_path,
                        manifest_type="pip",
                        dependencies=deps,
                    )
                )
        elif filename == "package.json":
            deps = _parse_package_json_content(content)
            if deps:
                manifests.append(
                    DependencyManifest(
                        manifest_path=rel_path,
                        manifest_type="npm",
                        dependencies=deps,
                    )
                )
        elif filename == "pyproject.toml":
            deps = _parse_pyproject_content(content)
            if deps:
                manifests.append(
                    DependencyManifest(
                        manifest_path=rel_path,
                        manifest_type="poetry_pep621",
                        dependencies=deps,
                    )
                )

    # If base path exists on disk and manifests are still empty, try reading directly from root
    if not manifests and base and base.exists() and base.is_dir():
        for filename, m_type, parser in manifest_candidates:
            target_file = base / filename
            if target_file.is_file():
                try:
                    content = target_file.read_text(encoding="utf-8", errors="ignore")
                    deps = parser(content)
                    if deps:
                        manifests.append(
                            DependencyManifest(
                                manifest_path=filename,
                                manifest_type=m_type,
                                dependencies=deps,
                            )
                        )
                except Exception as exc:
                    logger.warning("Error reading manifest %s: %s", target_file, exc)

    return manifests


def create_repository_summary(
    source_type: IngestionSourceType,
    source_path_or_url: str,
    files: List[IngestedFile],
    base_path: Optional[Union[Path, str]] = None,
) -> RepositorySummary:
    """Consolidate files, language metrics, and dependencies into a RepositorySummary."""
    total_files = len(files)
    total_lines = sum(f.line_count for f in files)
    languages = detect_repository_languages(files)
    manifest_base = base_path if base_path is not None else source_path_or_url
    manifests = parse_dependency_manifests(manifest_base, files)

    return RepositorySummary(
        source_type=source_type,
        source_path_or_url=str(source_path_or_url),
        total_files=total_files,
        total_lines=total_lines,
        languages=languages,
        manifests=manifests,
        files=files,
    )

