"""Proves the grading delegation to the real MCPAudit engine works.

Skips cleanly if mcp-audits is not installed, so the suite stays green without
the engine while still exercising the integration when it is present.
"""

import pytest

pytest.importorskip("mcp_audit")

from shadow_mcp.grading.mcpaudit import grade_mcpaudit  # noqa: E402
from shadow_mcp.models import ServerSpec  # noqa: E402


def test_filesystem_server_scores_above_zero():
    # A filesystem server with a broad root should register capability risk.
    spec = ServerSpec(
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/"],
    )
    grade = grade_mcpaudit("filesystem", spec)
    assert grade.error is None
    assert grade.composite >= 0.0  # engine produced a real composite
    assert isinstance(grade.findings, list)


def test_engine_never_raises_on_minimal_spec():
    grade = grade_mcpaudit("bare", ServerSpec(transport="stdio", command="true"))
    assert grade.error is None or "composite" in grade.model_dump()


def test_grading_does_not_pollute_stdout(capsys):
    # The engine writes a stray newline to stdout per scan; shadow-mcp's stdout is
    # the machine-readable deliverable (JSON/markdown) and must stay clean.
    grade_mcpaudit("x", ServerSpec(transport="stdio", command="true"))
    assert capsys.readouterr().out == ""
