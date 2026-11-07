"""Standalone HTML report generator for Automated Code Vulnerability Reviewer.

Generates self-contained, offline-ready HTML reports with executive metrics,
severity distributions, prioritized findings with code evidence, and print stylesheets.
"""

from html import escape
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.core.models import ConsolidatedReview, ModeratedFinding

logger = logging.getLogger("reviewer.reports.html")


class HTMLReportGenerator:
    """Generates self-contained, offline-ready HTML reports from ConsolidatedReview instances."""

    def __init__(self) -> None:
        """Initialize the HTML report generator."""
        pass

    def generate(self, review: ConsolidatedReview) -> str:
        """Generate a complete standalone HTML document for the given review.

        Args:
            review: ConsolidatedReview model instance.

        Returns:
            Complete HTML5 document string with embedded styles and no external dependencies.
        """
        findings = sorted(review.findings, key=lambda f: f.priority_rank)

        # Compute summary metrics safely
        total_findings = len(findings)
        raw_max = review.risk_summary.get("max_risk_score")
        if raw_max is not None:
            try:
                max_risk = float(raw_max)
            except (ValueError, TypeError):
                max_risk = 0.0
        else:
            max_risk = max((f.risk_score for f in findings), default=0.0)

        raw_avg = review.risk_summary.get("average_risk_score")
        if raw_avg is not None:
            try:
                avg_risk = float(raw_avg)
            except (ValueError, TypeError):
                avg_risk = 0.0
        else:
            avg_risk = (
                sum(f.risk_score for f in findings) / total_findings
                if total_findings > 0
                else 0.0
            )

        dedup_count = review.risk_summary.get(
            "deduplicated_count",
            sum(1 for f in findings if f.is_deduplicated),
        )

        # Severity breakdown counts
        sev_dist = review.severity_distribution or {}
        crit_count = sev_dist.get("CRITICAL", 0) + sev_dist.get("critical", 0)
        high_count = sev_dist.get("HIGH", 0) + sev_dist.get("high", 0)
        med_count = sev_dist.get("MEDIUM", 0) + sev_dist.get("medium", 0)
        low_count = sev_dist.get("LOW", 0) + sev_dist.get("low", 0)
        info_count = sev_dist.get("INFO", 0) + sev_dist.get("info", 0)

        # Agent metrics breakdown
        agent_metrics = review.agent_metrics or {}
        by_role = agent_metrics.get("by_role", {})
        sec_metrics = by_role.get("SECURITY_AUDITOR", {})
        arch_metrics = by_role.get("SOFTWARE_ARCHITECT", {})

        sec_findings = sec_metrics.get("findings_count", 0)
        sec_time = sec_metrics.get("execution_time_ms", 0.0) / 1000.0
        arch_findings = arch_metrics.get("findings_count", 0)
        arch_time = arch_metrics.get("execution_time_ms", 0.0) / 1000.0

        # Render findings HTML
        findings_html = self._render_findings(findings)

        # Render agent summary HTML
        agents_html = self._render_agent_metrics(
            sec_findings, sec_time, arch_findings, arch_time, dedup_count
        )

        css_styles = self._get_embedded_css()

        html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Security Audit Report - {escape(review.review_id)}</title>
  <style>
{css_styles}
  </style>
</head>
<body>
  <div class="report-container">
    <!-- Header -->
    <header class="report-header">
      <div class="header-top">
        <div class="brand">
          <div class="brand-icon">🛡️</div>
          <div>
            <h1 class="brand-title">Automated Code Vulnerability Reviewer</h1>
            <p class="brand-subtitle">AST-Guided Multi-Agent Security & Architecture Audit Report</p>
          </div>
        </div>
        <div class="header-actions no-print">
          <button class="btn-print" onclick="window.print()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9V2h12v7M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
            Print / Save to PDF
          </button>
        </div>
      </div>

      <div class="meta-strip">
        <div class="meta-item">
          <span class="meta-label">Review ID:</span>
          <span class="meta-val font-mono">{escape(review.review_id)}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Target Repository / Path:</span>
          <span class="meta-val font-mono">{escape(review.repo_id)}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Scan Timestamp:</span>
          <span class="meta-val">{escape(str(review.created_at))}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Files Reviewed:</span>
          <span class="meta-val">{review.total_files_reviewed}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Chunks Inspected:</span>
          <span class="meta-val">{review.total_chunks_reviewed}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Status:</span>
          <span class="badge badge-status">{escape(review.status.upper())}</span>
        </div>
      </div>
    </header>

    <!-- Executive Summary Section -->
    <section class="section">
      <h2 class="section-title"><span>📊</span> Executive Summary</h2>
      
      <!-- Metrics Cards Grid -->
      <div class="metric-grid">
        <div class="metric-card metric-card-risk">
          <div class="metric-val">{max_risk:.1f}</div>
          <div class="metric-label">Max Risk Score (0-10)</div>
          <div class="metric-sub">Average: {avg_risk:.2f}</div>
        </div>
        <div class="metric-card">
          <div class="metric-val">{total_findings}</div>
          <div class="metric-label">Total Findings</div>
          <div class="metric-sub">{dedup_count} Deduplicated</div>
        </div>
        <div class="metric-card metric-card-critical">
          <div class="metric-val">{crit_count}</div>
          <div class="metric-label">Critical Vulnerabilities</div>
          <div class="metric-sub">Requires Immediate Action</div>
        </div>
        <div class="metric-card metric-card-high">
          <div class="metric-val">{high_count}</div>
          <div class="metric-label">High Severity Issues</div>
          <div class="metric-sub">Architectural / Exploit Risk</div>
        </div>
      </div>

      <!-- Severity Distribution Breakdown -->
      <div class="severity-breakdown-card">
        <h3 class="subsection-title">Severity Distribution</h3>
        <div class="sev-pill-row">
          <div class="sev-badge sev-badge-critical">
            <span class="sev-dot"></span> Critical: <strong>{crit_count}</strong>
          </div>
          <div class="sev-badge sev-badge-high">
            <span class="sev-dot"></span> High: <strong>{high_count}</strong>
          </div>
          <div class="sev-badge sev-badge-medium">
            <span class="sev-dot"></span> Medium: <strong>{med_count}</strong>
          </div>
          <div class="sev-badge sev-badge-low">
            <span class="sev-dot"></span> Low: <strong>{low_count}</strong>
          </div>
          <div class="sev-badge sev-badge-info">
            <span class="sev-dot"></span> Info: <strong>{info_count}</strong>
          </div>
        </div>
      </div>

      <!-- Agent Contributions -->
      {agents_html}
    </section>

    <!-- Prioritized Findings Section -->
    <section class="section">
      <div class="section-header-row">
        <h2 class="section-title"><span>🔍</span> Prioritized Audit Findings ({total_findings})</h2>
        <span class="text-muted">Ranked by Mathematical Risk Scoring Matrix</span>
      </div>

      <div class="findings-list">
        {findings_html}
      </div>
    </section>

    <!-- Advisory Guidance Disclaimer Banner (REQ-11) -->
    <footer class="advisory-banner">
      <div class="advisory-icon">⚠️</div>
      <div class="advisory-content">
        <h4>Advisory Guidance Disclaimer</h4>
        <p>
          AI-generated recommendations provide advisory architectural and security guidance.
          Automated suggestions must be evaluated and verified by qualified developers before deployment.
          No code alterations have been executed automatically.
        </p>
      </div>
    </footer>
  </div>
</body>
</html>"""
        return html_doc

    def save_to_file(self, review: ConsolidatedReview, file_path: Union[str, Path]) -> Path:
        """Render HTML report and write to file with UTF-8 encoding.

        Args:
            review: ConsolidatedReview model instance.
            file_path: Destination path for HTML file.

        Returns:
            Resolved Path of the written report.
        """
        dest = Path(file_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        html_content = self.generate(review)
        dest.write_text(html_content, encoding="utf-8")
        logger.info("Saved HTML audit report to %s", dest)
        return dest

    def _render_findings(self, findings: List[ModeratedFinding]) -> str:
        """Render finding cards HTML."""
        if not findings:
            return """<div class="empty-findings">
              <div class="empty-icon">✅</div>
              <p>No vulnerabilities or architectural defects discovered in this scan.</p>
            </div>"""

        cards = []
        for mf in findings:
            f = mf.finding
            rank = mf.priority_rank
            risk_score = mf.risk_score
            sev = f.severity.value.upper() if hasattr(f.severity, "value") else str(f.severity).upper()
            title = escape(f.title)
            category = escape(f.category or "General")
            cwe_tag = f"CWE-{escape(str(f.cwe_id))}" if f.cwe_id else None
            owasp_tag = escape(f.owasp_category) if f.owasp_category else None
            desc = escape(f.description)
            
            # Sources badges
            sources_list = [
                s.value if hasattr(s, "value") else str(s)
                for s in (mf.sources or ([f.agent_role] if f.agent_role else []))
            ]
            sources_str = ", ".join(sources_list)

            # Code evidence
            ev = f.evidence
            file_path = escape(ev.file_path) if ev else "Unknown file"
            start_line = ev.start_line if ev else 1
            end_line = ev.end_line if ev else 1
            snippet = ev.code_snippet if ev else ""

            code_lines_html = self._format_code_lines(snippet, start_line)

            # Remediation
            rem = f.remediation
            explanation = escape(rem.explanation) if rem and rem.explanation else "No explanation provided."
            recommended_fix = escape(rem.recommended_fix) if rem and rem.recommended_fix else ""
            refs = rem.references if rem and rem.references else []
            refs_html = ""
            if refs:
                ref_items = "".join(f"<li>{escape(r)}</li>" for r in refs)
                refs_html = f'<div class="remediation-refs"><strong>References:</strong><ul>{ref_items}</ul></div>'

            fix_block = ""
            if recommended_fix:
                fix_block = f"""<div class="remediation-fix-box">
                  <div class="fix-title">💡 Recommended Fix:</div>
                  <pre class="fix-code"><code>{recommended_fix}</code></pre>
                </div>"""

            dedup_badge = '<span class="badge badge-dedup">Deduplicated</span>' if mf.is_deduplicated else ""

            card_html = f"""
        <article class="finding-card sev-border-{sev.lower()}">
          <div class="finding-card-header">
            <div class="finding-header-left">
              <span class="badge badge-rank">#{rank}</span>
              <span class="badge badge-sev badge-sev-{sev.lower()}">{sev}</span>
              <span class="badge badge-score">Score: {risk_score:.1f}</span>
              {dedup_badge}
            </div>
            <div class="finding-location">
              <code>{file_path}:{start_line}-{end_line}</code>
            </div>
          </div>

          <h3 class="finding-title">{title}</h3>

          <div class="finding-tags">
            <span class="tag tag-category">{category}</span>
            {f'<span class="tag tag-cwe">{cwe_tag}</span>' if cwe_tag else ''}
            {f'<span class="tag tag-owasp">{owasp_tag}</span>' if owasp_tag else ''}
            <span class="tag tag-agent">Source: {escape(sources_str)}</span>
          </div>

          <p class="finding-desc">{desc}</p>

          <!-- Code Evidence -->
          <div class="evidence-container">
            <div class="evidence-header">
              <span>Code Evidence & Location</span>
              <span>Lines {start_line} &ndash; {end_line}</span>
            </div>
            <div class="code-box font-mono">
              {code_lines_html}
            </div>
          </div>

          <!-- Remediation Guidance -->
          <div class="remediation-container">
            <div class="remediation-header">
              <span>🛠️ Remediation Guidance</span>
            </div>
            <div class="remediation-body">
              <p class="remediation-explanation">{explanation}</p>
              {fix_block}
              {refs_html}
            </div>
          </div>
        </article>
            """
            cards.append(card_html)

        return "\n".join(cards)

    def _format_code_lines(self, snippet: str, start_line: int) -> str:
        """Format snippet into line-numbered code lines with escaped content."""
        if not snippet.strip():
            return '<div class="code-line"><span class="line-no">--</span><span class="line-content text-muted">No snippet provided</span></div>'

        lines = snippet.split("\n")
        rendered = []
        for idx, line in enumerate(lines):
            line_no = start_line + idx
            escaped_line = escape(line) or "&nbsp;"
            rendered.append(
                f'<div class="code-line"><span class="line-no">{line_no}</span><span class="line-content">{escaped_line}</span></div>'
            )
        return "".join(rendered)

    def _render_agent_metrics(
        self,
        sec_findings: int,
        sec_time: float,
        arch_findings: int,
        arch_time: float,
        dedup_count: int,
    ) -> str:
        """Render agent contributions metrics block."""
        return f"""
      <div class="agent-contributions-grid">
        <div class="agent-box">
          <div class="agent-box-header">
            <span>🛡️ Security Auditor</span>
            <span class="agent-role-pill">Vulnerability Engine</span>
          </div>
          <div class="agent-stats">
            <div>Findings: <strong>{sec_findings}</strong></div>
            <div>Time: <strong>{sec_time:.2f}s</strong></div>
          </div>
        </div>
        <div class="agent-box">
          <div class="agent-box-header">
            <span>📐 Software Architect</span>
            <span class="agent-role-pill">Design &amp; Resilience</span>
          </div>
          <div class="agent-stats">
            <div>Findings: <strong>{arch_findings}</strong></div>
            <div>Time: <strong>{arch_time:.2f}s</strong></div>
          </div>
        </div>
        <div class="agent-box">
          <div class="agent-box-header">
            <span>⚖️ Review Moderator</span>
            <span class="agent-role-pill">Deduplication &amp; Scoring</span>
          </div>
          <div class="agent-stats">
            <div>Deduplicated: <strong>{dedup_count}</strong></div>
            <div>Status: <strong>Consolidated</strong></div>
          </div>
        </div>
      </div>
        """

    def _get_embedded_css(self) -> str:
        """Return full offline-ready CSS styles embedded directly in HTML."""
        return """
    :root {
      --bg-base: #0f172a;
      --bg-surface: #1e293b;
      --bg-elevated: #334155;
      --border-subtle: #334155;
      --border-accent: #475569;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --accent-cyan: #38bdf8;
      --accent-indigo: #818cf8;
      --accent-green: #34d399;
      --accent-amber: #fbbf24;
      --sev-crit-bg: rgba(239, 68, 68, 0.15);
      --sev-crit-text: #f87171;
      --sev-crit-border: #ef4444;
      --sev-high-bg: rgba(249, 115, 22, 0.15);
      --sev-high-text: #fb923c;
      --sev-high-border: #f97316;
      --sev-med-bg: rgba(245, 158, 11, 0.15);
      --sev-med-text: #fbbf24;
      --sev-med-border: #f59e0b;
      --sev-low-bg: rgba(59, 130, 246, 0.15);
      --sev-low-text: #60a5fa;
      --sev-low-border: #3b82f6;
      --sev-info-bg: rgba(6, 182, 212, 0.15);
      --sev-info-text: #22d3ee;
      --sev-info-border: #06b6d4;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg-base);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
      padding: 2rem 1rem;
      font-size: 15px;
    }

    .report-container {
      max-width: 1100px;
      margin: 0 auto;
    }

    .font-mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }

    /* Header */
    .report-header {
      background-color: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 1.75rem;
      margin-bottom: 2rem;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }

    .header-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
      padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--border-subtle);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 1rem;
    }

    .brand-icon {
      font-size: 2.25rem;
    }

    .brand-title {
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--text-main);
      letter-spacing: -0.02em;
    }

    .brand-subtitle {
      font-size: 0.9rem;
      color: var(--text-muted);
    }

    .btn-print {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      background: linear-gradient(135deg, #4f46e5, #6366f1);
      color: #ffffff;
      border: none;
      padding: 0.6rem 1.1rem;
      border-radius: 8px;
      font-weight: 600;
      font-size: 0.85rem;
      cursor: pointer;
      transition: opacity 0.2s;
    }

    .btn-print:hover {
      opacity: 0.9;
    }

    .meta-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
    }

    .meta-item {
      display: flex;
      flex-direction: column;
      gap: 0.2rem;
    }

    .meta-label {
      font-size: 0.75rem;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-weight: 600;
    }

    .meta-val {
      font-size: 0.9rem;
      color: var(--text-main);
      word-break: break-all;
    }

    /* Sections */
    .section {
      background-color: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 1.75rem;
      margin-bottom: 2rem;
    }

    .section-title {
      font-size: 1.25rem;
      font-weight: 700;
      margin-bottom: 1.25rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      color: var(--text-main);
    }

    .section-header-row {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 1.25rem;
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .subsection-title {
      font-size: 0.95rem;
      color: var(--text-muted);
      margin-bottom: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .text-muted {
      color: var(--text-muted);
      font-size: 0.85rem;
    }

    /* Metric Grid */
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }

    .metric-card {
      background-color: var(--bg-base);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 1.25rem;
      text-align: center;
    }

    .metric-val {
      font-size: 2.25rem;
      font-weight: 800;
      color: var(--text-main);
      line-height: 1.1;
      margin-bottom: 0.35rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    .metric-label {
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 0.25rem;
    }

    .metric-sub {
      font-size: 0.75rem;
      color: var(--text-dim);
    }

    .metric-card-risk .metric-val {
      color: var(--accent-cyan);
    }

    .metric-card-critical .metric-val {
      color: var(--sev-crit-text);
    }

    .metric-card-high .metric-val {
      color: var(--sev-high-text);
    }

    /* Severity distribution pills */
    .severity-breakdown-card {
      background-color: var(--bg-base);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 1.25rem;
      margin-bottom: 1.5rem;
    }

    .sev-pill-row {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
    }

    .sev-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 0.85rem;
      border-radius: 20px;
      font-size: 0.85rem;
      font-weight: 500;
      border: 1px solid transparent;
    }

    .sev-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
    }

    .sev-badge-critical {
      background: var(--sev-crit-bg);
      color: var(--sev-crit-text);
      border-color: var(--sev-crit-border);
    }
    .sev-badge-critical .sev-dot { background: var(--sev-crit-border); }

    .sev-badge-high {
      background: var(--sev-high-bg);
      color: var(--sev-high-text);
      border-color: var(--sev-high-border);
    }
    .sev-badge-high .sev-dot { background: var(--sev-high-border); }

    .sev-badge-medium {
      background: var(--sev-med-bg);
      color: var(--sev-med-text);
      border-color: var(--sev-med-border);
    }
    .sev-badge-medium .sev-dot { background: var(--sev-med-border); }

    .sev-badge-low {
      background: var(--sev-low-bg);
      color: var(--sev-low-text);
      border-color: var(--sev-low-border);
    }
    .sev-badge-low .sev-dot { background: var(--sev-low-border); }

    .sev-badge-info {
      background: var(--sev-info-bg);
      color: var(--sev-info-text);
      border-color: var(--sev-info-border);
    }
    .sev-badge-info .sev-dot { background: var(--sev-info-border); }

    /* Agent contributions */
    .agent-contributions-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
    }

    .agent-box {
      background-color: var(--bg-base);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 1rem;
    }

    .agent-box-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
      font-weight: 600;
      font-size: 0.9rem;
    }

    .agent-role-pill {
      font-size: 0.7rem;
      background: var(--bg-elevated);
      padding: 0.2rem 0.5rem;
      border-radius: 6px;
      color: var(--text-muted);
    }

    .agent-stats {
      display: flex;
      justify-content: space-between;
      font-size: 0.82rem;
      color: var(--text-muted);
    }

    /* Finding Cards */
    .findings-list {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }

    .finding-card {
      background-color: var(--bg-base);
      border: 1px solid var(--border-subtle);
      border-left-width: 4px;
      border-radius: 10px;
      padding: 1.5rem;
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
    }

    .sev-border-critical { border-left-color: var(--sev-crit-border); }
    .sev-border-high { border-left-color: var(--sev-high-border); }
    .sev-border-medium { border-left-color: var(--sev-med-border); }
    .sev-border-low { border-left-color: var(--sev-low-border); }
    .sev-border-info { border-left-color: var(--sev-info-border); }

    .finding-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .finding-header-left {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      padding: 0.25rem 0.6rem;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .badge-rank {
      background: var(--bg-elevated);
      color: var(--text-main);
    }

    .badge-status {
      background: rgba(52, 211, 153, 0.2);
      color: var(--accent-green);
      font-size: 0.7rem;
      padding: 0.2rem 0.5rem;
    }

    .badge-sev-critical { background: var(--sev-crit-bg); color: var(--sev-crit-text); border: 1px solid var(--sev-crit-border); }
    .badge-sev-high { background: var(--sev-high-bg); color: var(--sev-high-text); border: 1px solid var(--sev-high-border); }
    .badge-sev-medium { background: var(--sev-med-bg); color: var(--sev-med-text); border: 1px solid var(--sev-med-border); }
    .badge-sev-low { background: var(--sev-low-bg); color: var(--sev-low-text); border: 1px solid var(--sev-low-border); }
    .badge-sev-info { background: var(--sev-info-bg); color: var(--sev-info-text); border: 1px solid var(--sev-info-border); }

    .badge-score {
      background: rgba(99, 102, 241, 0.2);
      color: #a5b4fc;
      border: 1px solid #6366f1;
    }

    .badge-dedup {
      background: rgba(148, 163, 184, 0.2);
      color: var(--text-muted);
      border: 1px dashed var(--text-dim);
    }

    .finding-location {
      font-size: 0.8rem;
      color: var(--text-muted);
      word-break: break-all;
    }

    .finding-title {
      font-size: 1.15rem;
      font-weight: 700;
      color: var(--text-main);
      margin-bottom: 0.5rem;
    }

    .finding-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
      margin-bottom: 0.85rem;
    }

    .tag {
      font-size: 0.75rem;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      font-weight: 600;
      background: var(--bg-surface);
      color: var(--text-muted);
      border: 1px solid var(--border-subtle);
    }

    .tag-cwe {
      color: #cbd5e1;
      border-color: #475569;
    }

    .tag-agent {
      color: var(--accent-cyan);
    }

    .finding-desc {
      font-size: 0.92rem;
      color: #e2e8f0;
      line-height: 1.6;
      margin-bottom: 1.25rem;
    }

    /* Evidence container */
    .evidence-container {
      background: #020617;
      border: 1px solid #1e293b;
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 1.25rem;
    }

    .evidence-header {
      background: #0f172a;
      padding: 0.5rem 1rem;
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      display: flex;
      justify-content: space-between;
      border-bottom: 1px solid #1e293b;
    }

    .code-box {
      padding: 0.75rem 0;
      overflow-x: auto;
      font-size: 0.85rem;
      line-height: 1.5;
    }

    .code-line {
      display: flex;
      padding: 0 1rem;
    }

    .code-line:hover {
      background: rgba(255, 255, 255, 0.03);
    }

    .line-no {
      min-width: 3.5rem;
      padding-right: 1rem;
      text-align: right;
      color: #475569;
      user-select: none;
      border-right: 1px solid #1e293b;
      margin-right: 1rem;
    }

    .line-content {
      color: #e2e8f0;
      white-space: pre-wrap;
      word-break: break-all;
    }

    /* Remediation */
    .remediation-container {
      background: rgba(16, 185, 129, 0.06);
      border: 1px solid rgba(16, 185, 129, 0.25);
      border-radius: 8px;
      padding: 1rem;
    }

    .remediation-header {
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--accent-green);
      margin-bottom: 0.5rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .remediation-explanation {
      font-size: 0.9rem;
      color: #e2e8f0;
      line-height: 1.5;
      margin-bottom: 0.75rem;
    }

    .remediation-fix-box {
      background: rgba(0, 0, 0, 0.3);
      border-left: 3px solid var(--accent-green);
      padding: 0.75rem 1rem;
      border-radius: 4px;
      margin-bottom: 0.5rem;
    }

    .fix-title {
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--accent-green);
      margin-bottom: 0.25rem;
    }

    .fix-code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.85rem;
      color: #a7f3d0;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .remediation-refs {
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-top: 0.5rem;
    }

    .remediation-refs ul {
      margin-left: 1.25rem;
      margin-top: 0.25rem;
    }

    /* Advisory Banner */
    .advisory-banner {
      background: rgba(245, 158, 11, 0.1);
      border: 1px solid rgba(245, 158, 11, 0.3);
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      display: flex;
      gap: 1rem;
      align-items: flex-start;
      margin-top: 2rem;
    }

    .advisory-icon {
      font-size: 1.5rem;
    }

    .advisory-content h4 {
      font-size: 0.95rem;
      color: var(--accent-amber);
      margin-bottom: 0.25rem;
      font-weight: 700;
    }

    .advisory-content p {
      font-size: 0.85rem;
      color: #cbd5e1;
      line-height: 1.5;
    }

    /* Print Stylesheet (@media print) */
    @media print {
      body {
        background-color: #ffffff !important;
        color: #111827 !important;
        padding: 0 !important;
        font-size: 12pt !important;
      }

      .no-print {
        display: none !important;
      }

      .report-header, .section, .finding-card, .metric-card, .severity-breakdown-card, .agent-box, .advisory-banner {
        background-color: #ffffff !important;
        color: #111827 !important;
        border: 1px solid #d1d5db !important;
        box-shadow: none !important;
      }

      .brand-title {
        color: #111827 !important;
      }

      .brand-subtitle, .meta-label, .meta-val, .metric-label, .metric-sub, .text-muted, .finding-desc, .remediation-explanation {
        color: #374151 !important;
      }

      .metric-val {
        color: #111827 !important;
      }

      .evidence-container {
        background: #f9fafb !important;
        border: 1px solid #d1d5db !important;
      }

      .evidence-header {
        background: #f3f4f6 !important;
        color: #4b5563 !important;
        border-bottom: 1px solid #d1d5db !important;
      }

      .line-no {
        color: #6b7280 !important;
        border-right: 1px solid #d1d5db !important;
      }

      .line-content {
        color: #111827 !important;
      }

      .remediation-container {
        background: #f0fdf4 !important;
        border: 1px solid #86efac !important;
      }

      .fix-code {
        color: #065f46 !important;
      }

      .finding-card {
        break-inside: avoid;
        page-break-inside: avoid;
        margin-bottom: 1.5rem !important;
      }

      .metric-card, .agent-box {
        break-inside: avoid;
        page-break-inside: avoid;
      }
    }
"""

