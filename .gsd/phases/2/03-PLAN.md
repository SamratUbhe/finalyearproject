---
phase: 2
plan: "03"
wave: 3
depends_on:
  - "01"
  - "02"
files_modified:
  - src/moderator/__init__.py
  - src/moderator/moderator.py
  - src/api/routes/review.py
  - src/main.py
  - tests/test_moderator.py
  - tests/test_review_pipeline.py
autonomous: true
gap_closure: false
must_haves:
  truths:
    - "Review Moderator Agent identifies and merges duplicate findings from multiple agents using file path, line span overlap, and CWE/semantic similarity"
    - "Conflict arbitration applies security precedence over architectural/style suggestions when findings clash on security boundaries"
    - "Prioritized risk scoring formula calculates quantitative risk scores using Severity * Confidence with evidence fidelity bonus and sorts findings descending"
    - "Advisory safety is strictly preserved with standard advisory disclaimer and no automated code rewriting or patching"
    - "FastAPI review endpoints (/api/v1/review/run and /api/v1/review/moderate) return validated ConsolidatedReview responses"
  artifacts:
    - src/moderator/__init__.py
    - src/moderator/moderator.py
    - src/api/routes/review.py
    - tests/test_moderator.py
    - tests/test_review_pipeline.py
---

# Plan 2.03: Review Moderator Agent, Deduplication, Risk Scoring & Review API

<objective>
Implement the Review Moderator Agent responsible for consolidating raw observations from the Security Auditor and Software Architect agents into a unified, prioritized review report. Implement line-span and CWE-based deduplication algorithms, deterministic conflict arbitration giving precedence to security over style/architecture, and a quantitative risk scoring formula (`SeverityWeight * ConfidenceMultiplier`). Expose FastAPI review endpoints (`/api/v1/review/run` and `/api/v1/review/moderate`) and verify the full multi-agent pipeline end-to-end.

Purpose: Fulfill REQ-07 and REQ-11 by delivering the central moderation brain of the framework that turns disparate agent findings into cohesive, prioritized, and advisory reports.
Output: `src/moderator/__init__.py`, `src/moderator/moderator.py`, `src/api/routes/review.py`, registered in `src/main.py`, and test suites `tests/test_moderator.py` and `tests/test_review_pipeline.py`.
</objective>

<context>
Load for context:
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- .gsd/REQUIREMENTS.md
- src/core/models.py
- src/orchestrator/runner.py
- src/agents/security_agent.py
- src/agents/architect_agent.py
- src/main.py
</context>

<tasks>

<task type="auto">
  <name>Build Review Moderator Agent with deduplication, conflict arbitration, and prioritized risk scoring</name>
  <files>
    src/moderator/__init__.py
    src/moderator/moderator.py
    tests/test_moderator.py
  </files>
  <action>
    Implement `ReviewModeratorAgent` in `src/moderator/moderator.py` (REQ-07, REQ-11):

    1. Create `src/moderator/__init__.py`.
    2. Implement `ReviewModeratorAgent` class:
       - Configurable severity weights:
         `CRITICAL: 10.0`, `HIGH: 7.5`, `MEDIUM: 5.0`, `LOW: 2.5`, `INFO: 1.0`
       - Configurable confidence multipliers:
         `HIGH: 1.0`, `MEDIUM: 0.75`, `LOW: 0.5`
       - Method `calculate_risk_score(severity: SeverityEnum, confidence: ConfidenceEnum, has_evidence: bool = True) -> float`:
         - `base = severity_weight[severity] * confidence_multiplier[confidence]`
         - If `has_evidence`: add `+0.5` evidence fidelity bonus (capped at 10.0).
         - Return `round(base, 1)`.
       - Method `are_findings_duplicate(f1: Finding, f2: Finding) -> bool`:
         - Must have matching `file_path`.
         - Must have overlapping or adjacent line spans:
           `max(f1.evidence.start_line, f2.evidence.start_line) <= min(f1.evidence.end_line, f2.evidence.end_line) + 3`.
         - Must share matching `cwe_id` (if both have CWEs) OR have significant token/word overlap between their titles/categories (>0.3 Jaccard similarity).
       - Method `arbitrate_conflict(findings: list[Finding]) -> tuple[Finding, list[AgentRoleEnum], Optional[str]]`:
         - Determine all contributing agent roles: `sources = list({f.agent_role for f in findings})`.
         - If both `SECURITY_AUDITOR` and `SOFTWARE_ARCHITECT` are present:
           - Security Precedence Rule: The security finding takes precedence. Select the finding originating from `SECURITY_AUDITOR`.
           - If architectural finding recommended code simplification that compromises security boundaries, append `arbitration_notes="Security Auditor recommendation takes precedence over Software Architect simplification/refactoring."`.
         - Else: select the finding with the highest severity.
         - Ensure combined `sources` are preserved.
       - Method `deduplicate_and_arbitrate(findings: list[Finding]) -> list[tuple[Finding, list[AgentRoleEnum], bool, Optional[str]]]`:
         - Groups duplicate findings using `are_findings_duplicate`.
         - For each duplicate group, applies `arbitrate_conflict` to produce a single resolved finding with merged sources and notes.
       - Method `moderate_review(repo_id: str, agent_results: list[AgentResult], total_files: int = 0, total_chunks: int = 0) -> ConsolidatedReview`:
         - Extract all findings from `agent_results` where `success=True`.
         - Run `deduplicate_and_arbitrate` over the collected findings.
         - For each resolved finding:
           - Calculate `risk_score` using `calculate_risk_score`.
           - Set `finding.is_advisory_only = True` (REQ-11).
           - Wrap in `ModeratedFinding(finding=..., risk_score=..., priority_rank=0, is_deduplicated=..., sources=..., arbitration_notes=...)`.
         - Sort all `ModeratedFinding` items in descending order of `risk_score`.
         - Assign sequential `priority_rank` (1, 2, 3, ...).
         - Compute `severity_distribution`: count occurrences of each `SeverityEnum`.
         - Compute `risk_summary`: `average_risk_score`, `max_risk_score`, `total_findings`, `critical_count`, `high_count`, `deduplicated_count`.
         - Aggregate `agent_metrics`: execution time, success counts, token usage across agent results.
         - Construct and return `ConsolidatedReview` with UUID `review_id`, timestamp `created_at`, status `"completed"`, and non-empty `advisory_disclaimer`.

    3. Create `tests/test_moderator.py`:
       - Test deduplication: Feed overlapping findings from Security and Architect; verify merged into one with both sources and `is_deduplicated=True`.
       - Test security precedence arbitration: Feed conflicting advice on same lines; verify Security finding prevails and arbitration notes are set.
       - Test risk scoring: Verify critical findings rank above low findings and score matches formula.
       - Test advisory safety: Verify all findings have `is_advisory_only=True` and `ConsolidatedReview` contains the advisory disclaimer.

    AVOID: Naive string matching for deduplication; use normalized line span overlaps and semantic category matching.
    USE: Deterministic risk scoring formula (`Severity * Confidence`) and explicit security precedence arbitration.
  </action>
  <verify>
    python -m pytest tests/test_moderator.py -v
  </verify>
  <done>
    `ReviewModeratorAgent` deduplicates findings, applies security precedence arbitration, scores risk accurately, and passes all tests in `test_moderator.py`.
  </done>
</task>

<task type="auto">
  <name>Build review API endpoints and verify full pipeline end-to-end</name>
  <files>
    src/api/routes/review.py
    src/main.py
    tests/test_review_pipeline.py
  </files>
  <action>
    Expose review endpoints in FastAPI and create end-to-end integration tests:

    1. In `src/api/routes/review.py`:
       - Create `APIRouter(prefix="/api/v1/review", tags=["Review & Moderation"])`.
       - Implement `POST /run`:
         - Accepts `context: ReviewContext` in request body.
         - Instantiates `ReviewOrchestrator` and `ReviewModeratorAgent`.
         - Runs `agent_results = await orchestrator.run_review(context)`.
         - Runs `review = moderator.moderate_review(context.repo_id, agent_results, len(context.summary.files), context.total_chunks)`.
         - Returns `ConsolidatedReview`.
       - Implement `POST /moderate`:
         - Accepts payload `ModerationRequest(repo_id: str, agent_results: list[AgentResult], total_files: int = 0, total_chunks: int = 0)`.
         - Runs `moderator.moderate_review(...)`.
         - Returns `ConsolidatedReview`.

    2. In `src/main.py`:
       - Import and register review router: `app.include_router(review_router)`.

    3. In `tests/test_review_pipeline.py`:
       - Test `POST /api/v1/review/run` with a simulated multi-chunk `ReviewContext` using mocked agent responses:
         - Verify 200 OK status.
         - Verify response conforms to `ConsolidatedReview` schema.
         - Verify findings are ranked in descending order of risk score.
         - Verify duplicate findings across agents were successfully unified.
         - Verify advisory disclaimer and advisory flags are present (REQ-11).
       - Test `POST /api/v1/review/moderate` directly with sample `AgentResult` items.
       - Run health check to confirm zero route collisions or regressions.

    AVOID: Leaving API endpoints unregistered or returning unvalidated JSON dictionaries.
    USE: Typed FastAPI response models returning validated `ConsolidatedReview` schemas.
  </action>
  <verify>
    python -m pytest tests/test_review_pipeline.py tests/test_health.py -v
  </verify>
  <done>
    Review API endpoints `/api/v1/review/run` and `/api/v1/review/moderate` are registered in `src/main.py`, tested end-to-end, and all tests pass cleanly.
  </done>
</task>

</tasks>

<must_haves>
After all tasks complete, verify:
- [ ] `ReviewModeratorAgent` deduplicates findings and applies security precedence arbitration
- [ ] Prioritized risk scoring formula produces quantitative risk scores and priority rankings
- [ ] Advisory safety is strictly maintained with `is_advisory_only=True` and advisory disclaimer
- [ ] `POST /api/v1/review/run` and `POST /api/v1/review/moderate` return valid `ConsolidatedReview`
- [ ] `pytest tests/test_moderator.py tests/test_review_pipeline.py` passes 100%
</must_haves>

<success_criteria>
- [ ] All tasks verified passing
- [ ] Must-haves confirmed
- [ ] Full Phase 2 multi-agent review and moderation pipeline verified and operational
</success_criteria>

