"""Compute an A-F danger grade for servers the mcp-trust registry hasn't scanned.

The registry only carries grades for the handful of servers someone has already
scanned and seeded, so most locally-discovered servers come back ``unknown``.
Rather than leave them ungraded, we feed the MCPAudit capability dimensions we
already have into mcp-trust's *own* ``grade()`` logic (its danger weighting +
critical cap). This delegates to mcp-trust's grading IP without writing to its
database — a computed letter, clearly marked as such, not a persisted scan.
"""

from __future__ import annotations

from ..models import McpAuditGrade
from ._score import risk_score

_REQUIRED_DIMENSIONS = (
    "file_access",
    "network_access",
    "shell_execution",
    "destructive",
    "exfiltration",
)


def compute_trust_grade(mcpaudit: McpAuditGrade | None) -> str | None:
    """Return an A-F letter via mcp-trust's grade(), or None if unavailable."""
    if mcpaudit is None or mcpaudit.error:
        return None
    if risk_score(mcpaudit.composite) is None:
        return None
    try:
        from mcp_trust.core.grading import grade as _grade
        from mcp_trust.core.models import RiskSummary, Severity
    except ImportError:
        return None

    dims = mcpaudit.dimensions
    if any(risk_score(dims.get(name)) is None for name in _REQUIRED_DIMENSIONS):
        return None
    findings_by_severity: dict = {}
    for f in mcpaudit.findings:
        if not isinstance(f, dict):
            return None
        sev = f.get("severity")
        if not isinstance(sev, str):
            return None
        try:
            severity = Severity[sev.upper()]
        except KeyError:
            return None
        findings_by_severity[severity] = findings_by_severity.get(severity, 0) + 1

    risk = RiskSummary(
        composite=mcpaudit.composite,
        file_access=dims["file_access"],
        network_access=dims["network_access"],
        shell_execution=dims["shell_execution"],
        destructive=dims["destructive"],
        exfiltration=dims["exfiltration"],
        findings_by_severity=findings_by_severity,
        # annotation_coverage drives only the (separate) transparency axis, not
        # the letter; grade() ignores it. Leave at the model default.
    )
    try:
        return str(_grade(risk))
    except Exception:
        return None
