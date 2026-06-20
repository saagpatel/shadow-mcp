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
