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
    "risk_score",
    [
        {"composite": 1.0, "file_access": float("nan")},
        {"composite": -1.0, "file_access": 1.0},
        {"composite": 1.0, "file_access": 11.0},
    ],
)
def test_out_of_range_or_nonfinite_scores_make_grade_unavailable(risk_score):
    grade = audit_to_grade({"risk_score": risk_score})

    assert grade.error and "score" in grade.error


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
