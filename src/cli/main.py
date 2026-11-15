"""Command-Line Interface (CLI) entrypoint for Automated Code Vulnerability Reviewer."""

import argparse
import asyncio
import inspect
import json
import os
from pathlib import Path
import sys
from typing import Any, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from src.cli.formatter import CLIFormatter
from src.cli.runner import CLIScanRunner
from src.core.models import SeverityEnum
from src.storage.history import ReviewHistoryStorage


def execute_coroutine_sync(coro: Any) -> Any:
    """Safely step an async coroutine without socket-level event loops."""
    stack = [coro]
    val = None
    is_exc = False
    exc_obj = None

    while stack:
        current = stack[-1]
        try:
            if is_exc:
                is_exc = False
                res = current.throw(exc_obj)
            else:
                res = current.send(val)
            val = None

            if inspect.iscoroutine(res):
                stack.append(res)
            else:
                val = getattr(res, "result", lambda: res)()
        except StopIteration as stop:
            stack.pop()
            val = stop.value
        except Exception as exc:
            stack.pop()
            is_exc = True
            exc_obj = exc

    if is_exc and exc_obj is not None:
        raise exc_obj
    return val


def _add_scan_arguments(parser: argparse.ArgumentParser) -> None:
    """Register common scanning options on parser."""
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Target local directory to scan (default: current directory '.')",
    )
    parser.add_argument(
        "--github",
        type=str,
        default=None,
        help="Remote GitHub repository URL (e.g. https://github.com/owner/repo)",
    )
    parser.add_argument(
        "--ref",
        type=str,
        default=None,
        help="Git branch, tag, or commit SHA for remote repository",
    )
    parser.add_argument(
        "--pr",
        type=int,
        default=None,
        help="GitHub pull request number for scanning PR changes",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="GitHub personal access token (defaults to GITHUB_TOKEN environment variable)",
    )
    parser.add_argument(
        "--min-severity",
        type=str,
        choices=["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
        default=None,
        help="Minimum severity threshold to display in findings table",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output pure JSON report to stdout (disabling Rich terminal formatting)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Save complete JSON review report to specified file path",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        default=False,
        help="Render full finding cards with code snippets and remediation advice",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        default=False,
        help="Do not save scan report to review history",
    )
    parser.add_argument(
        "--export-html",
        type=str,
        default=None,
        help="Export standalone HTML audit report to specified file path",
    )
    parser.add_argument(
        "--export-pdf",
        type=str,
        default=None,
        help="Export academic PDF audit report to specified file path",
    )


def _add_export_arguments(parser: argparse.ArgumentParser) -> None:
    """Register report export options on parser."""
    parser.add_argument(
        "review_id",
        type=str,
        help="Review ID from review history to export",
    )
    parser.add_argument(
        "--html",
        type=str,
        default=None,
        help="File path to save standalone HTML report",
    )
    parser.add_argument(
        "--pdf",
        type=str,
        default=None,
        help="File path to save academic PDF audit report",
    )


def _add_history_arguments(parser: argparse.ArgumentParser) -> None:
    """Register history query options on parser."""
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Filter review history by repository identifier",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of historical reviews to display (default: 50)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output historical review records as JSON to stdout",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build command-line argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="loki",
        description="LOKI: Automated Code Vulnerability Reviewer CLI",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")
    scan_parser = subparsers.add_parser("scan", help="Run automated vulnerability review on codebase")
    _add_scan_arguments(scan_parser)

    history_parser = subparsers.add_parser("history", help="Query and view past review scan history")
    _add_history_arguments(history_parser)

    export_parser = subparsers.add_parser("export", help="Export HTML or PDF audit reports for an existing scan")
    _add_export_arguments(export_parser)

    return parser


def normalize_cli_args(argv: Optional[List[str]] = None) -> List[str]:
    """Normalize CLI arguments to ensure scan subcommand is always routed appropriately."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return ["scan", "."]

    if args[0] in ("-h", "--help", "-v", "--version"):
        return args

    known_subcommands = {"scan", "history", "export"}
    if args[0] not in known_subcommands:
        return ["scan"] + args

    return args


async def run_cli_scan(args: argparse.Namespace, console: Optional[Console] = None) -> int:
    """Execute scan workflow with arguments and handle terminal presentation."""
    console = console or Console()
    formatter = CLIFormatter(console=console)
    runner = CLIScanRunner()

    target = args.github if args.github else args.path
    is_github = bool(args.github)

    min_sev: Optional[SeverityEnum] = None
    if args.min_severity:
        try:
            min_sev = SeverityEnum[args.min_severity]
        except KeyError:
            min_sev = None

    try:
        if args.json:
            # Silent execution without rich terminal UI
            review = await runner.run_scan(
                target=target,
                is_github=is_github,
                ref=args.ref,
                token=args.token,
                pr_number=args.pr,
            )
            json_text = formatter.format_json_output(review)
            sys.stdout.write(json_text + "\n")
            sys.stdout.flush()

            if args.output:
                out_path = Path(args.output).resolve()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json_text, encoding="utf-8")

            if getattr(args, "export_html", None):
                try:
                    from src.reports.html_generator import HTMLReportGenerator
                    html_path = Path(args.export_html).resolve()
                    HTMLReportGenerator().save_to_file(review, html_path)
                except Exception:
                    pass

            if getattr(args, "export_pdf", None):
                try:
                    from src.reports.pdf_generator import PDFReportGenerator
                    pdf_path = Path(args.export_pdf).resolve()
                    PDFReportGenerator().generate(review, output_path=pdf_path)
                except Exception:
                    pass

            if not getattr(args, "no_save", False):
                try:
                    ReviewHistoryStorage().save_review(review)
                except Exception:
                    pass

            has_critical = review.severity_distribution.get("CRITICAL", 0) > 0
            return 2 if has_critical else 0

        # Rich interactive terminal mode
        console.print(
            Panel(
                Text(
                    f"⚡ LOKI: Automated Code Vulnerability Reviewer\nTarget: {target}",
                    justify="center",
                    style="bold white",
                ),
                border_style="cyan",
            )
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            scan_task = progress.add_task("[cyan]Starting repository review...", total=None)

            def on_stage(stage: str, msg: str) -> None:
                progress.update(scan_task, description=f"[cyan]{msg}[/cyan]")

            def on_progress(chunk: Any, results: Any = None) -> None:
                chunk_name = getattr(chunk, "name", "chunk")
                progress.update(scan_task, description=f"[cyan]Analyzing chunk: {chunk_name}[/cyan]")

            review = await runner.run_scan(
                target=target,
                is_github=is_github,
                ref=args.ref,
                token=args.token,
                pr_number=args.pr,
                on_progress=on_progress,
                on_stage=on_stage,
            )

        # 1. High-level Summary Panel
        console.print(formatter.format_summary_panel(review))

        # 2. Overview Findings Table
        console.print(formatter.format_findings_table(review.findings, min_severity=min_sev))

        # 3. Detailed Finding Cards
        has_critical = review.severity_distribution.get("CRITICAL", 0) > 0
        if args.detailed:
            console.print("\n[bold cyan]Detailed Finding Breakdowns:[/bold cyan]")
            for item in review.findings:
                if min_sev and item.finding.severity.value not in [
                    s.value
                    for s in SeverityEnum
                    if list(SeverityEnum).index(s) <= list(SeverityEnum).index(min_sev)
                ]:
                    continue
                console.print(formatter.format_finding_card(item))
        elif has_critical:
            console.print("\n[bold red]Critical Vulnerabilities Requiring Immediate Review:[/bold red]")
            for item in review.findings:
                if item.finding.severity == SeverityEnum.CRITICAL:
                    console.print(formatter.format_finding_card(item))

        # 4. Save to output file if requested
        if args.output:
            out_path = Path(args.output).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(formatter.format_json_output(review), encoding="utf-8")
            console.print(f"\n[bold green]✓ Complete review report saved to: {out_path}[/bold green]")

        # 4b. Export HTML report if requested
        if getattr(args, "export_html", None):
            try:
                from src.reports.html_generator import HTMLReportGenerator
                html_path = Path(args.export_html).resolve()
                html_path.parent.mkdir(parents=True, exist_ok=True)
                HTMLReportGenerator().save_to_file(review, html_path)
                console.print(f"[bold green]✓ Standalone HTML report exported to:[/bold green] [bold cyan]{html_path}[/bold cyan]")
            except Exception as exp_err:
                console.print(f"[bold red]Failed to export HTML report: {exp_err}[/bold red]")

        # 4c. Export PDF report if requested
        if getattr(args, "export_pdf", None):
            try:
                from src.reports.pdf_generator import PDFReportGenerator
                pdf_path = Path(args.export_pdf).resolve()
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                PDFReportGenerator().generate(review, output_path=pdf_path)
                console.print(f"[bold green]✓ Academic PDF report exported to:[/bold green] [bold cyan]{pdf_path}[/bold cyan]")
            except Exception as exp_err:
                console.print(f"[bold red]Failed to export PDF report: {exp_err}[/bold red]")

        # 5. Save to review history unless disabled
        if not getattr(args, "no_save", False):
            try:
                storage = ReviewHistoryStorage()
                storage.save_review(review)
                console.print(Text(f"[Review saved to history with ID: {review.review_id}]", style="bold green"))
            except Exception as hist_err:
                console.print(f"[dim yellow]Warning: Failed to save review to history: {hist_err}[/dim yellow]")

        # 6. Advisory Disclaimer Footer
        console.print(
            Panel(
                Text(
                    f"ADVISORY DISCLAIMER:\n{review.advisory_disclaimer}",
                    style="italic dim yellow",
                    justify="center",
                ),
                border_style="dim yellow",
            )
        )

        return 2 if has_critical else 0

    except (FileNotFoundError, ValueError) as err:
        if args.json:
            sys.stderr.write(f'{{"error": "{str(err)}"}}\n')
        else:
            console.print(f"[bold red]Validation Error:[/bold red] {err}")
        return 1
    except Exception as exc:
        if args.json:
            sys.stderr.write(f'{{"error": "{str(exc)}"}}\n')
        else:
            console.print(f"[bold red]Scan Failed:[/bold red] {exc}")
        return 1


def run_cli_history(args: argparse.Namespace, console: Optional[Console] = None) -> int:
    """Query and display past review scans from history storage."""
    console = console or Console()
    storage = ReviewHistoryStorage()
    repo_filter = getattr(args, "repo", None)
    limit = getattr(args, "limit", 50)
    reviews = storage.list_reviews(repo_id=repo_filter, limit=limit)

    if getattr(args, "json", False):
        sys.stdout.write(json.dumps(reviews, indent=2) + "\n")
        sys.stdout.flush()
        return 0

    if not reviews:
        filter_msg = f" for repository '{repo_filter}'" if repo_filter else ""
        console.print(f"[dim yellow]No historical reviews found{filter_msg}.[/dim yellow]")
        return 0

    table = Table(
        title="[bold white]Review Scan History[/bold white]",
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Review ID", style="cyan", no_wrap=True)
    table.add_column("Repository", style="white")
    table.add_column("Date", style="dim")
    table.add_column("Findings", justify="right")
    table.add_column("Critical", justify="right", style="bold red")
    table.add_column("High", justify="right", style="red")
    table.add_column("Medium", justify="right", style="yellow")
    table.add_column("Max Risk", justify="right", style="bold magenta")

    for r in reviews:
        sev = r.get("severity_distribution", {})
        crit_count = sev.get("CRITICAL", 0)
        crit_str = f"[bold red]{crit_count}[/bold red]" if crit_count > 0 else "0"
        high_count = sev.get("HIGH", 0)
        high_str = f"[red]{high_count}[/red]" if high_count > 0 else "0"
        med_count = sev.get("MEDIUM", 0)
        med_str = f"[yellow]{med_count}[/yellow]" if med_count > 0 else "0"
        max_risk = r.get("max_risk_score", 0.0)

        table.add_row(
            str(r.get("review_id", ""))[:8] + "...",
            str(r.get("repo_id", "")),
            str(r.get("created_at", ""))[:19].replace("T", " "),
            str(r.get("total_findings", 0)),
            crit_str,
            high_str,
            med_str,
            f"{max_risk:.2f}",
        )

    console.print(table)
    return 0


def run_cli_export(args: argparse.Namespace, console: Optional[Console] = None) -> int:
    """Export standalone HTML or academic PDF reports for a historical review scan."""
    console = console or Console()
    storage = ReviewHistoryStorage()
    review = storage.get_review(args.review_id)
    if not review:
        console.print(f"[bold red]Error: Review '{args.review_id}' not found in review history.[/bold red]")
        return 1

    exported = False
    html_target = args.html
    pdf_target = args.pdf

    # If neither specified, default to exporting both into current working directory
    if not html_target and not pdf_target:
        html_target = f"review-{args.review_id}.html"
        pdf_target = f"review-{args.review_id}.pdf"

    if html_target:
        try:
            from src.reports.html_generator import HTMLReportGenerator
            out_html = Path(html_target).resolve()
            out_html.parent.mkdir(parents=True, exist_ok=True)
            HTMLReportGenerator().save_to_file(review, out_html)
            console.print(f"[bold green]✓ Standalone HTML report exported to:[/bold green] [bold cyan]{out_html}[/bold cyan]")
            exported = True
        except Exception as err:
            console.print(f"[bold red]Failed to export HTML report: {err}[/bold red]")

    if pdf_target:
        try:
            from src.reports.pdf_generator import PDFReportGenerator
            out_pdf = Path(pdf_target).resolve()
            out_pdf.parent.mkdir(parents=True, exist_ok=True)
            PDFReportGenerator().generate(review, output_path=out_pdf)
            console.print(f"[bold green]✓ Academic PDF report exported to:[/bold green] [bold cyan]{out_pdf}[/bold cyan]")
            exported = True
        except Exception as err:
            console.print(f"[bold red]Failed to export PDF report: {err}[/bold red]")

    return 0 if exported else 1


def main(argv: Optional[List[str]] = None) -> int:
    """CLI application entrypoint."""
    parser = build_parser()
    normalized = normalize_cli_args(argv)
    args = parser.parse_args(normalized)

    if getattr(args, "command", None) == "history":
        return run_cli_history(args)

    if getattr(args, "command", None) == "export":
        return run_cli_export(args)

    # In sandboxed environments or under pytest, use execute_coroutine_sync to avoid socket IOCP hangs
    if "pytest" in sys.modules or os.environ.get("SANDBOX_MODE") == "1":
        return execute_coroutine_sync(run_cli_scan(args))

    try:
        return asyncio.run(run_cli_scan(args))
    except Exception:
        return execute_coroutine_sync(run_cli_scan(args))


if __name__ == "__main__":
    sys.exit(main())
