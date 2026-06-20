from io import StringIO

from rich.console import Console

from shadow_mcp.models import (
    GradedServer,
    InventoryEntry,
    Provenance,
    RiskAssessment,
    ServerSpec,
)
from shadow_mcp.report import build_report, render_markdown, render_terminal


def _graded(name, band, sources=("claude_code",), running=False):
    provs = [Provenance(source=s, location=s, scope="user", declared_name=name) for s in sources]
    if running:
        provs.append(
            Provenance(source="process", location="ps", scope="runtime", declared_name=name)
        )
    entry = InventoryEntry(
        identity=f"cmd:{name}",
        canonical_name=name,
        spec=ServerSpec(transport="stdio", command=name),
        provenances=provs,
    )
    return GradedServer(
        entry=entry,
        risk=RiskAssessment(band=band, headline=band.upper(), reasons=[f"{name} reason"]),
    )


def _report():
    graded = [
        _graded("low-srv", "low"),
        _graded("crit-srv", "critical"),
        _graded("ghost", "high", sources=(), running=True),  # running, unconfigured
        _graded("everywhere", "medium", sources=("claude_code", "codex", "claude_desktop")),
    ]
    return build_report(
        graded,
        host="testhost",
        generated_at="2026-06-20T00:00:00+00:00",
        source_counts={"claude_code": 3},
    )


def test_servers_sorted_critical_first():
    report = _report()
    assert report.servers[0].entry.canonical_name == "crit-srv"


def test_shadow_findings_detect_running_unconfigured_and_blast_radius():
    report = _report()
    kinds = {f.kind for f in report.shadow}
    assert "running_unconfigured" in kinds
    assert "broad_blast_radius" in kinds


def test_render_markdown_has_sections():
    md = render_markdown(_report())
    assert "# shadow-mcp inventory — testhost" in md
    assert "## Inventory" in md
    assert "## Shadow & attention" in md
    assert "crit-srv" in md


def test_render_terminal_runs():
    console = Console(file=StringIO(), force_terminal=False, width=120)
    render_terminal(_report(), console=console)
    out = console.file.getvalue()
    assert "shadow-mcp" in out
    assert "crit-srv" in out
