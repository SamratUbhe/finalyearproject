# SPEC.md — Project Specification

> **Status**: `FINALIZED`
>
> ⚠️ **Planning Lock**: Requirements and architecture are finalized per IJSREM Oct 2026 paper and user alignment. Ready for Phase 1 planning.

## Vision
An automated code vulnerability reviewing framework based on a role-based multi-agent architecture (Security Auditor Agent, Software Architect Agent, and Review Moderator Agent) integrated with GitHub and local workspaces. The system retrieves target code, generates syntax-aware structural context, coordinates parallel LLM-powered specialist reviews via Google Gemini API, and moderates observations into prioritized, evidence-backed advisory reports presented through a local Web Dashboard and CLI, with a dedicated evaluation benchmark suite for academic defense.

## Goals
1. **Dual Ingestion**: Ingest source code from both local folder paths and remote GitHub repository URLs (branches, pull requests, commits).
2. **Syntax-Aware Context Preparation**: Extract structural AST elements (functions, classes, dependencies, surrounding context) for Python and JavaScript/TypeScript.
3. **Role-Based Parallel Multi-Agent Review**: Execute the Security Auditor Agent (identifying vulnerabilities, OWASP Top 10, CWEs, unsafe calls) and Software Architect Agent (code structure, maintainability, design anti-patterns) independently in parallel using Google Gemini API.
4. **Moderator Consolidation & Risk Prioritization**: The Review Moderator Agent merges findings, eliminates duplicates, arbitrates conflicts (security precedence), and scores risk based on severity, confidence, and code evidence.
5. **Dual Developer Interfaces**: Provide a local web dashboard (real-time progress, code viewer, findings explorer, review history) and a command-line interface (CLI) for terminal execution.
6. **Structured Reporting**: Generate downloadable, professional review reports in HTML and PDF formats.
7. **Advisory Safety Principle**: Maintain developer authority with strict advisory recommendations; no automated modifying of source files.
8. **Empirical Evaluation Benchmark Suite**: Implement the evaluation framework from Section VII of the paper to compute Precision, Recall, F1-score, False Positive Rate, and Localization Accuracy across test vulnerability sets.

## Non-Goals (Out of Scope)
- Automatic code patching / writing directly to analyzed repositories (Human-in-the-loop only).
- Multi-tenant cloud SaaS deployment (locally hosted, privacy-preserving execution).
- IDE extension development (VS Code plugin is future scope; Web Dashboard + CLI serve developer needs).

## Users
- Final Year / Diploma Students & Evaluators (Zeal Polytechnic AIML Department).
- Software Developers and Code Reviewers looking for automated security reviews before merge.
- Security and Quality Analysts inspecting repositories.

## Constraints
- **Backend / Orchestrator**: Python 3.10+ (FastAPI + Asyncio native multi-agent coordination).
- **LLM Provider**: Google Gemini API (`gemini-2.0-flash` / `gemini-1.5-pro`).
- **Initial Language Targets**: Python (`.py`) and JavaScript/TypeScript (`.js`, `.jsx`, `.ts`, `.tsx`).
- **Security & Privacy**: API keys stored strictly in local environment variables (`.env`), not in git or exported reports.

## Success Criteria
- [ ] Code ingestion accepts a local directory path or a GitHub repository URL.
- [ ] Language detector accurately classifies Python and JavaScript/TypeScript codebases.
- [ ] Context preparation module extracts relevant code blocks with surrounding lines and AST structure.
- [ ] Security Auditor and Software Architect agents run in parallel and return structured JSON findings.
- [ ] Review Moderator successfully eliminates duplicate issues and outputs a unified prioritized finding list.
- [ ] Web dashboard displays running agent states, review progress, and interactive findings.
- [ ] CLI executes complete reviews from the command line with colored terminal output.
- [ ] Reports can be exported and downloaded in both HTML and PDF formats.
- [ ] Built-in benchmark suite runs against test vulnerability datasets and produces the 8 paper evaluation metrics.

---

*Last updated: 2026-11-04*

