"""Regression coverage for incomplete evidence in every grading adapter."""

import pytest

from shadow_mcp.config import GradingPaths
from shadow_mcp.grading.combine import assess
from shadow_mcp.grading.mcpaudit import audit_to_grade, grade_mcpaudit
from shadow_mcp.grading.mcpaudit_connect import grade_mcpaudit_connected
from shadow_mcp.grading.mcptrust import McpTrustGrader
from shadow_mcp.grading.mcptrust_compute import compute_trust_grade
from shadow_mcp.models import InventoryEntry, McpAuditGrade, Provenance, ServerSpec

_TRUST_DIMENSIONS = (
    "file_access",
    "network_access",
    "shell_execution",
    "destructive",
    "exfiltration",
)


def _entry() -> InventoryEntry:
    return InventoryEntry(
        identity="cmd:fixture",
        canonical_name="fixture",
        spec=ServerSpec(command="fixture"),
        provenances=[
            Provenance(
                source="claude_code",
                location="fixture",
                scope="user",
                declared_name="fixture",
            )
        ],
    )


def _partial_audit() -> dict:
    return {
        "risk_score": {"composite": 9.0},
        "connection_status": "connected",
        "tools": [{"name": "fixture_tool"}],
    }


def _exercise_grade_inventory(monkeypatch, tmp_path):
    import shadow_mcp.grading as grading

    monkeypatch.setattr(
        grading, "grade_mcpaudit", lambda name, spec: audit_to_grade(_partial_audit())
    )
    seed = tmp_path / "seed.json"
    seed.write_text("[]", encoding="utf-8")
    graded = grading.grade_inventory(
        [_entry()],
        grading_paths=GradingPaths(
            mcptrust_registry_db=tmp_path / "registry.sqlite", mcptrust_seed=seed
        ),
        compute_missing=True,
    )
    assert graded[0].risk.band == "critical"
    assert graded[0].risk.mcptrust.grade == "unknown"


def _exercise_assess(monkeypatch, tmp_path):
    result = assess(
        _entry(), McpAuditGrade(composite=0.0, high_risk=False, error="missing score"), None
    )
    assert result.band == "unknown"


def _exercise_grade_mcpaudit(monkeypatch, tmp_path):
    import mcp_audit.api

    monkeypatch.setattr(
        mcp_audit.api,
        "scan_config_only_dict",
        lambda config, redact: {"schema_version": 1, "audits": [_partial_audit()]},
    )
    grade = grade_mcpaudit("fixture", ServerSpec(command="fixture"))
    assert grade.composite == 9.0
    assert compute_trust_grade(grade) is None


def _exercise_grade_mcpaudit_connected(monkeypatch, tmp_path):
    import shadow_mcp.grading.mcpaudit_connect as connected

    monkeypatch.setattr(connected, "_run_connected", lambda *args: _partial_audit())
    grade = grade_mcpaudit_connected("fixture", ServerSpec(command="fixture"))
    assert grade.composite == 9.0
    assert compute_trust_grade(grade) is None


def _exercise_registry_grader(monkeypatch, tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text("[]", encoding="utf-8")
    grader = McpTrustGrader(
        GradingPaths(mcptrust_registry_db=tmp_path / "registry.sqlite", mcptrust_seed=seed)
    )
    try:
        assert grader.grade(_entry()).grade == "unknown"
    finally:
        grader.close()


def _exercise_compute_trust_grade(monkeypatch, tmp_path):
    audit = McpAuditGrade(composite=9.0, high_risk=True)
    assert compute_trust_grade(audit) is None


_PUBLIC_ADAPTER_CASES = {
    "grade_inventory": _exercise_grade_inventory,
    "assess": _exercise_assess,
    "grade_mcpaudit": _exercise_grade_mcpaudit,
    "grade_mcpaudit_connected": _exercise_grade_mcpaudit_connected,
    "McpTrustGrader": _exercise_registry_grader,
    "compute_trust_grade": _exercise_compute_trust_grade,
}


@pytest.mark.parametrize("adapter_name", sorted(_PUBLIC_ADAPTER_CASES))
def test_public_grading_adapters_reject_or_preserve_incomplete_evidence(
    adapter_name, monkeypatch, tmp_path
):
    import shadow_mcp.grading as grading

    assert set(_PUBLIC_ADAPTER_CASES) == set(grading.__all__)
    _PUBLIC_ADAPTER_CASES[adapter_name](monkeypatch, tmp_path)


@pytest.mark.parametrize(
    "report",
    [None, [], {"audits": {"one": _partial_audit()}}, {"audits": [None]}],
)
def test_static_adapter_returns_unavailable_for_malformed_report(report, monkeypatch):
    import mcp_audit.api

    monkeypatch.setattr(mcp_audit.api, "scan_config_only_dict", lambda config, redact: report)

    grade = grade_mcpaudit("fixture", ServerSpec(command="fixture"))

    assert grade.error is not None


@pytest.mark.parametrize("audit", [None, [], "malformed"])
def test_audit_parser_returns_unavailable_for_malformed_audit(audit):
    grade = audit_to_grade(audit)

    assert grade.error is not None


def test_audit_parser_returns_unavailable_for_malformed_connection_status():
    grade = audit_to_grade({"connection_status": 1})

    assert grade.error is not None


@pytest.mark.parametrize(
    "spec",
    [ServerSpec(transport="unknown"), ServerSpec(command="  "), ServerSpec(url=" ")],
)
def test_static_adapter_rejects_spec_without_usable_launch_information(spec):
    grade = grade_mcpaudit("fixture", spec)

    assert grade.error is not None


@pytest.mark.parametrize(
    "spec",
    [ServerSpec(transport="unknown"), ServerSpec(command="  "), ServerSpec(url=" ")],
)
def test_connected_adapter_does_not_run_without_usable_launch_information(spec, monkeypatch):
    import shadow_mcp.grading.mcpaudit_connect as connected

    monkeypatch.setattr(
        connected, "_run_connected", lambda *args: pytest.fail("must not run an empty command")
    )

    grade = grade_mcpaudit_connected("fixture", spec)

    assert grade.error is not None


@pytest.mark.parametrize("severity", ["critical", "high", "medium", "low", "info"])
def test_audit_parser_accepts_valid_finding_severity_with_optional_fields(severity):
    risk_score = {"composite": 0.0, **{name: 0.0 for name in _TRUST_DIMENSIONS}}
    grade = audit_to_grade(
        {"risk_score": risk_score, "injection_findings": [{"severity": severity}]}
    )

    assert grade.error is None
    assert grade.findings[0]["severity"] == severity


@pytest.mark.parametrize(
    "findings",
    [[None], {"severity": "high"}, [{"severity": "unexpected"}]],
)
def test_malformed_findings_do_not_produce_computed_trust_grade(findings):
    pytest.importorskip("mcp_trust")
    risk_score = {"composite": 0.0, **{name: 0.0 for name in _TRUST_DIMENSIONS}}
    grade = audit_to_grade({"risk_score": risk_score, "capability_findings": findings})

    assert grade.error is not None
    assert compute_trust_grade(grade) is None


def test_finding_limit_retains_critical_evidence():
    risk_score = {"composite": 0.0, **{name: 0.0 for name in _TRUST_DIMENSIONS}}
    findings = [{"severity": "high", "title": f"high-{index}"} for index in range(8)]
    findings.append({"severity": "critical", "title": "critical finding"})
    grade = audit_to_grade({"risk_score": risk_score, "injection_findings": findings})

    assert len(grade.findings) == 8
    assert any(finding["severity"] == "critical" for finding in grade.findings)
    assert compute_trust_grade(grade) == "D"


@pytest.mark.parametrize("finding", [{}, {"severity": "unexpected"}])
def test_compute_trust_rejects_malformed_findings(finding):
    pytest.importorskip("mcp_trust")
    dimensions = {name: 0.0 for name in _TRUST_DIMENSIONS}
    grade = McpAuditGrade(
        composite=0.0,
        high_risk=False,
        dimensions=dimensions,
        findings=[finding],
    )

    assert compute_trust_grade(grade) is None


@pytest.mark.parametrize("missing_dimension", _TRUST_DIMENSIONS)
def test_computed_trust_requires_all_dimensions(missing_dimension):
    pytest.importorskip("mcp_trust")
    dimensions = {name: 0.0 for name in _TRUST_DIMENSIONS if name != missing_dimension}
    audit = McpAuditGrade(composite=0.0, high_risk=False, dimensions=dimensions)

    assert compute_trust_grade(audit) is None
