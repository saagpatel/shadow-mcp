"""Grading orchestration: delegate to both engines, compose, attach to entries."""

from __future__ import annotations

from ..config import GradingPaths
from ..models import GradedServer, InventoryEntry
from .combine import assess
from .mcpaudit import grade_mcpaudit
from .mcptrust import McpTrustGrader

__all__ = ["grade_inventory", "assess", "grade_mcpaudit", "McpTrustGrader"]


def grade_inventory(
    entries: list[InventoryEntry],
    *,
    grading_paths: GradingPaths | None = None,
    run_mcpaudit: bool = True,
) -> list[GradedServer]:
    trust = McpTrustGrader(grading_paths)
    try:
        graded: list[GradedServer] = []
        for entry in entries:
            audit = grade_mcpaudit(entry.canonical_name, entry.spec) if run_mcpaudit else None
            tg = trust.grade(entry)
            graded.append(GradedServer(entry=entry, risk=assess(entry, audit, tg)))
        return graded
    finally:
        trust.close()
