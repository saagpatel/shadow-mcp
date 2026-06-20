"""Build and render the report: JSON deliverable + rich terminal + markdown."""

from __future__ import annotations

from collections import Counter

from rich.console import Console
from rich.table import Table

from .models import GradedServer, Report, ShadowFinding
from .shadow import build_shadow_findings

_BAND_STYLE = {
    "critical": "bold red",
    "high": "dark_orange",
    "medium": "yellow",
    "low": "green",
    "unknown": "grey62",
}
_BAND_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unknown": 0}


def build_report(
    graded: list[GradedServer],
    *,
    host: str,
    generated_at: str,
    source_counts: dict[str, int],
    errors: list[str] | None = None,
) -> Report:
    shadow = build_shadow_findings(graded)
    # highest band first; names ascending within a band
    ordered = sorted(
        graded,
        key=lambda g: (-_BAND_RANK.get(g.risk.band, 0), g.entry.canonical_name.lower()),
    )
    notes = list(errors or [])
    return Report(
        generated_at=generated_at,
        host=host,
        servers=ordered,
        shadow=shadow,
        source_summary=dict(source_counts),
        notes=notes,
    )


def _band_counts(report: Report) -> Counter:
    return Counter(g.risk.band for g in report.servers)


def render_terminal(report: Report, console: Console | None = None) -> None:
    console = console or Console()
    counts = _band_counts(report)
    summary = "  ".join(
        f"[{_BAND_STYLE.get(b, '')}]{b}={counts.get(b, 0)}[/]"
        for b in ("critical", "high", "medium", "low", "unknown")
        if counts.get(b, 0)
    )
    console.print(
        f"\n[bold]shadow-mcp[/] — {len(report.servers)} servers on "
        f"[bold]{report.host}[/]  ({report.generated_at})"
    )
    console.print(f"Risk: {summary or 'none graded'}")
    srcs = ", ".join(f"{k}:{v}" for k, v in sorted(report.source_summary.items()))
    console.print(f"Sources: {srcs}\n")

    table = Table(title="MCP server inventory", header_style="bold", expand=True)
    table.add_column("server", style="bold", no_wrap=True)
    table.add_column("transport")
    table.add_column("sources")
    table.add_column("risk")
    table.add_column("top reason", overflow="fold")
    for g in report.servers:
        e = g.entry
        run = " [cyan]●live[/]" if e.running else ""
        reason = g.risk.reasons[0] if g.risk.reasons else ""
        table.add_row(
            e.canonical_name + run,
            e.spec.transport,
            ",".join(e.sources),
            f"[{_BAND_STYLE.get(g.risk.band, '')}]{g.risk.headline}[/]",
            reason,
        )
    console.print(table)

    if report.shadow:
        console.print("\n[bold]Shadow & attention[/]")
        stable = Table(show_header=True, header_style="bold", expand=True)
        stable.add_column("kind", no_wrap=True)
        stable.add_column("server", no_wrap=True)
        stable.add_column("detail", overflow="fold")
        for f in report.shadow:
            stable.add_row(f"[{_BAND_STYLE.get(f.band, '')}]{f.kind}[/]", f.server, f.detail)
        console.print(stable)

    if report.notes:
        console.print("\n[grey62]Notes:[/]")
        for n in report.notes:
            console.print(f"  [grey62]- {n}[/]")
    console.print()


def render_markdown(report: Report) -> str:
    counts = _band_counts(report)
    lines: list[str] = []
    lines.append(f"# shadow-mcp inventory — {report.host}")
    lines.append("")
    lines.append(f"Generated: {report.generated_at}")
    band_line = ", ".join(
        f"{b}={counts.get(b, 0)}"
        for b in ("critical", "high", "medium", "low", "unknown")
        if counts.get(b, 0)
    )
    lines.append(f"Servers: {len(report.servers)} ({band_line or 'none graded'})")
    src = ", ".join(f"{k}: {v}" for k, v in sorted(report.source_summary.items()))
    lines.append(f"Sources: {src}")
    lines.append("")
    lines.append("## Inventory")
    lines.append("")
    lines.append("| Server | Transport | Sources | Risk | Top reason |")
    lines.append("|---|---|---|---|---|")
    for g in report.servers:
        e = g.entry
        reason = (g.risk.reasons[0] if g.risk.reasons else "").replace("|", "/")
        live = " (live)" if e.running else ""
        lines.append(
            f"| {e.canonical_name}{live} | {e.spec.transport} | "
            f"{','.join(e.sources)} | {g.risk.headline} | {reason} |"
        )
    if report.shadow:
        lines.append("")
        lines.append("## Shadow & attention")
        lines.append("")
        lines.append("| Kind | Server | Detail |")
        lines.append("|---|---|---|")
        for f in report.shadow:
            lines.append(f"| {f.kind} | {f.server} | {f.detail.replace('|', '/')} |")
    if report.notes:
        lines.append("")
        lines.append("## Notes")
        lines.append("")
        for n in report.notes:
            lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines)
