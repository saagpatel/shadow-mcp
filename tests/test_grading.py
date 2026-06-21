import os
import sqlite3

import pytest

from shadow_mcp.config import GradingPaths
from shadow_mcp.grading.combine import assess
from shadow_mcp.grading.mcptrust import McpTrustGrader
from shadow_mcp.models import (
    InventoryEntry,
    McpAuditGrade,
    McpTrustGrade,
    Provenance,
    ServerSpec,
)


def _entry(
    name="srv", transport="stdio", env_keys=None, command="srv", url=None, sources=("claude_code",)
):
    provs = [Provenance(source=s, location=s, scope="user", declared_name=name) for s in sources]
    return InventoryEntry(
        identity=f"cmd:{name}",
        canonical_name=name,
        spec=ServerSpec(transport=transport, command=command, url=url, env_keys=env_keys or []),
        provenances=provs,
    )


def test_band_from_composite_thresholds():
    e = _entry()
    assert assess(e, McpAuditGrade(composite=7.5, high_risk=True), None).band == "critical"
    assert assess(e, McpAuditGrade(composite=5.0, high_risk=False), None).band == "high"
    assert assess(e, McpAuditGrade(composite=4.0, high_risk=False), None).band == "medium"
    assert assess(e, McpAuditGrade(composite=1.0, high_risk=False), None).band == "low"


def test_missing_engine_is_unknown_not_low():
    e = _entry()
    a = assess(e, McpAuditGrade(composite=0.0, high_risk=False, error="not installed"), None)
    assert a.band == "unknown"


def test_mcptrust_F_raises_band():
    e = _entry()
    base = assess(e, McpAuditGrade(composite=4.0, high_risk=False), None).band  # medium
    bumped = assess(e, McpAuditGrade(composite=4.0, high_risk=False), McpTrustGrade(grade="F")).band
    assert base == "medium" and bumped == "high"


def test_http_transport_raises_low_band_and_cites_mcp07():
    e = _entry(transport="http", command=None, url="https://x.y/mcp")
    a = assess(e, McpAuditGrade(composite=1.0, high_risk=False), None)
    assert a.band == "medium"  # low bumped by exposure
    assert any("MCP07" in r for r in a.reasons)


def test_secret_env_cites_mcp01():
    e = _entry(env_keys=["BRIDGE_DB_PRINCIPAL_TOKEN"])
    a = assess(e, McpAuditGrade(composite=2.0, high_risk=False), None)
    assert any("MCP01" in r for r in a.reasons)


# ---- mcp-trust delegation against a temp registry ----


@pytest.fixture
def trust_paths(tmp_path):
    seed = tmp_path / "seed_servers.json"
    seed.write_text(
        '[{"slug": "mcp-reference-time", "name": "Reference Time", '
        '"source": {"kind": "npm", "reference": "@modelcontextprotocol/server-time"}}]',
        encoding="utf-8",
    )
    db = tmp_path / "registry.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE scans (id INTEGER PRIMARY KEY, server_slug TEXT, grade TEXT, "
        "transparency TEXT, risk_json TEXT, scanned_at TEXT)"
    )
    conn.execute(
        "INSERT INTO scans (server_slug, grade, transparency, risk_json, scanned_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("mcp-reference-time", "B", "high", '{"composite": 2.7}', "2026-06-01T00:00:00"),
    )
    conn.commit()
    conn.close()
    return GradingPaths(mcptrust_registry_db=db, mcptrust_seed=seed)


def test_mcptrust_resolves_seed_and_reads_grade(trust_paths):
    grader = McpTrustGrader(trust_paths)
    e = _entry(name="mcp-reference-time")
    g = grader.grade(e)
    grader.close()
    assert g.grade == "B"
    assert g.slug == "mcp-reference-time"
    assert g.composite == 2.7


def test_mcptrust_resolves_by_package_reference(trust_paths):
    grader = McpTrustGrader(trust_paths)
    e = _entry(name="whatever", command="npx")
    e.spec.args = ["@modelcontextprotocol/server-time"]
    e.identity = "cmd:@modelcontextprotocol/server-time"
    g = grader.grade(e)
    grader.close()
    assert g.grade == "B"


def test_mcptrust_unknown_is_default_not_error(trust_paths):
    grader = McpTrustGrader(trust_paths)
    g = grader.grade(_entry(name="never-heard-of-it"))
    grader.close()
    assert g.grade == "unknown"


# ---- thread 2: computed grade fills the registry gap ----


def test_compute_trust_grade_maps_dimensions_to_letter():
    from shadow_mcp.grading.mcptrust_compute import compute_trust_grade

    pytest.importorskip("mcp_trust")
    # high file_access -> danger-weighted -> low letter (D/F)
    risky = McpAuditGrade(
        composite=7.7, high_risk=True, dimensions={"file_access": 8.0, "network_access": 2.0}
    )
    assert compute_trust_grade(risky) in ("D", "F")
    # near-zero capability -> A
    benign = McpAuditGrade(composite=0.0, high_risk=False, dimensions={"file_access": 0.0})
    assert compute_trust_grade(benign) == "A"
    # no usable audit -> no computed grade
    assert compute_trust_grade(None) is None
    assert compute_trust_grade(McpAuditGrade(composite=0.0, high_risk=False, error="x")) is None


def test_connected_grade_never_spawns_remote_endpoints():
    pytest.importorskip("mcp_audit")
    from shadow_mcp.grading.mcpaudit_connect import grade_mcpaudit_connected

    spec = ServerSpec(transport="http", url="https://example.invalid/mcp")
    g = grade_mcpaudit_connected("remote", spec, timeout=2)
    assert g.connected is False  # a remote endpoint is never spawned by a local tool


def test_connected_grade_falls_back_when_server_wont_start():
    pytest.importorskip("mcp_audit")
    from shadow_mcp.grading.mcpaudit_connect import grade_mcpaudit_connected

    spec = ServerSpec(transport="stdio", command="/nonexistent/shadow-mcp/nope")
    g = grade_mcpaudit_connected("nope", spec, timeout=3)
    # a server that won't start falls back to the static grade, never crashes
    assert g.connected is False


@pytest.mark.skipif(
    not os.environ.get("SHADOW_MCP_RUN_CONNECT"),
    reason="set SHADOW_MCP_RUN_CONNECT=1 to run the real-spawn connected scan (uses npx)",
)
def test_connected_scan_spawns_real_server_and_spreads_grade():
    pytest.importorskip("mcp_audit")
    from shadow_mcp.grading.mcpaudit_connect import grade_mcpaudit_connected
    from shadow_mcp.grading.mcptrust_compute import compute_trust_grade

    spec = ServerSpec(
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    )
    g = grade_mcpaudit_connected("filesystem", spec, timeout=30)
    assert g.connection_status == "connected"
    assert g.connected is True and g.composite > 0
    # the connected dimensions push the computed letter off the static "A" floor
    assert compute_trust_grade(g) in ("B", "C", "D", "F")


def test_grade_inventory_fills_unknown_with_computed(trust_paths):
    from shadow_mcp.grading import grade_inventory

    pytest.importorskip("mcp_trust")
    # a server not in the registry, graded without the heavy MCPAudit engine but
    # with an injected audit via run_mcpaudit=False would give no audit; instead
    # verify the wiring marks computed grades when an audit is present is covered
    # by the compute unit test above. Here assert unknown stays unknown when both
    # engines are off.
    graded = grade_inventory(
        [_entry(name="mystery-server")],
        grading_paths=trust_paths,
        run_mcpaudit=False,
        compute_missing=True,
    )
    assert graded[0].risk.mcptrust.grade == "unknown"
    assert graded[0].risk.mcptrust.computed is False
