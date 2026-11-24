import pytest

from shadow_mcp.grading.combine import assess
from shadow_mcp.grading.mcpaudit import audit_to_grade
from shadow_mcp.models import InventoryEntry, ServerSpec


@pytest.mark.parametrize(
    "audit", [{}, {"risk_score": {"composite": "x"}}, {"risk_score": {"composite": float("inf")}}]
)
def test_invalid_capability_score_is_unavailable(audit):
    entry = InventoryEntry(identity="cmd:x", canonical_name="x", spec=ServerSpec(command="x"))
    grade = audit_to_grade(audit)
    assert assess(entry, grade, None).headline == "UNKNOWN"
    assert grade.error and "composite" in grade.error


@pytest.mark.parametrize(
    ("key", "value"),
    [("file_access", float("nan")), ("composite", -1.0), ("file_access", 11.0)],
)
def test_out_of_range_or_nonfinite_scores_make_grade_unavailable(key, value):
    score = dict.fromkeys(
        (
            "composite",
            "file_access",
            "network_access",
            "shell_execution",
            "destructive",
            "exfiltration",
        ),
        0.0,
    )
    score[key] = value
    grade = audit_to_grade({"risk_score": score})

    assert grade.error and key in grade.error
    assert not grade.dimensions


def test_connected_invalid_score_preserves_successful_connection(monkeypatch):
    import shadow_mcp.grading.mcpaudit_connect as connected

    monkeypatch.setattr(
        connected,
        "_run_connected",
        lambda name, spec, timeout: {
            "risk_score": {"composite": None},
            "connection_status": "connected",
            "tools": [{"name": "read_file"}],
        },
    )
    monkeypatch.setattr(
        connected,
        "grade_mcpaudit",
        lambda name, spec: pytest.fail("successful connection must not use static fallback"),
    )

    grade = connected.grade_mcpaudit_connected("fixture", ServerSpec(command="fixture"))

    assert grade.error and "composite" in grade.error
    assert grade.connected is True
    assert grade.connection_status == "connected"
    assert grade.tool_count == 1


@pytest.mark.parametrize(
    "missing",
    [None, "file_access", "network_access", "shell_execution", "destructive", "exfiltration"],
)
def test_assessment_requires_all_provider_dimensions(missing):
    score = {
        "composite": 0,
        "file_access": 0,
        "network_access": 0,
        "shell_execution": 0,
        "destructive": 0,
        "exfiltration": 0,
    }
    if missing:
        del score[missing]
    grade = audit_to_grade(
        {"risk_score": score, "connection_status": "connected", "tools": []}, connected=True
    )
    entry = InventoryEntry(
        identity="cmd:fixture", canonical_name="fixture", spec=ServerSpec(command="fixture")
    )
    assert grade.connected and grade.connection_status == "connected" and grade.tool_count == 0
    assert assess(entry, grade, None).headline == ("UNKNOWN" if missing else "LOW (cap 0.0)")
    assert bool(grade.error) == bool(missing)
