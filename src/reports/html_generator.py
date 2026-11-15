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
  <title>LOKI Security Audit Report - {escape(review.review_id)}</title>
  <style>
{css_styles}
  </style>
</head>
<body>
  <div class="report-container">
    <!-- Apple-grade Glass Header -->
    <header class="report-header">
      <div class="header-top">
        <div class="brand">
          <div class="brand-icon">⚡</div>
          <div>
            <h1 class="brand-title">LOKI <span style="font-weight: 400; opacity: 0.65;">|</span> Automated Code Vulnerability Reviewer</h1>
            <p class="brand-subtitle">AST-Guided Semantic Discovery &amp; Deterministic Multi-Agent Audit Report</p>
          </div>
        </div>
        <div class="header-actions no-print">
          <button class="btn-print" onclick="window.print()">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9V2h12v7M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
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
              <p>No security or architectural defects were detected in this scan.</p>
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
              <div class="evidence-header-left">
                <span class="mac-dot red"></span>
                <span class="mac-dot yellow"></span>
                <span class="mac-dot green"></span>
                <span class="evidence-path font-mono">{file_path}</span>
              </div>
              <span class="evidence-lines">Lines {start_line} &ndash; {end_line}</span>
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
      --apple-black: #050507;
      --bg-surface: rgba(18, 18, 22, 0.78);
      --bg-card: rgba(26, 26, 32, 0.65);
      --bg-elevated: rgba(36, 36, 44, 0.85);
      --border-subtle: rgba(255, 255, 255, 0.08);
      --border-hairline: rgba(255, 255, 255, 0.12);
      --text-main: #f5f5f7;
      --text-muted: #a1a1aa;
      --text-dim: #71717a;

      --apple-green: #30d158;
      --apple-cyan: #64d2ff;
      --apple-orange: #ff9f0a;
      --apple-red: #ff453a;
      --apple-yellow: #ffd60a;

      --sev-crit-bg: rgba(255, 69, 58, 0.14);
      --sev-crit-text: #ff453a;
      --sev-crit-border: rgba(255, 69, 58, 0.45);

      --sev-high-bg: rgba(255, 159, 10, 0.14);
      --sev-high-text: #ff9f0a;
      --sev-high-border: rgba(255, 159, 10, 0.45);

      --sev-med-bg: rgba(255, 214, 10, 0.14);
      --sev-med-text: #ffd60a;
      --sev-med-border: rgba(255, 214, 10, 0.4);

      --sev-low-bg: rgba(48, 209, 88, 0.14);
      --sev-low-text: #30d158;
      --sev-low-border: rgba(48, 209, 88, 0.4);

      --sev-info-bg: rgba(100, 210, 255, 0.14);
      --sev-info-text: #64d2ff;
      --sev-info-border: rgba(100, 210, 255, 0.35);

      --radius-sm: 8px;
      --radius-md: 14px;
      --radius-lg: 20px;
      --radius-pill: 9999px;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--apple-black);
      background-image:
        radial-gradient(ellipse at 50% 0%, rgba(48, 209, 88, 0.09) 0%, transparent 65%),
        radial-gradient(ellipse at 85% 30%, rgba(10, 132, 255, 0.05) 0%, transparent 50%);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Inter", -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
      padding: 2.5rem 1.25rem 5rem 1.25rem;
      font-size: 15px;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }

    .report-container {
      max-width: 1120px;
      margin: 0 auto;
    }

    .font-mono {
      font-family: "JetBrains Mono", SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }

    /* Apple Glass Header */
    .report-header {
      background: var(--bg-surface);
      border: 1px solid var(--border-hairline);
      border-radius: var(--radius-lg);
      padding: 2rem;
      margin-bottom: 2rem;
      box-shadow: inset 0 1px 1px 0 rgba(255, 255, 255, 0.14), 0 20px 48px -10px rgba(0, 0, 0, 0.7);
      backdrop-filter: blur(28px) saturate(180%);
      -webkit-backdrop-filter: blur(28px) saturate(180%);
      position: relative;
    }

    .report-header::before {
      content: "";
      position: absolute;
      top: 0;
      left: 15%;
      right: 15%;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.5), transparent);
      pointer-events: none;
    }

    .header-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--border-subtle);
      flex-wrap: wrap;
      gap: 1rem;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 1rem;
    }

    .brand-icon {
      width: 44px;
      height: 44px;
      border-radius: 12px;
      background: linear-gradient(135deg, rgba(48, 209, 88, 0.2) 0%, rgba(48, 209, 88, 0.05) 100%);
      border: 1px solid rgba(48, 209, 88, 0.4);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.4rem;
      color: var(--apple-green);
      box-shadow: 0 0 16px rgba(48, 209, 88, 0.25);
    }

    .brand-title {
      font-size: 1.45rem;
      font-weight: 700;
      color: #ffffff;
      letter-spacing: -0.03em;
      line-height: 1.2;
    }

    .brand-subtitle {
      font-size: 0.88rem;
      color: var(--text-muted);
      margin-top: 0.2rem;
    }

    /* Glisse Filled Glass Print Button */
    .btn-print {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      background: linear-gradient(180deg, #ffffff 0%, #ececf2 100%);
      color: #000000;
      border: 1px solid rgba(255, 255, 255, 0.95);
      padding: 0.65rem 1.35rem;
      border-radius: var(--radius-pill);
      font-weight: 600;
      font-size: 0.86rem;
      cursor: pointer;
      box-shadow: inset 0 1.5px 2px 0 #ffffff, inset 0 -1px 1px 0 rgba(0, 0, 0, 0.25), 0 4px 16px rgba(0, 0, 0, 0.4);
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      font-family: inherit;
    }

    .btn-print:hover {
      transform: translateY(-1.5px);
      box-shadow: inset 0 1.5px 2px 0 #ffffff, inset 0 -1px 1px 0 rgba(0, 0, 0, 0.3), 0 8px 24px rgba(255, 255, 255, 0.25);
    }

    .btn-print:active {
      transform: scale(0.98);
    }

    .meta-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 0.85rem;
    }

    .meta-item {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 0.65rem 0.85rem;
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }

    .meta-label {
      font-size: 0.72rem;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-weight: 600;
    }

    .meta-val {
      font-size: 0.86rem;
      color: var(--text-main);
      word-break: break-all;
      font-weight: 500;
    }

    /* Sections */
    .section {
      background: var(--bg-surface);
      border: 1px solid var(--border-hairline);
      border-radius: var(--radius-lg);
      padding: 2rem;
      margin-bottom: 2rem;
      box-shadow: inset 0 1px 1px 0 rgba(255, 255, 255, 0.1), 0 20px 48px -10px rgba(0, 0, 0, 0.65);
      backdrop-filter: blur(28px) saturate(180%);
      -webkit-backdrop-filter: blur(28px) saturate(180%);
    }

    .section-title {
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin-bottom: 1.25rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      color: #ffffff;
    }

    .section-header-row {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 1.5rem;
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .subsection-title {
      font-size: 0.82rem;
      color: var(--text-dim);
      margin-bottom: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 600;
    }

    .text-muted {
      color: var(--text-muted);
      font-size: 0.85rem;
    }

    /* Metric Grid (Apple Glass Cards) */
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }

    .metric-card {
      background: var(--bg-card);
      border: 1px solid var(--border-hairline);
      border-radius: var(--radius-md);
      padding: 1.5rem 1.25rem;
      text-align: left;
      position: relative;
      overflow: hidden;
      transition: all 0.2s ease;
    }

    .metric-card:hover {
      border-color: var(--border-hover);
      transform: translateY(-2px);
    }

    .metric-val {
      font-size: 2.75rem;
      font-weight: 800;
      color: #ffffff;
      line-height: 1.05;
      margin-bottom: 0.45rem;
      letter-spacing: -0.04em;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif;
    }

    .metric-label {
      font-size: 0.86rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 0.25rem;
    }

    .metric-sub {
      font-size: 0.76rem;
      color: var(--text-dim);
    }

    .metric-card-risk .metric-val {
      color: var(--apple-cyan);
      text-shadow: 0 0 20px rgba(100, 210, 255, 0.35);
    }

    .metric-card-critical .metric-val {
      color: var(--apple-red);
      text-shadow: 0 0 20px rgba(255, 69, 58, 0.35);
    }

    .metric-card-high .metric-val {
      color: var(--apple-orange);
      text-shadow: 0 0 20px rgba(255, 159, 10, 0.35);
    }

    /* Severity distribution pills */
    .severity-breakdown-card {
      background: var(--bg-card);
      border: 1px solid var(--border-hairline);
      border-radius: var(--radius-md);
      padding: 1.25rem 1.5rem;
      margin-bottom: 1.5rem;
    }

    .sev-pill-row {
      display: flex;
      flex-wrap: wrap;
      gap: 0.65rem;
    }

    .sev-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.45rem 0.95rem;
      border-radius: var(--radius-pill);
      font-size: 0.82rem;
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
    .sev-badge-critical .sev-dot { background: var(--sev-crit-text); box-shadow: 0 0 6px var(--sev-crit-text); }

    .sev-badge-high {
      background: var(--sev-high-bg);
      color: var(--sev-high-text);
      border-color: var(--sev-high-border);
    }
    .sev-badge-high .sev-dot { background: var(--sev-high-text); box-shadow: 0 0 6px var(--sev-high-text); }

    .sev-badge-medium {
      background: var(--sev-med-bg);
      color: var(--sev-med-text);
      border-color: var(--sev-med-border);
    }
    .sev-badge-medium .sev-dot { background: var(--sev-med-text); box-shadow: 0 0 6px var(--sev-med-text); }

    .sev-badge-low {
      background: var(--sev-low-bg);
      color: var(--sev-low-text);
      border-color: var(--sev-low-border);
    }
    .sev-badge-low .sev-dot { background: var(--sev-low-text); box-shadow: 0 0 6px var(--sev-low-text); }

    .sev-badge-info {
      background: var(--sev-info-bg);
      color: var(--sev-info-text);
      border-color: var(--sev-info-border);
    }
    .sev-badge-info .sev-dot { background: var(--sev-info-text); box-shadow: 0 0 6px var(--sev-info-text); }

    /* Agent contributions */
    .agent-contributions-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
    }

    .agent-box {
      background: var(--bg-card);
      border: 1px solid var(--border-hairline);
      border-radius: var(--radius-md);
      padding: 1.25rem;
      transition: all 0.2s ease;
    }

    .agent-box-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
      font-weight: 600;
      font-size: 0.9rem;
      color: #ffffff;
    }

    .agent-role-pill {
      font-size: 0.7rem;
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      padding: 0.2rem 0.55rem;
      border-radius: var(--radius-pill);
      color: var(--text-muted);
      font-weight: 500;
    }

    .agent-stats {
      display: flex;
      justify-content: space-between;
      font-size: 0.82rem;
      color: var(--text-muted);
    }

    .agent-stats strong {
      color: var(--text-main);
    }

    /* Finding Cards */
    .findings-list {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }

    .finding-card {
      background: var(--bg-card);
      border: 1px solid var(--border-hairline);
      border-left-width: 4px;
      border-radius: var(--radius-md);
      padding: 1.75rem;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
      transition: transform 0.2s ease;
    }

    .sev-border-critical { border-left-color: var(--apple-red); }
    .sev-border-high { border-left-color: var(--apple-orange); }
    .sev-border-medium { border-left-color: var(--apple-yellow); }
    .sev-border-low { border-left-color: var(--apple-green); }
    .sev-border-info { border-left-color: var(--apple-cyan); }

    .finding-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.85rem;
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
      padding: 0.25rem 0.65rem;
      border-radius: var(--radius-pill);
      font-size: 0.74rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .badge-rank {
      background: rgba(255, 255, 255, 0.08);
      color: #ffffff;
      border: 1px solid var(--border-hairline);
    }

    .badge-status {
      background: rgba(48, 209, 88, 0.15);
      color: var(--apple-green);
      font-size: 0.72rem;
      padding: 0.2rem 0.65rem;
      border: 1px solid rgba(48, 209, 88, 0.35);
    }

    .badge-sev-critical { background: var(--sev-crit-bg); color: var(--sev-crit-text); border: 1px solid var(--sev-crit-border); }
    .badge-sev-high { background: var(--sev-high-bg); color: var(--sev-high-text); border: 1px solid var(--sev-high-border); }
    .badge-sev-medium { background: var(--sev-med-bg); color: var(--sev-med-text); border: 1px solid var(--sev-med-border); }
    .badge-sev-low { background: var(--sev-low-bg); color: var(--sev-low-text); border: 1px solid var(--sev-low-border); }
    .badge-sev-info { background: var(--sev-info-bg); color: var(--sev-info-text); border: 1px solid var(--sev-info-border); }

    .badge-score {
      background: rgba(10, 132, 255, 0.15);
      color: var(--apple-blue);
      border: 1px solid rgba(10, 132, 255, 0.4);
    }

    .badge-dedup {
      background: rgba(255, 255, 255, 0.06);
      color: var(--text-muted);
      border: 1px dashed var(--text-dim);
    }

    .finding-location {
      font-size: 0.82rem;
      color: var(--text-muted);
      word-break: break-all;
    }

    .finding-location code {
      background: rgba(255, 255, 255, 0.04);
      padding: 0.2rem 0.5rem;
      border-radius: 6px;
      border: 1px solid var(--border-subtle);
    }

    .finding-title {
      font-size: 1.2rem;
      font-weight: 700;
      color: #ffffff;
      letter-spacing: -0.02em;
      margin-bottom: 0.65rem;
    }

    .finding-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 0.45rem;
      margin-bottom: 1rem;
    }

    .tag {
      font-size: 0.74rem;
      padding: 0.2rem 0.55rem;
      border-radius: var(--radius-pill);
      font-weight: 500;
      background: rgba(255, 255, 255, 0.04);
      color: var(--text-muted);
      border: 1px solid var(--border-subtle);
    }

    .tag-cwe {
      color: #ffffff;
      background: rgba(255, 255, 255, 0.08);
      border-color: var(--border-hairline);
      font-weight: 600;
    }

    .tag-agent {
      color: var(--apple-cyan);
      border-color: rgba(100, 210, 255, 0.25);
    }

    .finding-desc {
      font-size: 0.94rem;
      color: #e4e4e7;
      line-height: 1.6;
      margin-bottom: 1.25rem;
    }

    /* macOS Style Evidence Terminal */
    .evidence-container {
      background: #000000;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 12px;
      overflow: hidden;
      margin-bottom: 1.25rem;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    }

    .evidence-header {
      background: rgba(255, 255, 255, 0.04);
      padding: 0.6rem 1rem;
      font-size: 0.78rem;
      font-weight: 500;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }

    .evidence-header-left {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .mac-dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      display: inline-block;
    }
    .mac-dot.red { background: #ff5f56; }
    .mac-dot.yellow { background: #ffbd2e; }
    .mac-dot.green { background: #27c93f; }

    .evidence-path {
      color: #ffffff;
      font-size: 0.78rem;
      margin-left: 4px;
    }

    .evidence-lines {
      color: var(--text-dim);
      font-size: 0.75rem;
    }

    .code-box {
      padding: 0.85rem 0;
      overflow-x: auto;
      font-size: 0.85rem;
      line-height: 1.55;
    }

    .code-line {
      display: flex;
      padding: 0 1rem;
    }

    .code-line:hover {
      background: rgba(255, 255, 255, 0.04);
    }

    .line-no {
      min-width: 3.5rem;
      padding-right: 1rem;
      text-align: right;
      color: #52525b;
      user-select: none;
      border-right: 1px solid rgba(255, 255, 255, 0.08);
      margin-right: 1rem;
    }

    .line-content {
      color: #f4f4f5;
      white-space: pre-wrap;
      word-break: break-all;
    }

    /* Apple Remediation Box */
    .remediation-container {
      background: rgba(48, 209, 88, 0.05);
      border: 1px solid rgba(48, 209, 88, 0.22);
      border-radius: 12px;
      padding: 1.25rem;
    }

    .remediation-header {
      font-size: 0.82rem;
      font-weight: 700;
      color: var(--apple-green);
      margin-bottom: 0.5rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .remediation-explanation {
      font-size: 0.9rem;
      color: #e4e4e7;
      line-height: 1.5;
      margin-bottom: 0.75rem;
    }

    .remediation-fix-box {
      background: rgba(0, 0, 0, 0.4);
      border-left: 3px solid var(--apple-green);
      padding: 0.75rem 1rem;
      border-radius: 6px;
      margin-bottom: 0.5rem;
    }

    .fix-title {
      font-size: 0.78rem;
      font-weight: 600;
      color: var(--apple-green);
      margin-bottom: 0.25rem;
    }

    .fix-code {
      font-family: "JetBrains Mono", SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.84rem;
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

    .empty-findings {
      text-align: center;
      padding: 3rem 1.5rem;
      color: var(--text-muted);
    }

    .empty-icon {
      font-size: 2.5rem;
      margin-bottom: 0.75rem;
    }

    /* Advisory Banner */
    .advisory-banner {
      background: rgba(255, 159, 10, 0.07);
      border: 1px solid rgba(255, 159, 10, 0.28);
      border-radius: var(--radius-md);
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
      font-size: 0.92rem;
      color: var(--apple-orange);
      margin-bottom: 0.25rem;
      font-weight: 700;
    }

    .advisory-content p {
      font-size: 0.85rem;
      color: #d4d4d8;
      line-height: 1.5;
    }

    /* Print Stylesheet (@media print) */
    @media print {
      body {
        background: #ffffff !important;
        color: #111827 !important;
        padding: 0 !important;
        font-size: 11pt !important;
      }

      .no-print {
        display: none !important;
      }

      .report-header, .section, .finding-card, .metric-card, .severity-breakdown-card, .agent-box, .advisory-banner {
        background: #ffffff !important;
        color: #111827 !important;
        border: 1px solid #e5e7eb !important;
        box-shadow: none !important;
        border-radius: 8px !important;
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
        border: 1px solid #e5e7eb !important;
      }

      .evidence-header {
        background: #f3f4f6 !important;
        color: #4b5563 !important;
        border-bottom: 1px solid #e5e7eb !important;
      }

      .line-no {
        color: #6b7280 !important;
        border-right: 1px solid #e5e7eb !important;
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
        margin-bottom: 1.25rem !important;
      }

      .metric-card, .agent-box {
        break-inside: avoid;
        page-break-inside: avoid;
      }
    }
"""

