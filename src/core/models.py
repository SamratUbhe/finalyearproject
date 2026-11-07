"""Core Pydantic domain models defining data schemas for code analysis and review."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LanguageEnum(str, Enum):
    """Supported source code languages."""

    python = "python"
    javascript = "javascript"
    typescript = "typescript"
    unknown = "unknown"


class IngestionSourceType(str, Enum):
    """Source origin of the ingested repository."""

    local = "local"
    github = "github"


# Enum created dynamically to allow 'class' as a member name despite Python keyword
ChunkType = Enum(
    "ChunkType",
    {
        "function": "function",
        "method": "method",
        "class": "class",
        "module_header": "module_header",
        "standalone_block": "standalone_block",
    },
    type=str,
)
setattr(ChunkType, "class_", ChunkType["class"])


class IngestedFile(BaseModel):
    """Metadata and raw text content of an ingested file."""

    file_path: str
    relative_path: str
    language: LanguageEnum
    content: str
    line_count: int
    size_bytes: int


class DependencyManifest(BaseModel):
    """Parsed package dependencies for vulnerability checking."""

    manifest_path: str
    manifest_type: str
    dependencies: Dict[str, str] = Field(default_factory=dict)


class RepositorySummary(BaseModel):
    """Aggregated structural and language metadata of an ingested codebase."""

    source_type: IngestionSourceType
    source_path_or_url: str
    total_files: int
    total_lines: int
    languages: Dict[str, int] = Field(default_factory=dict)
    manifests: List[DependencyManifest] = Field(default_factory=list)
    files: List[IngestedFile] = Field(default_factory=list)


class CodeChunk(BaseModel):
    """Individual granular code unit extracted via AST/parser with contextual scope."""

    chunk_id: str
    file_path: str
    relative_path: str
    language: LanguageEnum
    chunk_type: ChunkType
    name: str
    signature: Optional[str] = None
    start_line: int
    end_line: int
    code: str
    context_lines: Optional[str] = None
    docstring: Optional[str] = None
    imports: List[str] = Field(default_factory=list)
    parent_scope: Optional[str] = None


class ReviewContext(BaseModel):
    """Consolidated review context containing repository summary and all extracted code chunks."""

    repo_id: str
    summary: RepositorySummary
    chunks: List[CodeChunk] = Field(default_factory=list)
    total_chunks: int


class HealthResponse(BaseModel):
    """System health check response schema."""

    status: str
    version: str
    app_name: str


class LocalIngestRequest(BaseModel):
    """Request payload for local directory ingestion."""

    path: str
    max_file_size: int = 1048576
    extra_ignores: Optional[List[str]] = None


class GitHubIngestRequest(BaseModel):
    """Request payload for GitHub repository ingestion."""

    repo_url: str
    ref: Optional[str] = None
    pr_number: Optional[int] = None
    token: Optional[str] = None
    max_file_size: int = 1048576


class SeverityEnum(str, Enum):
    """Vulnerability and finding severity levels."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ConfidenceEnum(str, Enum):
    """Detection confidence levels."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AgentRoleEnum(str, Enum):
    """Specialized agent roles in multi-agent review architecture."""

    SECURITY_AUDITOR = "SECURITY_AUDITOR"
    SOFTWARE_ARCHITECT = "SOFTWARE_ARCHITECT"
    REVIEW_MODERATOR = "REVIEW_MODERATOR"


class CodeEvidence(BaseModel):
    """Concrete source code reference pinpointing detected issue location."""

    file_path: str
    start_line: int
    end_line: int
    code_snippet: str


class RemediationAdvice(BaseModel):
    """Actionable developer guidance for safely addressing identified issues."""

    explanation: str
    recommended_fix: str
    references: List[str] = Field(default_factory=list)


class Finding(BaseModel):
    """Individual code vulnerability or architectural defect detected by a specialist agent."""

    id: str
    agent_role: AgentRoleEnum
    category: str
    cwe_id: Optional[str] = None
    owasp_category: Optional[str] = None
    title: str
    description: str
    severity: SeverityEnum
    confidence: ConfidenceEnum
    evidence: CodeEvidence
    remediation: RemediationAdvice
    raw_risk_score: Optional[float] = None
    is_advisory_only: bool = True


class AgentResult(BaseModel):
    """Execution output from a single specialist agent reviewing a specific code chunk."""

    agent_role: AgentRoleEnum
    chunk_id: Optional[str] = None
    file_path: str
    execution_time_ms: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    findings: List[Finding] = Field(default_factory=list)
    tokens_used: Optional[int] = None


class ModeratedFinding(BaseModel):
    """Arbitrated, deduplicated, and prioritized finding produced by Review Moderator."""

    finding: Finding
    risk_score: float
    priority_rank: int
    is_deduplicated: bool = False
    sources: List[AgentRoleEnum] = Field(default_factory=list)
    arbitration_notes: Optional[str] = None


class ConsolidatedReview(BaseModel):
    """Final moderated repository review report ready for developer consumption."""

    review_id: str
    repo_id: str
    created_at: str
    status: str
    total_files_reviewed: int
    total_chunks_reviewed: int
    findings: List[ModeratedFinding] = Field(default_factory=list)
    severity_distribution: Dict[str, int] = Field(default_factory=dict)
    risk_summary: Dict[str, Any] = Field(default_factory=dict)
    agent_metrics: Dict[str, Any] = Field(default_factory=dict)
    advisory_disclaimer: str = (
        "This review report contains purely advisory recommendations for developer "
        "evaluation. No source code modifications have been applied automatically."
    )



