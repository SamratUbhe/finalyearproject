---
phase: 2
plan: "02"
wave: 2
depends_on:
  - "01"
files_modified:
  - src/orchestrator/__init__.py
  - src/orchestrator/runner.py
  - tests/test_orchestrator.py
autonomous: true
gap_closure: false
must_haves:
  truths:
    - "Review orchestrator coordinates parallel asynchronous execution of Security Auditor and Software Architect agents over code chunks"
    - "Concurrency is capped via asyncio.Semaphore to prevent API rate limit exhaustion"
    - "Individual chunk and agent timeouts are enforced via asyncio.wait_for without hanging the pipeline"
    - "Agent failures or network exceptions are isolated per chunk in AgentResult without aborting the broader review"
  artifacts:
    - src/orchestrator/__init__.py
    - src/orchestrator/runner.py
    - tests/test_orchestrator.py
---

# Plan 2.02: Parallel Asynchronous Review Execution Orchestrator

<objective>
Implement the multi-agent parallel execution orchestrator that coordinates simultaneous analysis runs between the Security Auditor Agent and the Software Architect Agent across all code chunks within a `ReviewContext`. Build concurrency management via `asyncio.Semaphore`, per-task timeout enforcement via `asyncio.wait_for`, and resilient error isolation so single-chunk or agent failures do not disrupt the complete repository review.

Purpose: Fulfill REQ-06 by providing a high-performance, asynchronous parallel pipeline that executes independent specialist reviews simultaneously with guaranteed safety against rate limits and timeouts.
Output: `src/orchestrator/__init__.py`, `src/orchestrator/runner.py`, and test suite `tests/test_orchestrator.py`.
</objective>

<context>
Load for context:
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- .gsd/REQUIREMENTS.md
- src/core/models.py
- src/core/config.py
- src/agents/security_agent.py
- src/agents/architect_agent.py
</context>

<tasks>

<task type="auto">
  <name>Build concurrency-controlled parallel multi-agent orchestrator</name>
  <files>
    src/orchestrator/__init__.py
    src/orchestrator/runner.py
  </files>
  <action>
    Implement `ReviewOrchestrator` in `src/orchestrator/runner.py`:

    1. Create `src/orchestrator/__init__.py`.
    2. Implement `ReviewOrchestrator` class (REQ-06):
       - `__init__(security_agent: Optional[SecurityAuditorAgent] = None, architect_agent: Optional[SoftwareArchitectAgent] = None, max_concurrency: Optional[int] = None, timeout_seconds: Optional[float] = None)`:
         - Fallback `security_agent` and `architect_agent` to default instantiated agents if not provided.
         - Fallback `max_concurrency` to `get_settings().agent_max_concurrency` (default 5).
         - Fallback `timeout_seconds` to `get_settings().agent_timeout_seconds` (default 60.0).
       - Method `async analyze_chunk_with_agents(chunk: CodeChunk, semaphore: asyncio.Semaphore, progress_callback: Optional[Callable] = None) -> list[AgentResult]`:
         - Acquires `semaphore` before dispatching agent tasks.
         - Spawns both agents concurrently:
           `task_sec = security_agent.analyze_chunk(chunk)`
           `task_arch = architect_agent.analyze_chunk(chunk)`
         - Executes both via `asyncio.gather(task_sec, task_arch, return_exceptions=True)` wrapped inside `asyncio.wait_for(..., timeout=timeout_seconds)`.
         - If timeout occurs (`asyncio.TimeoutError`):
           - Returns failed `AgentResult` objects for both agents with `error_message=f"Chunk analysis timed out after {timeout_seconds}s"`.
         - If an individual agent returns an `Exception`, constructs an `AgentResult` with `success=False`, `error_message=str(exc)`.
         - Invokes `progress_callback` if provided, reporting chunk completion status.
         - Returns `list[AgentResult]` (two results per chunk).
       - Method `async run_review(context: ReviewContext, progress_callback: Optional[Callable] = None) -> list[AgentResult]`:
         - Initializes `semaphore = asyncio.Semaphore(self.max_concurrency)`.
         - If `context.chunks` is empty, returns empty list `[]`.
         - Creates chunk analysis coroutines for all chunks in `context.chunks`.
         - Executes all chunk tasks using `asyncio.gather(*tasks)`.
         - Flattens the nested lists of `AgentResult` items into a single `list[AgentResult]`.
         - Returns all aggregated `AgentResult` items.

    AVOID: Unbounded concurrent API requests that trigger HTTP 429 rate limits or crash the event loop.
    USE: `asyncio.Semaphore` and `asyncio.wait_for` for strict concurrency and timeout isolation per chunk.
  </action>
  <verify>
    python -c "from src.orchestrator.runner import ReviewOrchestrator; assert ReviewOrchestrator is not None; print('ReviewOrchestrator verified successfully')"
  </verify>
  <done>
    `ReviewOrchestrator` is implemented with semaphore concurrency control, per-chunk timeout handling, and exception isolation.
  </done>
</task>

<task type="auto">
  <name>Build orchestrator integration and resilience test suite</name>
  <files>
    tests/test_orchestrator.py
  </files>
  <action>
    Build comprehensive async test suite in `tests/test_orchestrator.py`:

    1. Test parallel dispatch on multiple chunks:
       - Create mock `SecurityAuditorAgent` and `SoftwareArchitectAgent` returning predefined `AgentResult` objects.
       - Construct a sample `ReviewContext` with multiple `CodeChunk` instances.
       - Execute `orchestrator.run_review(context)`.
       - Assert both agents were called for every chunk and returned expected count of `AgentResult` items.
    
    2. Test concurrency limits:
       - Configure `max_concurrency = 2` on 6 chunks.
       - Track simultaneous running tasks using an active counter inside mock agents.
       - Assert active concurrent tasks never exceed `max_concurrency`.

    3. Test timeout resilience:
       - Mock an agent that sleeps longer than `timeout_seconds`.
       - Execute `orchestrator.run_review(context)`.
       - Assert orchestrator does not hang, completes within expected time, and records `success=False` with timeout error in `AgentResult`.

    4. Test exception isolation:
       - Mock an agent raising an unhandled `RuntimeError("LLM connection severed")` on chunk 1 while chunk 2 succeeds.
       - Assert review completes successfully, chunk 1 contains failed `AgentResult` with error message, and chunk 2 contains successful results.

    5. Test progress callback tracking:
       - Pass a tracking function into `run_review`.
       - Verify callback is called for completed chunks.

    AVOID: Making real external API calls in unit tests.
    USE: Async test doubles and `unittest.mock.AsyncMock` for deterministic test verification.
  </action>
  <verify>
    python -m pytest tests/test_orchestrator.py -v
  </verify>
  <done>
    `test_orchestrator.py` passes 100% of tests verifying parallel execution, concurrency capping, timeout handling, and exception resilience.
  </done>
</task>

</tasks>

<must_haves>
After all tasks complete, verify:
- [ ] `ReviewOrchestrator` runs Security and Architect agents concurrently per chunk
- [ ] Concurrency limit is strictly enforced via `asyncio.Semaphore`
- [ ] Per-chunk timeouts are enforced via `asyncio.wait_for` without crashing other tasks
- [ ] `pytest tests/test_orchestrator.py` passes all unit and integration tests
</must_haves>

<success_criteria>
- [ ] All tasks verified passing
- [ ] Must-haves confirmed
- [ ] Parallel execution orchestrator verified and ready for moderator integration
</success_criteria>

