from io import StringIO

from rich.console import Console

from shadow_mcp.models import (
    GradedServer,
    InventoryEntry,
    McpTrustGrade,
    Provenance,
    RiskAssessment,
    ServerSpec,
)
from shadow_mcp.report import build_report, render_markdown, render_terminal


def _graded(name, band, sources=("claude_code",), running=False, host_managed=False):
    provs = [Provenance(source=s, location=s, scope="user", declared_name=name) for s in sources]
    if running:
        provs.append(
            Provenance(
                source="process",
                location="ps",
                scope="runtime",
                declared_name=name,
                host_managed=host_managed,
            )
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
        _graded("ghost", "high", sources=(), running=True),  # standalone rogue (host_managed=False)
        _graded("plugin-child", "low", sources=(), running=True, host_managed=True),  # host-spawned
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
    assert "running_unconfigured" in kinds  # ghost: standalone rogue
    assert "host_spawned_unconfigured" in kinds  # plugin-child: host-managed
    assert "broad_blast_radius" in kinds
    # the genuine rogue is high; the host-spawned child is only low
    by_server = {f.server: f for f in report.shadow if f.kind.endswith("unconfigured")}
    assert by_server["ghost"].band == "high"
    assert by_server["plugin-child"].band == "low"


def test_computed_grade_adds_transparency_caveat_note():
    entry = InventoryEntry(
        identity="cmd:x",
        canonical_name="x",
        spec=ServerSpec(transport="stdio", command="x"),
        provenances=[Provenance(source="codex", location="c", scope="user", declared_name="x")],
    )
    graded = [
        GradedServer(
            entry=entry,
            risk=RiskAssessment(
                band="low",
                headline="LOW",
                mcptrust=McpTrustGrade(grade="A", computed=True, transparency="low"),
            ),
        )
    ]
    report = build_report(graded, host="h", generated_at="t", source_counts={"codex": 1})
    assert any("NOT 'verified safe'" in n for n in report.notes)


def test_no_caveat_note_without_computed_grades():
    entry = InventoryEntry(
        identity="cmd:x",
        canonical_name="x",
        spec=ServerSpec(transport="stdio", command="x"),
        provenances=[Provenance(source="codex", location="c", scope="user", declared_name="x")],
    )
    graded = [GradedServer(entry=entry, risk=RiskAssessment(band="low", headline="LOW"))]
    report = build_report(graded, host="h", generated_at="t", source_counts={"codex": 1})
    assert not any("verified safe" in n for n in report.notes)


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
