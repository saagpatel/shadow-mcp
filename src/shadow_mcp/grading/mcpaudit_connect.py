"""Connected grading: spawn a server, enumerate its real tools, grade it.

The static (config-only) path can't see a server's capabilities, so most grades
bottom out. This path delegates to MCPAudit's *connected* engine
(``_run_scan_core(skip_connect=False)`` — the same core the CLI's ``scan`` runs)
to spawn the server, list its tools, and score real permissions plus the deeper
injection/trifecta checks against actual tool descriptions.

SAFETY: connecting EXECUTES the server. This path is opt-in only (``--connect``
/ ``deep-scan``), runs only against stdio servers (never remote endpoints —
that's the network-scan tier), is bounded by a timeout, and falls back to the
static grade when a server won't start (e.g. it needs real secrets we don't have).
"""

from __future__ import annotations

from ..models import McpAuditGrade, ServerSpec
from .mcpaudit import _to_client_spec, audit_to_grade, grade_mcpaudit, muffle_stdout

_PASTED_SOURCE = "shadow-mcp:connect"


def _run_connected(name: str, spec: ServerSpec, timeout: int) -> dict | None:
    """Drive MCPAudit's connected core in-memory; return the ServerAudit dict."""
    import anyio
    from mcp_audit.api import parse_config
    from mcp_audit.cli import _run_scan_core
    from mcp_audit.overrides import OverrideApplier, OverrideConfig

    config = {"mcpServers": {name: _to_client_spec(spec)}}
    servers = parse_config(config, source=_PASTED_SOURCE)

    async def _scan():
        return await _run_scan_core(
            skip_connect=False,  # CONNECT: spawn the server and enumerate tools
            clients=None,
            timeout=timeout,
            extra_config=None,
            override_applier=OverrideApplier(OverrideConfig()),
            inject_check=True,
            trifecta_check=True,
            config_only=False,
            servers=servers,
        )

    with muffle_stdout():
        report = anyio.run(_scan)
    audits = report.model_dump(mode="json").get("audits") or []
    return audits[0] if audits else None


def grade_mcpaudit_connected(name: str, spec: ServerSpec, *, timeout: int = 8) -> McpAuditGrade:
    """Grade a single stdio server by connecting to it.

    Falls back to the static grade if the engine is missing, the server is not
    stdio, or the connection fails (so we never lose the config-only signal).
    """
    if spec.transport not in ("stdio", "unknown"):
        # remote endpoints are out of scope for a local tool; grade statically
        return grade_mcpaudit(name, spec)
    try:
        audit = _run_connected(name, spec, timeout)
    except ImportError:
        return McpAuditGrade(composite=0.0, high_risk=False, error="mcp-audits not installed")
    except Exception as exc:  # a flaky spawn must never break the sweep
        static = grade_mcpaudit(name, spec)
        static.connection_status = "failed"
        static.error = static.error or f"connect failed: {type(exc).__name__}"
        return static

    if audit is None:
        return grade_mcpaudit(name, spec)

    grade = audit_to_grade(audit, connected=True)
    # connection_status is one of: connected | failed | timeout | skipped.
    # If the server never actually connected, the config-only static grade is the
    # honest signal — keep it, but record that a connect was attempted.
    if grade.connection_status != "connected":
        static = grade_mcpaudit(name, spec)
        static.connection_status = grade.connection_status or "failed"
        return static
    return grade
