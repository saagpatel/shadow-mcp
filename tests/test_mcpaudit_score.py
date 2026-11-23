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
