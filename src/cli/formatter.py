"""Rich terminal output formatting utilities for code vulnerability review reports."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from src.core.models import (
    AgentRoleEnum,
    ConsolidatedReview,
    ModeratedFinding,
    SeverityEnum,
)

SEVERITY_STYLES: Dict[SeverityEnum, str] = {
    SeverityEnum.CRITICAL: "bold white on red",
    SeverityEnum.HIGH: "bold red",
    SeverityEnum.MEDIUM: "bold yellow",
    SeverityEnum.LOW: "bold cyan",
    SeverityEnum.INFO: "dim cyan",
}

SEVERITY_ORDER: Dict[SeverityEnum, int] = {
    SeverityEnum.CRITICAL: 5,
    SeverityEnum.HIGH: 4,
    SeverityEnum.MEDIUM: 3,
    SeverityEnum.LOW: 2,
    SeverityEnum.INFO: 1,
}

LEXER_MAP: Dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
}


class CLIFormatter:
    """Renders scan results, severity badges, tables, and finding cards for terminal display."""

    def __init__(self, console: Optional[Console] = None) -> None:
        """Initialize formatter with Rich console instance."""
        self.console = console or Console()

    def format_severity_badge(self, severity: SeverityEnum) -> Text:
        """Return styled Rich Text badge for vulnerability severity.

        Args:
            severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO).

        Returns:
            Rich Text badge formatted with distinct severity colors.
        """
        style = SEVERITY_STYLES.get(severity, "bold white")
        badge = Text(f" {severity.value} ", style=style)
        return badge

    def _detect_lexer(self, file_path: str) -> str:
        """Detect syntax lexer from file extension."""
        ext = Path(file_path).suffix.lower()
        return LEXER_MAP.get(ext, "python")

    def format_finding_card(self, finding: ModeratedFinding) -> Panel:
        """Format an individual moderated finding into a detailed Rich Panel card.

        Includes rank, severity badge, risk score, CWE metadata, code evidence snippet,
        and advisory remediation guidance.

        Args:
            finding: The arbitrated finding to format.

        Returns:
            Rich Panel component containing styled sections.
        """
        f = finding.finding
        badge = self.format_severity_badge(f.severity)

        # Header title
        title_text = Text()
        title_text.append(f"#{finding.priority_rank} ", style="bold white")
        title_text.append_text(badge)
        title_text.append(f" Score: {finding.risk_score:.1f} ", style="bold magenta")
        title_text.append(f"│ {f.title}", style="bold")

        body_elements: List[Any] = []

        # Metadata Section
        meta_table = Table.grid(padding=(0, 2))
        meta_table.add_column(style="bold cyan", justify="right")
        meta_table.add_column(style="white")

        source_names = ", ".join(s.value for s in (finding.sources or [f.agent_role]))
        meta_table.add_row("Agents:", source_names)
        meta_table.add_row("Category:", f.category)

        cwe_owasp = []
        if f.cwe_id:
            cwe_owasp.append(f.cwe_id)
        if f.owasp_category:
            cwe_owasp.append(f.owasp_category)
        if cwe_owasp:
            meta_table.add_row("Standards:", " │ ".join(cwe_owasp))

        loc_str = f"{f.evidence.file_path}:{f.evidence.start_line}-{f.evidence.end_line}"
        meta_table.add_row("Location:", loc_str)

        if finding.arbitration_notes:
            meta_table.add_row("Arbitration:", finding.arbitration_notes)

        body_elements.append(meta_table)
        body_elements.append(Text("\nDescription:", style="bold yellow"))
        body_elements.append(Text(f.description, style="white"))

        # Code Evidence Snippet
        snippet = f.evidence.code_snippet.strip()
        if snippet:
            lexer = self._detect_lexer(f.evidence.file_path)
            syntax = Syntax(
                f.evidence.code_snippet,
                lexer=lexer,
                line_numbers=True,
                start_line=max(1, f.evidence.start_line),
                word_wrap=True,
            )
            body_elements.append(
                Panel(
                    syntax,
                    title=f"[cyan]Code Evidence ({loc_str})[/cyan]",
                    border_style="dim",
                )
            )

        # Remediation Section
        remediation_text = Text()
        remediation_text.append("Explanation: ", style="bold green")
        remediation_text.append(f"{f.remediation.explanation}\n")
        remediation_text.append("Recommended Fix: ", style="bold green")
        remediation_text.append(f"{f.remediation.recommended_fix}")

        if f.remediation.references:
            remediation_text.append("\nReferences:\n", style="bold green")
            for ref in f.remediation.references:
                remediation_text.append(f" • {ref}\n", style="dim")

        body_elements.append(
            Panel(
                remediation_text,
                title="[green]Actionable Remediation Guidance[/green]",
                border_style="green",
            )
        )

        # Advisory Disclaimer Note
        if f.is_advisory_only:
            body_elements.append(
                Text(
                    "Note: Purely advisory recommendation. Requires human engineer evaluation.",
                    style="italic dim yellow",
                )
            )

        border_color = "red" if f.severity in (SeverityEnum.CRITICAL, SeverityEnum.HIGH) else "yellow"
        if f.severity in (SeverityEnum.LOW, SeverityEnum.INFO):
            border_color = "cyan"

        return Panel(
            Group(*body_elements),
            title=title_text,
            border_style=border_color,
            padding=(1, 2),
        )

    def format_findings_table(
        self,
        findings: List[ModeratedFinding],
        min_severity: Optional[SeverityEnum] = None,
    ) -> Table:
        """Create a summary table of findings filtered by optional minimum severity.

        Args:
            findings: List of ModeratedFinding items.
            min_severity: Optional cutoff severity (CRITICAL, HIGH, MEDIUM, LOW, INFO).

        Returns:
            Rich Table containing ranked findings overview.
        """
        table = Table(
            title="Automated Vulnerability & Architecture Findings",
            header_style="bold cyan",
            show_header=True,
            expand=True,
        )

        table.add_column("#", justify="right", style="bold", width=4)
        table.add_column("Severity", justify="center", width=12)
        table.add_column("Score", justify="right", style="magenta", width=7)
        table.add_column("Title", style="white", ratio=3)
        table.add_column("CWE / Category", style="dim", ratio=2)
        table.add_column("Location", style="cyan", ratio=2)
        table.add_column("Agents", style="dim", ratio=2)

        min_level = SEVERITY_ORDER.get(min_severity, 0) if min_severity else 0

        displayed_count = 0
        for item in findings:
            item_level = SEVERITY_ORDER.get(item.finding.severity, 0)
            if item_level < min_level:
                continue

            f = item.finding
            badge = self.format_severity_badge(f.severity)
            loc = f"{f.evidence.file_path}:{f.evidence.start_line}"
            if len(loc) > 40:
                loc = "..." + loc[-37:]

            cwe_or_cat = f.cwe_id if f.cwe_id else f.category
            sources = ", ".join(s.value.split("_")[0] for s in (item.sources or [f.agent_role]))

            table.add_row(
                str(item.priority_rank),
                badge,
                f"{item.risk_score:.1f}",
                f.title,
                cwe_or_cat,
                loc,
                sources,
            )
            displayed_count += 1

        if displayed_count == 0:
            table.add_row("-", Text("None", style="dim"), "-", "No matching findings detected", "-", "-", "-")

        return table

    def format_summary_panel(self, review: ConsolidatedReview) -> Panel:
        """Generate high-level summary metrics card.

        Args:
            review: ConsolidatedReview report.

        Returns:
            Rich Panel displaying total metrics, severity breakdown, and disclaimer.
        """
        summary_grid = Table.grid(padding=(0, 2))
        summary_grid.add_column(style="bold white", justify="right")
        summary_grid.add_column(style="cyan")
        summary_grid.add_column(style="bold white", justify="right")
        summary_grid.add_column(style="white")

        total_findings = len(review.findings)
        max_score = review.risk_summary.get("max_risk_score", 0.0)
        avg_score = review.risk_summary.get("average_risk_score", 0.0)

        summary_grid.add_row(
            "Review ID:",
            review.review_id,
            "Total Files:",
            str(review.total_files_reviewed),
        )
        summary_grid.add_row(
            "Repository ID:",
            review.repo_id,
            "Total Chunks:",
            str(review.total_chunks_reviewed),
        )
        summary_grid.add_row(
            "Total Findings:",
            f"{total_findings} detected",
            "Peak Risk Score:",
            f"{max_score:.1f} / 10.0",
        )
        summary_grid.add_row(
            "Status:",
            review.status.upper(),
            "Avg Risk Score:",
            f"{avg_score:.1f} / 10.0",
        )

        # Severity breakdown badges
        sev_counts = review.severity_distribution or {}
        sev_text = Text("\nSeverity Breakdown:  ")
        for sev in [
            SeverityEnum.CRITICAL,
            SeverityEnum.HIGH,
            SeverityEnum.MEDIUM,
            SeverityEnum.LOW,
            SeverityEnum.INFO,
        ]:
            count = sev_counts.get(sev.value, 0)
            badge = self.format_severity_badge(sev)
            sev_text.append_text(badge)
            sev_text.append(f" {count}   ")

        disclaimer_text = Text(
            f"\n\n[ADVISORY DISCLAIMER]\n{review.advisory_disclaimer}",
            style="italic dim yellow",
        )

        content = Group(summary_grid, sev_text, disclaimer_text)
        panel_color = "red" if sev_counts.get("CRITICAL", 0) > 0 else "blue"

        return Panel(
            content,
            title="[bold white]Review Execution Summary[/bold white]",
            border_style=panel_color,
            padding=(1, 2),
        )

    def format_json_output(self, review: ConsolidatedReview) -> str:
        """Serialize review to formatted JSON string.

        Args:
            review: ConsolidatedReview report.

        Returns:
            Indented JSON representation.
        """
        return review.model_dump_json(indent=2)

