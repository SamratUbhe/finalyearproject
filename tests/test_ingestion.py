"""Unit and integration tests for repository ingestion, language detection, and manifest parsing."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.routes.ingest import router
from src.core.models import IngestedFile, IngestionSourceType, LanguageEnum
from src.ingestion.detector import (
    create_repository_summary,
    detect_repository_languages,
    parse_dependency_manifests,
)
from src.ingestion.github import parse_github_url
from src.ingestion.local import LocalScanner, is_binary_file, scan_local_directory
from src.main import app


def test_is_binary_file(tmp_path: Path):
    text_file = tmp_path / "normal.txt"
    text_file.write_text("Hello world", encoding="utf-8")
    assert not is_binary_file(text_file)

    binary_ext = tmp_path / "pic.png"
    binary_ext.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert is_binary_file(binary_ext)

    null_byte_file = tmp_path / "custom.dat"
    null_byte_file.write_bytes(b"Header\x00BinaryData")
    assert is_binary_file(null_byte_file)


def test_local_scanner_traversal_and_filtering(tmp_path: Path):
    # Setup files and directories
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    (src_dir / "index.js").write_text("console.log('hello');\n", encoding="utf-8")
    (src_dir / "types.ts").write_text("export interface User { id: string; }\n", encoding="utf-8")

    # Ignored directory
    nm_dir = tmp_path / "node_modules"
    nm_dir.mkdir()
    (nm_dir / "bad.js").write_text("should be ignored", encoding="utf-8")

    # Binary file
    (tmp_path / "image.png").write_bytes(b"\x89PNG\x00")

    # Size cap file (> 100 bytes)
    large_file = tmp_path / "large.py"
    large_file.write_text("x" * 500, encoding="utf-8")

    # .gitignore
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("custom_ignore.py\n", encoding="utf-8")
    (tmp_path / "custom_ignore.py").write_text("ignored = True", encoding="utf-8")

    # Scan with 100-byte max file size
    scanner = LocalScanner(tmp_path, max_file_size=100)
    files = scanner.scan()

    relative_paths = {f.relative_path for f in files}
    assert "src/app.py" in relative_paths
    assert "src/index.js" in relative_paths
    assert "src/types.ts" in relative_paths

    # Exclusions
    assert not any("node_modules" in p for p in relative_paths)
    assert not any("image.png" in p for p in relative_paths)
    assert not any("large.py" in p for p in relative_paths)
    assert not any("custom_ignore.py" in p for p in relative_paths)

    # Check language detection
    py_file = next(f for f in files if f.relative_path == "src/app.py")
    assert py_file.language == LanguageEnum.python
    assert py_file.line_count == 2

    js_file = next(f for f in files if f.relative_path == "src/index.js")
    assert js_file.language == LanguageEnum.javascript

    ts_file = next(f for f in files if f.relative_path == "src/types.ts")
    assert ts_file.language == LanguageEnum.typescript


def test_parse_github_url():
    # Root repo
    res1 = parse_github_url("https://github.com/tiangolo/fastapi")
    assert res1["owner"] == "tiangolo"
    assert res1["repo"] == "fastapi"
    assert res1["ref"] is None
    assert res1["pr_number"] is None

    # Repo with .git suffix
    res2 = parse_github_url("https://github.com/tiangolo/fastapi.git")
    assert res2["repo"] == "fastapi"

    # SSH format
    res3 = parse_github_url("git@github.com:tiangolo/fastapi.git")
    assert res3["owner"] == "tiangolo"
    assert res3["repo"] == "fastapi"

    # Branch / tree ref
    res4 = parse_github_url("https://github.com/tiangolo/fastapi/tree/feature/v2")
    assert res4["ref"] == "feature/v2"

    # Commit ref
    res5 = parse_github_url("https://github.com/tiangolo/fastapi/commit/abc1234567")
    assert res5["ref"] == "abc1234567"

    # Pull Request
    res6 = parse_github_url("https://github.com/tiangolo/fastapi/pull/42")
    assert res6["pr_number"] == 42

    # Invalid URL
    with pytest.raises(ValueError):
        parse_github_url("https://github.com")


def test_parse_dependency_manifests(tmp_path: Path):
    req_content = """# Core deps
fastapi>=0.110.0
uvicorn==0.28.0 # web server
pydantic~=2.6.0
-r other.txt
"""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(req_content, encoding="utf-8")

    pkg_content = """{
  "name": "sample-pkg",
  "dependencies": {
    "express": "^4.18.2"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}"""
    pkg_file = tmp_path / "package.json"
    pkg_file.write_text(pkg_content, encoding="utf-8")

    pyproj_content = """[project]
dependencies = [
    "httpx>=0.27.0",
    "pytest>=8.0.0"
]
"""
    pyproj_file = tmp_path / "pyproject.toml"
    pyproj_file.write_text(pyproj_content, encoding="utf-8")

    files = [
        IngestedFile(
            file_path=str(req_file),
            relative_path="requirements.txt",
            language=LanguageEnum.unknown,
            content=req_content,
            line_count=5,
            size_bytes=len(req_content),
        ),
        IngestedFile(
            file_path=str(pkg_file),
            relative_path="package.json",
            language=LanguageEnum.unknown,
            content=pkg_content,
            line_count=10,
            size_bytes=len(pkg_content),
        ),
        IngestedFile(
            file_path=str(pyproj_file),
            relative_path="pyproject.toml",
            language=LanguageEnum.unknown,
            content=pyproj_content,
            line_count=6,
            size_bytes=len(pyproj_content),
        ),
    ]

    manifests = parse_dependency_manifests(tmp_path, files)
    manifest_dict = {m.manifest_path: m for m in manifests}

    assert "requirements.txt" in manifest_dict
    pip_deps = manifest_dict["requirements.txt"].dependencies
    assert pip_deps["fastapi"] == ">=0.110.0"
    assert pip_deps["uvicorn"] == "==0.28.0"
    assert pip_deps["pydantic"] == "~=2.6.0"

    assert "package.json" in manifest_dict
    npm_deps = manifest_dict["package.json"].dependencies
    assert npm_deps["express"] == "^4.18.2"
    assert npm_deps["typescript"] == "^5.0.0"

    assert "pyproject.toml" in manifest_dict
    toml_deps = manifest_dict["pyproject.toml"].dependencies
    assert toml_deps["httpx"] == ">=0.27.0"
    assert toml_deps["pytest"] == ">=8.0.0"


def test_create_repository_summary(tmp_path: Path):
    f1 = IngestedFile(
        file_path=str(tmp_path / "a.py"),
        relative_path="a.py",
        language=LanguageEnum.python,
        content="print('a')",
        line_count=1,
        size_bytes=10,
    )
    f2 = IngestedFile(
        file_path=str(tmp_path / "b.ts"),
        relative_path="b.ts",
        language=LanguageEnum.typescript,
        content="const b = 1;\nconsole.log(b);",
        line_count=2,
        size_bytes=28,
    )

    summary = create_repository_summary(
        source_type=IngestionSourceType.local,
        source_path_or_url=str(tmp_path),
        files=[f1, f2],
        base_path=tmp_path,
    )

    assert summary.total_files == 2
    assert summary.total_lines == 3
    assert summary.languages.get("python") == 1
    assert summary.languages.get("typescript") == 2
    assert summary.source_type == IngestionSourceType.local


def test_ingest_local_api_endpoint(tmp_path: Path):
    test_file = tmp_path / "main.py"
    test_file.write_text("print('test')", encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/v1/ingest/local",
        json={"path": str(tmp_path)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_files"] >= 1
    assert data["source_type"] == "local"
    assert any(f["relative_path"] == "main.py" for f in data["files"])


def test_ingest_local_api_invalid_path():
    client = TestClient(app)
    response = client.post(
        "/api/v1/ingest/local",
        json={"path": "non_existent_folder_12345"},
    )
    assert response.status_code == 404


def test_ingest_github_api_invalid_url():
    client = TestClient(app)
    response = client.post(
        "/api/v1/ingest/github",
        json={"repo_url": "https://not-a-valid-github-url"},
    )
    assert response.status_code == 400

