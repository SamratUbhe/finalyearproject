"""Server-side Academic & Professional Audit PDF Report Generator using ReportLab."""

import io
from pathlib import Path
from typing import List, Optional
import xml.sax.saxutils

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.core.models import (
    AgentRoleEnum,
    ConsolidatedReview,
    ModeratedFinding,
    SeverityEnum,
)


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas that accumulates pages and renders running headers/footers with 'Page X of Y'."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_decorations(self, page_count: int):
        self.saveState()

        # Running Top Header (pages 2 and higher)
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#475569"))
            self.drawString(
                54,
                750,
                "LOKI | Multi-Agent Security & Architecture Audit Report",
            )
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(54, 744, 558, 744)

        # Running Footer (all pages)
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(54, 45, 558, 45)

        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#64748b"))
        self.drawString(
            54,
            33,
            "LOKI ADVISORY GUIDANCE (REQ-11): Automated AI inspection findings require qualified developer verification.",
        )

        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 33, page_str)

        self.restoreState()


class PDFReportGenerator:
    """Compiles structured ConsolidatedReview models into publication-ready PDF audit documents."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Define project typography and paragraph styles."""
        self.styles.add(
            ParagraphStyle(
                name="ReportTitle",
                fontName="Helvetica-Bold",
                fontSize=20,
                leading=24,
                textColor=colors.HexColor("#0f172a"),
                alignment=0,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="ReportSubtitle",
                fontName="Helvetica",
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#64748b"),
                alignment=0,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="SectionHeading",
                fontName="Helvetica-Bold",
                fontSize=13,
                leading=17,
                textColor=colors.HexColor("#0f172a"),
                spaceBefore=10,
                spaceAfter=6,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="FindingCardTitle",
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=15,
                textColor=colors.HexColor("#0f172a"),
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="FindingMeta",
                fontName="Helvetica",
                fontSize=8.5,
                leading=12,
                textColor=colors.HexColor("#475569"),
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="FindingDesc",
                fontName="Helvetica",
                fontSize=8.5,
                leading=12,
                textColor=colors.HexColor("#1e293b"),
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="RemediationText",
                fontName="Helvetica",
                fontSize=8.5,
                leading=12,
                textColor=colors.HexColor("#065f46"),
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="DisclaimerText",
                fontName="Helvetica",
                fontSize=8,
                leading=11.5,
                textColor=colors.HexColor("#92400e"),
            )
        )

    def _get_severity_colors(self, severity: SeverityEnum):
        """Map severity levels to primary text and background colors."""
        sev = str(severity).upper() if hasattr(severity, "value") else str(severity).upper()
        if sev == "CRITICAL":
            return colors.HexColor("#dc2626"), colors.HexColor("#fee2e2")
        elif sev == "HIGH":
            return colors.HexColor("#ea580c"), colors.HexColor("#ffedd5")
        elif sev == "MEDIUM":
            return colors.HexColor("#d97706"), colors.HexColor("#fef3c7")
        elif sev == "LOW":
            return colors.HexColor("#0284c7"), colors.HexColor("#e0f2fe")
        return colors.HexColor("#4b5563"), colors.HexColor("#f3f4f6")

    def generate(
        self, review: ConsolidatedReview, output_path: Optional[Path] = None
    ) -> bytes:
        """Compile a ConsolidatedReview into PDF binary bytes.

        Args:
            review: ConsolidatedReview data model.
            output_path: Optional path to save the generated PDF file directly.

        Returns:
            bytes of the compiled PDF document.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=54,
            bottomMargin=54,
        )

        story = []

        # 1. Document Header
        story.append(Paragraph("LOKI: Automated Code Vulnerability Review", self.styles["ReportTitle"]))
        story.append(
            Paragraph(
                "Multi-Agent AST-Guided Vulnerability & Architectural Resilience Audit Report",
                self.styles["ReportSubtitle"],
            )
        )
        story.append(Spacer(1, 10))

        # 2. Metadata Table Block
        risk_summary = review.risk_summary or {}
        max_risk = float(risk_summary.get("max_risk_score", 0.0))
        avg_risk = float(risk_summary.get("average_risk_score", 0.0))
        dedup_count = risk_summary.get("deduplicated_count", 0)

        meta_data = [
            [
                Paragraph("<b>Review ID:</b>", self.styles["FindingMeta"]),
                Paragraph(f"<code>{review.review_id}</code>", self.styles["FindingMeta"]),
                Paragraph("<b>Date & Time:</b>", self.styles["FindingMeta"]),
                Paragraph(
                    f"{review.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if hasattr(review.created_at, 'strftime') else str(review.created_at)}",
                    self.styles["FindingMeta"],
                ),
            ],
            [
                Paragraph("<b>Target Repository:</b>", self.styles["FindingMeta"]),
                Paragraph(f"<b>{xml.sax.saxutils.escape(review.repo_id)}</b>", self.styles["FindingMeta"]),
                Paragraph("<b>Overall Risk Score:</b>", self.styles["FindingMeta"]),
                Paragraph(
                    f"<b>{max_risk:.2f} / 10.0</b>",
                    self.styles["FindingMeta"],
                ),
            ],
            [
                Paragraph("<b>Total Findings:</b>", self.styles["FindingMeta"]),
                Paragraph(f"{len(review.findings)} issues identified", self.styles["FindingMeta"]),
                Paragraph("<b>Chunks Reviewed:</b>", self.styles["FindingMeta"]),
                Paragraph(f"{review.total_chunks_reviewed} syntax blocks", self.styles["FindingMeta"]),
            ],
        ]

        meta_table = Table(meta_data, colWidths=[100, 150, 110, 144])
        meta_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(meta_table)
        story.append(Spacer(1, 12))

        # 3. Advisory Disclaimer Callout (REQ-11)
        disclaimer_data = [[
            Paragraph(
                "<b>HUMAN-IN-THE-LOOP ADVISORY DISCLAIMER (REQ-11):</b> "
                "This report provides automated architectural and security guidance generated by specialized LLM agents. "
                "Findings and proposed remediation patches are strictly advisory and must be reviewed and tested by qualified developers before production deployment.",
                self.styles["DisclaimerText"],
            )
        ]]
        disclaimer_table = Table(disclaimer_data, colWidths=[504])
        disclaimer_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#f59e0b")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        story.append(disclaimer_table)
        story.append(Spacer(1, 12))

        # 4. Executive Summary Section
        story.append(Paragraph("Executive Summary & Severity Distribution", self.styles["SectionHeading"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceBefore=2, spaceAfter=8))

        dist = review.severity_distribution or {}
        summary_data = [
            [
                Paragraph("<b>Severity Level</b>", self.styles["FindingMeta"]),
                Paragraph("<b>Count</b>", self.styles["FindingMeta"]),
                Paragraph("<b>Multi-Agent Findings Breakdown</b>", self.styles["FindingMeta"]),
                Paragraph("<b>Reviewer Engine Stats</b>", self.styles["FindingMeta"]),
            ],
            [
                Paragraph("<font color='#dc2626'><b>CRITICAL</b></font>", self.styles["FindingMeta"]),
                Paragraph(f"<b>{dist.get('CRITICAL', dist.get('critical', 0))}</b>", self.styles["FindingMeta"]),
                Paragraph(
                    f"Security Auditor Findings: {sum(1 for f in review.findings if AgentRoleEnum.SECURITY_AUDITOR in f.sources or 'security_auditor' in [str(s).lower() for s in f.sources])}",
                    self.styles["FindingMeta"],
                ),
                Paragraph(f"Deduplicated Duplicates: {dedup_count}", self.styles["FindingMeta"]),
            ],
            [
                Paragraph("<font color='#ea580c'><b>HIGH</b></font>", self.styles["FindingMeta"]),
                Paragraph(f"<b>{dist.get('HIGH', dist.get('high', 0))}</b>", self.styles["FindingMeta"]),
                Paragraph(
                    f"Software Architect Findings: {sum(1 for f in review.findings if AgentRoleEnum.SOFTWARE_ARCHITECT in f.sources or 'software_architect' in [str(s).lower() for s in f.sources])}",
                    self.styles["FindingMeta"],
                ),
                Paragraph(f"Status: {review.status.upper()}", self.styles["FindingMeta"]),
            ],
            [
                Paragraph("<font color='#d97706'><b>MEDIUM</b></font>", self.styles["FindingMeta"]),
                Paragraph(f"<b>{dist.get('MEDIUM', dist.get('medium', 0))}</b>", self.styles["FindingMeta"]),
                Paragraph(f"Average Risk Score: {avg_risk:.2f}", self.styles["FindingMeta"]),
                Paragraph("Language Scope: Python, JS/TS", self.styles["FindingMeta"]),
            ],
            [
                Paragraph("<font color='#0284c7'><b>LOW / INFO</b></font>", self.styles["FindingMeta"]),
                Paragraph(f"<b>{dist.get('LOW', dist.get('low', 0)) + dist.get('INFO', dist.get('info', 0))}</b>", self.styles["FindingMeta"]),
                Paragraph("AST ASTScope Context Engine: Active", self.styles["FindingMeta"]),
                Paragraph("Gemini LLM Parallel Dispatch: OK", self.styles["FindingMeta"]),
            ],
        ]

        summary_table = Table(summary_data, colWidths=[90, 60, 180, 174])
        summary_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(summary_table)
        story.append(Spacer(1, 14))

        # 5. Prioritized Findings Detail Section
        story.append(Paragraph("Prioritized Security & Architectural Findings", self.styles["SectionHeading"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceBefore=2, spaceAfter=10))

        if not review.findings:
            no_findings = [
                [
                    Paragraph(
                        "<b>✅ No vulnerabilities or architectural defects were detected across reviewed modules.</b>",
                        self.styles["FindingDesc"],
                    )
                ]
            ]
            t = Table(no_findings, colWidths=[504])
            t.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#86efac")),
                    ("PADDING", (0, 0), (-1, -1), 10),
                ])
            )
            story.append(t)
        else:
            sorted_findings = sorted(review.findings, key=lambda f: f.priority_rank)
            for finding in sorted_findings:
                card_elements = self._build_finding_card(finding)
                story.append(KeepTogether(card_elements))
                story.append(Spacer(1, 8))

        doc.build(story, canvasmaker=NumberedCanvas)

        pdf_bytes = buffer.getvalue()
        buffer.close()

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(pdf_bytes)

        return pdf_bytes

    def _build_finding_card(self, finding: ModeratedFinding) -> List:
        """Render a single finding card flowable block."""
        inner = finding.finding
        ev = inner.evidence
        rem = inner.remediation

        text_color, bg_color = self._get_severity_colors(inner.severity)
        sev_str = str(inner.severity).upper() if hasattr(inner.severity, "value") else str(inner.severity).upper()

        card_flowables = []

        # Card Title Header Table
        title_text = f"<b>#{finding.priority_rank} [{sev_str}] {xml.sax.saxutils.escape(inner.title)}</b>"
        cwe_str = inner.cwe_id or "Architectural"
        cwe_text = f"<b>{cwe_str}</b> | Score: <b>{finding.risk_score:.1f}</b>"

        header_table = Table(
            [[
                Paragraph(f"<font color='{text_color.hexval()}'>{title_text}</font>", self.styles["FindingCardTitle"]),
                Paragraph(f"<font color='#475569'>{cwe_text}</font>", self.styles["FindingMeta"]),
            ]],
            colWidths=[370, 134],
        )
        header_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), bg_color),
                ("BOX", (0, 0), (-1, -1), 0.5, text_color),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ])
        )
        card_flowables.append(header_table)

        # Details Table
        sources_str = ", ".join(s.value if hasattr(s, "value") else str(s) for s in finding.sources)
        loc_str = f"{ev.file_path}:{ev.start_line}-{ev.end_line}"

        meta_rows = [
            [
                Paragraph("<b>Location:</b>", self.styles["FindingMeta"]),
                Paragraph(f"<code>{xml.sax.saxutils.escape(loc_str)}</code>", self.styles["FindingMeta"]),
                Paragraph("<b>Agent Source:</b>", self.styles["FindingMeta"]),
                Paragraph(xml.sax.saxutils.escape(sources_str), self.styles["FindingMeta"]),
            ],
            [
                Paragraph("<b>Category:</b>", self.styles["FindingMeta"]),
                Paragraph(xml.sax.saxutils.escape(inner.category or "General"), self.styles["FindingMeta"]),
                Paragraph("<b>Confidence:</b>", self.styles["FindingMeta"]),
                Paragraph(str(inner.confidence).upper() if hasattr(inner.confidence, "value") else str(inner.confidence), self.styles["FindingMeta"]),
            ],
        ]

        if inner.description:
            meta_rows.append([
                Paragraph("<b>Description:</b>", self.styles["FindingMeta"]),
                Paragraph(xml.sax.saxutils.escape(inner.description), self.styles["FindingDesc"]),
                Paragraph("", self.styles["FindingMeta"]),
                Paragraph("", self.styles["FindingMeta"]),
            ])

        details_table = Table(meta_rows, colWidths=[65, 185, 75, 179])
        details_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("SPAN", (1, 2), (3, 2)) if inner.description else ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ])
        )
        card_flowables.append(details_table)

        # Code Evidence Box (if snippet exists)
        if ev.code_snippet and ev.code_snippet.strip():
            snippet = ev.code_snippet.strip()
            # truncate snippet if exceptionally long to fit on page
            lines = snippet.splitlines()
            if len(lines) > 12:
                snippet = "\n".join(lines[:12]) + f"\n... [{len(lines) - 12} additional lines truncated]"

            code_flowable = Preformatted(
                snippet,
                ParagraphStyle(
                    name="CodeSnippet",
                    fontName="Courier",
                    fontSize=7.5,
                    leading=9.5,
                    textColor=colors.HexColor("#0f172a"),
                ),
            )
            code_table = Table([[code_flowable]], colWidths=[504])
            code_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("PADDING", (0, 0), (-1, -1), 5),
                ])
            )
            card_flowables.append(code_table)

        # Remediation Advice Box
        rem_text = rem.recommended_fix or rem.explanation or "Apply standard secure coding practices to eliminate this vulnerability."
        rem_content = [
            Paragraph(
                f"<b>Recommended Remediation:</b> {xml.sax.saxutils.escape(rem_text)}",
                self.styles["RemediationText"],
            )
        ]
        rem_table = Table([[rem_content]], colWidths=[504])
        rem_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ecfdf5")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#6ee7b7")),
                ("PADDING", (0, 0), (-1, -1), 5),
            ])
        )
        card_flowables.append(rem_table)

        return card_flowables
