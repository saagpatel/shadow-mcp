"""Grading orchestration: delegate to both engines, compose, attach to entries."""

from __future__ import annotations

from ..config import GradingPaths
from ..models import GradedServer, InventoryEntry, McpTrustGrade
from .combine import assess
from .mcpaudit import grade_mcpaudit
from .mcptrust import McpTrustGrader
from .mcptrust_compute import compute_trust_grade

__all__ = [
    "grade_inventory",
    "assess",
    "grade_mcpaudit",
    "McpTrustGrader",
    "compute_trust_grade",
]


def grade_inventory(
    entries: list[InventoryEntry],
    *,
    grading_paths: GradingPaths | None = None,
    run_mcpaudit: bool = True,
    compute_missing: bool = True,
) -> list[GradedServer]:
    trust = McpTrustGrader(grading_paths)
    try:
        graded: list[GradedServer] = []
        for entry in entries:
            audit = grade_mcpaudit(entry.canonical_name, entry.spec) if run_mcpaudit else None
            tg = trust.grade(entry)
            # Fill a registry gap with a grade computed from mcp-trust's own logic.
            # It is derived from MCPAudit's STATIC config-only dimensions, so its
            # transparency is low: "cannot verify safe" (no connected scan), not
            # "verified safe". We mark it computed + low-transparency to say so.
            if compute_missing and tg.grade == "unknown":
                letter = compute_trust_grade(audit)
                if letter:
                    tg = McpTrustGrade(
                        grade=letter, slug=tg.slug, computed=True, transparency="low"
                    )
            graded.append(GradedServer(entry=entry, risk=assess(entry, audit, tg)))
        return graded
    finally:
        trust.close()
