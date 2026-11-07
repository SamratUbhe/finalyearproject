---
milestone: v1.0
version: 1.0.0
updated: 2026-11-06
---

# Roadmap — Automated Code Vulnerability Reviewing

> **Current Phase:** Phase 4 - Structured Report Generation (HTML & PDF)
> **Status:** planning

## Must-Haves (from SPEC)

- [x] Dual ingestion from local directory paths and GitHub URLs (Phase 1)
- [x] Syntax-aware context preparation (Python and JavaScript/TypeScript) (Phase 1)
- [x] Parallel execution of Security Auditor and Software Architect agents via Google Gemini API (Phase 2)
- [x] Review Moderator consolidation, deduplication, and risk prioritization (Phase 2)
- [x] Developer interfaces: Local Web Dashboard + Command-Line Interface (CLI) (Phase 3)
- [ ] Downloadable structured review reports in HTML and PDF formats
- [ ] Evaluation benchmark harness producing Paper Section VII metrics (Precision, Recall, F1)

---

## Phases

### Phase 1: Ingestion & Context Preparation Engine
**Status:** ✅ Complete  
**Objective:** Deliver core repository retrieval (local directory + GitHub API), automatic language detection, file filtering, and AST/syntax-aware code chunking for Python and JavaScript/TypeScript.  
**Requirements:** REQ-01, REQ-02, REQ-03  

**Plans:**
- [x] Plan 1.1: Project scaffolding, environment configuration (.env), and FastAPI backend foundation.
- [x] Plan 1.2: Repository and local workspace ingestion engine with language and dependency detection.
- [x] Plan 1.3: Syntax-aware context preparation and AST extractor for Python and JS/TS.

---

### Phase 2: Multi-Agent Review & Moderation Core
**Status:** ✅ Complete  
**Objective:** Implement the three specialized agents (Security Auditor, Software Architect, Review Moderator) with async parallel execution using the Google Gemini API, structured JSON outputs, deduplication, and risk scoring.  
**Depends on:** Phase 1  
**Requirements:** REQ-04, REQ-05, REQ-06, REQ-07, REQ-11  

**Plans:**
- [x] Plan 2.1: Gemini client integration, review schemas, and Security Auditor & Software Architect specialized agents.
- [x] Plan 2.2: Concurrency-controlled asynchronous parallel review orchestrator with timeout and error resilience.
- [x] Plan 2.3: Review Moderator agent implementation for deduplication, conflict arbitration, risk prioritization, and review API routes.

---

### Phase 3: Developer Interfaces (CLI & Local Web Dashboard)
**Status:** ✅ Complete  
**Objective:** Provide both terminal-based CLI interaction and a local Web Dashboard to initiate reviews, watch live agent progress, inspect detailed findings with code context, and browse review history.  
**Depends on:** Phase 2  
**Requirements:** REQ-08, REQ-09  

**Plans:**
- [x] Plan 3.1: Command-Line Interface (CLI) with rich terminal output, progress spinners, and colored vulnerability cards.
- [x] Plan 3.2: Review history storage, scan comparison engine, and REST history API routes.
- [x] Plan 3.3: Local Web Dashboard frontend with review initiation, live agent telemetry, findings explorer, and history viewer.

---

### Phase 4: Structured Report Generation (HTML & PDF)
**Status:** 🟡 Ready to Execute  
**Objective:** Build report generation pipeline producing clean, professional HTML and PDF reports containing issue titles, file/line locations, code evidence, and remediation advice.  
**Depends on:** Phase 3  
**Requirements:** REQ-10  

**Plans:**
- [ ] Plan 4.1: HTML report generator with styled vulnerability badges, code snippets, metrics overview, and Web Dashboard export.
- [ ] Plan 4.2: PDF export generator (ReportLab), CLI export flags, and comprehensive test suite.

---

### Phase 5: Evaluation Benchmark Suite & College Defense Prep
**Status:** ⬜ Not Started  
**Objective:** Implement the empirical evaluation module from Section VII of the paper with curated test codebases (vulnerable & secure) to compute Precision, Recall, F1, FPR, and review speed for the final year defense.  
**Depends on:** Phase 4  
**Requirements:** REQ-12  

**Plans:**
- [ ] Plan 5.1: Benchmark dataset of known vulnerability test cases (Python and JavaScript) with ground-truth labels.
- [ ] Plan 5.2: Evaluation metrics runner calculating Section VII metrics and generating summary tables and charts.

---

## Progress Summary

| Phase | Status | Plans | Complete |
|-------|--------|-------|----------|
| 1. Ingestion & Context Engine | ✅ Complete | 3/3 | 100% |
| 2. Multi-Agent Review Core | ✅ Complete | 3/3 | 100% |
| 3. CLI & Web Dashboard | ✅ Complete | 3/3 | 100% |
| 4. Report Generation (HTML/PDF) | ⬜ Not Started | 0/2 | 0% |
| 5. Evaluation Benchmark Suite | ⬜ Not Started | 0/2 | 0% |

---

*Last updated: 2026-11-06*
