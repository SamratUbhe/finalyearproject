# DECISIONS.md — Architecture Decision Records

> **Purpose**: Log significant technical decisions and their rationale.

## [DECISION-001] Role-Based Triad Multi-Agent Architecture

**Date**: 2026-11-04  
**Status**: Accepted  

### Context
Using a single general-purpose LLM prompt to review code leads to missed security issues, hallucinated vulnerability descriptions, and conflation of style suggestions with critical CVE risks.

### Decision
Adopt a role-based 3-agent architecture as formulated in the IJSREM paper:
1. **Security Auditor Agent**: Specializes solely in vulnerability detection (injections, OWASP, secrets, unsanitized inputs).
2. **Software Architect Agent**: Specializes in design, modularity, code smell, and maintainability concerns.
3. **Review Moderator Agent**: Merges findings, deduplicates overlapping issues, resolves conflicts with security priority, and calculates risk scores.

### Rationale
Separating security from architectural evaluation ensures neither concern is diluted. Running specialist agents in parallel cuts review latency, while the Review Moderator ensures consistent, non-redundant feedback.

---

## [DECISION-002] Multi-Ingestion: Local Filesystem and GitHub URLs

**Date**: 2026-11-04  
**Status**: Accepted  

### Context
While production workflows integrate with GitHub pull requests, academic defenses and local developer workflows require reviewing code offline without deploying public webhook endpoints.

### Decision
Support both local directory scanning (instant offline evaluation) and remote GitHub repository URL ingestion (fetching branches/commits via GitHub API).

---

## [DECISION-003] LLM Backbone Selection: Google Gemini API

**Date**: 2026-11-04  
**Status**: Accepted  

### Context
The multi-agent system requires high speed, generous context windows for source code, structured JSON output enforcement, and cost-effective access for academic testing.

### Decision
Standardize on Google Gemini API (`gemini-2.0-flash` / `gemini-1.5-pro`) for all three agents.

---

*Last updated: 2026-11-04*

