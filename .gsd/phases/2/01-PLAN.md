---
phase: 2
plan: "01"
wave: 1
depends_on: []
files_modified:
  - src/core/config.py
  - src/core/models.py
  - src/agents/__init__.py
  - src/agents/gemini_client.py
  - src/agents/security_agent.py
  - src/agents/architect_agent.py
  - tests/test_gemini_client.py
  - tests/test_agents.py
autonomous: true
gap_closure: false
must_haves:
  truths:
    - "Multi-agent review domain models define complete Pydantic schemas for Finding, AgentResult, CodeEvidence, RemediationAdvice, ModeratedFinding, and ConsolidatedReview"
    - "Gemini API client executes asynchronous requests, parses structured JSON, retries transient rate limits with backoff, and provides graceful missing-key handling"
    - "Security Auditor Agent evaluates code chunks for OWASP Top 10 vulnerabilities and CWEs, returning schema-compliant findings with code evidence"
    - "Software Architect Agent evaluates code chunks for complexity, code smells, modularity, and anti-patterns, returning schema-compliant findings"
    - "Advisory safety is enforced with is_advisory_only flags and purely advisory remediation advice without automated code modifications"
  artifacts:
    - src/core/models.py
    - src/agents/gemini_client.py
    - src/agents/security_agent.py
    - src/agents/architect_agent.py
    - tests/test_gemini_client.py
    - tests/test_agents.py
---

# Plan 2.01: Gemini Client Integration, Review Schemas & Specialized Review Agents

<objective>
Implement the core LLM client integration and role-specialized review agents: the Security Auditor Agent and the Software Architect Agent. Establish strongly typed Pydantic models for vulnerability findings, code evidence, and advisory remediation, build an asynchronous Google Gemini API client with schema enforcement and retry resilience, and engineer role-specific system prompts with strictly advisory safety rules.

Purpose: Fulfill REQ-04, REQ-05, and REQ-11 by equipping the framework with standardized vulnerability review schemas and the specialized prompt intelligence required to detect security flaws and architectural weaknesses.
Output: Extended `src/core/config.py` and `src/core/models.py`, `src/agents/gemini_client.py`, `src/agents/security_agent.py`, `src/agents/architect_agent.py`, and test suites `tests/test_gemini_client.py` and `tests/test_agents.py`.
</objective>

<context>
Load for context:
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- .gsd/REQUIREMENTS.md
- src/core/config.py
- src/core/models.py
</context>

<tasks>

<task type="auto">
  <name>Extend configuration and implement review domain models with advisory safety</name>
  <files>
    src/core/config.py
    src/core/models.py
  </files>
  <action>
    Extend settings and define multi-agent review domain schemas in Pydantic v2:
    
    1. In `src/core/config.py`, add agent and Gemini configuration fields to `Settings`:
       - `gemini_model: str = "gemini-2.0-flash"`
       - `gemini_fallback_model: str = "gemini-1.5-pro"`
       - `gemini_temperature: float = 0.2`
       - `gemini_max_retries: int = 3`
       - `agent_timeout_seconds: float = 60.0`
       - `agent_max_concurrency: int = 5`

    2. In `src/core/models.py`, implement domain models:
       - `SeverityEnum(str, Enum)`: `CRITICAL = "CRITICAL"`, `HIGH = "HIGH"`, `MEDIUM = "MEDIUM"`, `LOW = "LOW"`, `INFO = "INFO"`
       - `ConfidenceEnum(str, Enum)`: `HIGH = "HIGH"`, `MEDIUM = "MEDIUM"`, `LOW = "LOW"`
       - `AgentRoleEnum(str, Enum)`: `SECURITY_AUDITOR = "SECURITY_AUDITOR"`, `SOFTWARE_ARCHITECT = "SOFTWARE_ARCHITECT"`, `REVIEW_MODERATOR = "REVIEW_MODERATOR"`
       - `CodeEvidence(BaseModel)`:
         - `file_path: str`
         - `start_line: int`
         - `end_line: int`
         - `code_snippet: str`
       - `RemediationAdvice(BaseModel)`:
         - `explanation: str`
         - `recommended_fix: str`
         - `references: List[str] = Field(default_factory=list)`
       - `Finding(BaseModel)`:
         - `id: str`
         - `agent_role: AgentRoleEnum`
         - `category: str` (e.g. "OWASP A03:2021-Injection", "CWE-89", "Code Quality / Complexity")
         - `cwe_id: Optional[str] = None`
         - `owasp_category: Optional[str] = None`
         - `title: str`
         - `description: str`
         - `severity: SeverityEnum`
         - `confidence: ConfidenceEnum`
         - `evidence: CodeEvidence`
         - `remediation: RemediationAdvice`
         - `raw_risk_score: Optional[float] = None`
         - `is_advisory_only: bool = True` (REQ-11 safety constraint)
       - `AgentResult(BaseModel)`:
         - `agent_role: AgentRoleEnum`
         - `chunk_id: Optional[str] = None`
         - `file_path: str`
         - `execution_time_ms: float = 0.0`
         - `success: bool = True`
         - `error_message: Optional[str] = None`
         - `findings: List[Finding] = Field(default_factory=list)`
         - `tokens_used: Optional[int] = None`
       - `ModeratedFinding(BaseModel)`:
         - `finding: Finding`
         - `risk_score: float`
         - `priority_rank: int`
         - `is_deduplicated: bool = False`
         - `sources: List[AgentRoleEnum] = Field(default_factory=list)`
         - `arbitration_notes: Optional[str] = None`
       - `ConsolidatedReview(BaseModel)`:
         - `review_id: str`
         - `repo_id: str`
         - `created_at: str`
         - `status: str`
         - `total_files_reviewed: int`
         - `total_chunks_reviewed: int`
         - `findings: List[ModeratedFinding] = Field(default_factory=list)`
         - `severity_distribution: Dict[str, int] = Field(default_factory=dict)`
         - `risk_summary: Dict[str, Any] = Field(default_factory=dict)`
         - `agent_metrics: Dict[str, Any] = Field(default_factory=dict)`
         - `advisory_disclaimer: str = "This review report contains purely advisory recommendations for developer evaluation. No source code modifications have been applied automatically."` (REQ-11)

    AVOID: Unvalidated or loose dictionaries for LLM outputs.
    USE: Strongly typed Pydantic models with default values and enum validation.
  </action>
  <verify>
    python -c "from src.core.models import Finding, SeverityEnum, AgentRoleEnum, ConsolidatedReview; from src.core.config import get_settings; s = get_settings(); assert s.gemini_model == 'gemini-2.0-flash'; print('Settings & models validated')"
  </verify>
  <done>
    `src/core/config.py` contains LLM settings and `src/core/models.py` contains complete multi-agent review Pydantic models.
  </done>
</task>

<task type="auto">
  <name>Build asynchronous Gemini API client with structured JSON enforcement and retry resilience</name>
  <files>
    src/agents/__init__.py
    src/agents/gemini_client.py
    tests/test_gemini_client.py
  </files>
  <action>
    Implement asynchronous Google Gemini API client in `src/agents/gemini_client.py`:

    1. Implement `GeminiClient` class:
       - Configurable via `__init__(api_key: Optional[str] = None, model_name: Optional[str] = None, temperature: Optional[float] = None, timeout: Optional[float] = None)`.
       - Defaults fall back to `get_settings()`.
       - Calls Google Gemini REST endpoint asynchronously using `httpx.AsyncClient`:
         `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}`
         (or delegates to `google-genai` SDK if configured and compatible).
       - In the request body, configure:
         - `contents`: formatted user prompt and code context.
         - `system_instruction`: role and guidelines.
         - `generationConfig`: `temperature`, `response_mime_type="application/json"`.
       - Implement retry mechanism with exponential backoff (e.g. 1s, 2s, 4s) for HTTP 429 (rate limit) and HTTP 503 (service unavailable) up to `gemini_max_retries`.
       - Implement robust JSON cleaning: handles optional markdown wrapping (````json ... ````) and parses JSON defensively.
       - Method `async generate_structured_review(prompt: str, system_instruction: str) -> dict | list`:
         - Sends request, validates JSON response.
         - If `api_key` is not configured or empty, raises clear `ValueError("GEMINI_API_KEY is not configured in environment")` so caller can handle gracefully.
         - Sets client timeout adhering to `agent_timeout_seconds`.

    2. Create unit tests in `tests/test_gemini_client.py`:
       - Test client initialization with default settings.
       - Test JSON response parsing and markdown fence stripping with mocked httpx transport.
       - Test rate limit 429 retry behavior with mock backoff.
       - Test error raising when API key is missing.

    AVOID: Synchronous blocking API calls that freeze the asyncio event loop.
    USE: `httpx.AsyncClient` with `response_mime_type="application/json"` and defensive retry backoff.
  </action>
  <verify>
    python -m pytest tests/test_gemini_client.py -v
  </verify>
  <done>
    `GeminiClient` executes async calls, cleans and parses JSON responses, retries on 429 errors, and passes all tests in `test_gemini_client.py`.
  </done>
</task>

<task type="auto">
  <name>Implement Security Auditor and Software Architect specialized agents</name>
  <files>
    src/agents/security_agent.py
    src/agents/architect_agent.py
    tests/test_agents.py
  </files>
  <action>
    Implement role-specialized review agents with prompt engineering and schema validation:

    1. In `src/agents/security_agent.py`, implement `SecurityAuditorAgent` (REQ-04, REQ-11):
       - System instruction: Act as a Senior Application Security Auditor.
       - Rules: Inspect code chunk and surrounding context for:
         - OWASP Top 10 vulnerabilities (SQLi, command injection, path traversal, XSS, broken authentication, insecure deserialization, SSRF).
         - Secret leakage (hardcoded API tokens, credentials, private keys).
         - Insecure cryptography (weak hashes like MD5/SHA1 for passwords, ECB mode, hardcoded salts).
         - Require valid CWE identifiers (e.g. "CWE-89") and OWASP categories for every issue.
         - Require exact line spans and code evidence matching the chunk.
         - Formulate purely advisory remediation advice with secure patterns (REQ-11).
       - Method `async analyze_chunk(chunk: CodeChunk) -> AgentResult`:
         - Formats analysis prompt with chunk name, code, imports, and surrounding context.
         - Invokes `GeminiClient.generate_structured_review`.
         - Parses returned JSON into `list[Finding]` with `agent_role = AgentRoleEnum.SECURITY_AUDITOR`, `is_advisory_only = True`.
         - Measures execution time and returns `AgentResult`.
         - Catches LLM/network errors and returns `AgentResult(agent_role=AgentRoleEnum.SECURITY_AUDITOR, success=False, error_message=str(exc))`.

    2. In `src/agents/architect_agent.py`, implement `SoftwareArchitectAgent` (REQ-05, REQ-11):
       - System instruction: Act as a Principal Software Architect.
       - Rules: Inspect code chunk and surrounding context for:
         - Excessive cyclomatic/cognitive complexity and God methods/classes.
         - Single Responsibility Principle (SRP) violations and tight coupling.
         - Resource leak anti-patterns (unclosed files, network sockets, database handles).
         - Code duplication and dead/unreachable logic.
         - Anti-patterns in async/await, error suppression, and exception swallowing.
       - Method `async analyze_chunk(chunk: CodeChunk) -> AgentResult`:
         - Formats analysis prompt with chunk metadata.
         - Invokes `GeminiClient.generate_structured_review`.
         - Parses returned JSON into `list[Finding]` with `agent_role = AgentRoleEnum.SOFTWARE_ARCHITECT`, `is_advisory_only = True`.
         - Measures execution time and returns `AgentResult`.
         - Catches errors and returns `AgentResult(agent_role=AgentRoleEnum.SOFTWARE_ARCHITECT, success=False, error_message=str(exc))`.

    3. In `tests/test_agents.py`:
       - Test `SecurityAuditorAgent` with mocked LLM response returning an injection vulnerability; verify `Finding` schema, CWE, severity, and advisory flag.
       - Test `SoftwareArchitectAgent` with mocked LLM response returning high cyclomatic complexity; verify schema, evidence, and remediation advice.
       - Test agent error handling when LLM client raises an exception.

    AVOID: Freeform text output without schema constraints that breaks downstream parsers.
    USE: Schema-enforced prompts returning structured JSON arrays conforming to `Finding` schema.
  </action>
  <verify>
    python -m pytest tests/test_agents.py -v
  </verify>
  <done>
    `SecurityAuditorAgent` and `SoftwareArchitectAgent` analyze code chunks, produce schema-validated `AgentResult` and `Finding` objects, and pass all tests in `test_agents.py`.
  </done>
</task>

</tasks>

<must_haves>
After all tasks complete, verify:
- [ ] `src/core/models.py` contains `Finding`, `AgentResult`, `ModeratedFinding`, and `ConsolidatedReview`
- [ ] `GeminiClient` handles async requests, JSON cleaning, and rate-limit retries
- [ ] `SecurityAuditorAgent` and `SoftwareArchitectAgent` parse LLM outputs into structured `Finding` objects
- [ ] `pytest tests/test_gemini_client.py tests/test_agents.py` passes 100%
</must_haves>

<success_criteria>
- [ ] All tasks verified passing
- [ ] Must-haves confirmed
- [ ] Specialized agents ready for parallel orchestration
</success_criteria>

