# REQUIREMENTS.md

## Requirement Mapping

| ID | Requirement | Source | Status |
|----|-------------|--------|--------|
| **REQ-01** | Support ingestion from local folder paths and remote GitHub repository URLs | SPEC Goal 1 | ✅ Complete |
| **REQ-02** | Automatic language detection & dependency file identification for Python & JS/TS | SPEC Goal 1, 2 | ✅ Complete |
| **REQ-03** | AST and syntax-aware context preparation (chunking, functions, classes, line offsets) | SPEC Goal 2 | ✅ Complete |
| **REQ-04** | Security Auditor Agent prompt & schema for detecting vulnerabilities (OWASP, CWE, injection, secrets) | SPEC Goal 3 | ✅ Complete |
| **REQ-05** | Software Architect Agent prompt & schema for code quality, complexity, maintainability, and design | SPEC Goal 3 | ✅ Complete |
| **REQ-06** | Parallel asynchronous agent execution engine using Google Gemini API | SPEC Goal 3 | ✅ Complete |
| **REQ-07** | Review Moderator Agent with deduplication logic, conflict resolution, and risk prioritization formula | SPEC Goal 4 | ✅ Complete |
| **REQ-08** | Command-Line Interface (CLI) to initiate scans, monitor progress, and view formatted summaries | SPEC Goal 5 | ✅ Complete |
| **REQ-09** | Local Web Dashboard with live scan status, interactive findings viewer, and scan history | SPEC Goal 5 | ✅ Complete |
| **REQ-10** | HTML & PDF report generation engine with code snippets, evidence, and remediation advice | SPEC Goal 6 | Pending |
| **REQ-11** | Strictly advisory review flow without automatic source code modification | SPEC Goal 7 | ✅ Complete |
| **REQ-12** | Evaluation benchmark harness calculating Precision, Recall, F1, FPR, and localization accuracy | SPEC Goal 8 | Pending |

---

*Last updated: 2026-11-06*
