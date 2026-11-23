"""Delegate capability grading to the MCPAudit engine.

We call ``mcp_audit.api.scan_config_only_dict`` (static, no spawn, no network)
per server so one malformed spec cannot void every grade. The engine is an
optional import: if it is not installed, grading degrades to ``error`` and
discovery still works.
"""

from __future__ import annotations

import contextlib
import io

from ..models import McpAuditGrade, ServerSpec
from ._score import risk_score


@contextlib.contextmanager
def muffle_stdout():
    """Capture stdout written by the delegated engine.

    mcp-audits>=2.3 is silent by default (no console passed -> no output), so
    this is defense in depth: shadow-mcp's stdout is its machine-readable
    deliverable (JSON / markdown), and an upstream output regression must never
    corrupt it.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        yield


# finding-list keys MCPAudit emits in the config-only path -> our category label
_FINDING_KEYS = {
    "permissions": "permission",
    "capability_findings": "capability",
    "injection_findings": "injection",
    "ssrf_findings": "ssrf",
    "egress_findings": "egress",
    "trifecta_findings": "trifecta",
    "escalation_findings": "escalation",
    "provenance_findings": "provenance",
    "integrity_findings": "integrity",
}
_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def _to_client_spec(spec: ServerSpec) -> dict:
    d: dict = {}
    if spec.command:
        d["command"] = spec.command
    if spec.args:
        d["args"] = list(spec.args)
    if spec.url:
        d["url"] = spec.url
    if spec.transport in ("http", "sse"):
        d["type"] = spec.transport
    if spec.env_keys:
        # values are unknown to us by design; expose only the keys to the engine
        d["env"] = {k: "" for k in spec.env_keys}
    return d


def _extract_findings(audit: dict) -> tuple[list[dict], str | None]:
    out: list[dict] = []
    for key, category in _FINDING_KEYS.items():
        if key not in audit:
            continue
        items = audit[key]
        if not isinstance(items, list):
            return [], f"invalid MCPAudit findings {key}"
        for f in items:
            if not isinstance(f, dict):
                return [], f"invalid MCPAudit finding in {key}"
            severity = f.get("severity")
            if not isinstance(severity, str) or severity.lower() not in _SEV_RANK:
                return [], f"invalid MCPAudit finding severity in {key}"
            out.append(
                {
                    "rule_id": f.get("rule_id"),
                    "severity": severity.lower(),
                    "title": f.get("title") or f.get("description") or "",
                    "category": category,
                }
            )
    out.sort(key=lambda f: _SEV_RANK[f["severity"]], reverse=True)
    return out[:8], None


def audit_to_grade(audit: object, *, connected: bool = False) -> McpAuditGrade:
    """Parse one MCPAudit ServerAudit dict into our McpAuditGrade.

    Shared by the static (config-only) and connected scan paths so both surface
    the same shape.
    """
    if not isinstance(audit, dict):
        return McpAuditGrade(
            composite=0.0,
            high_risk=False,
            connected=connected,
            error="invalid MCPAudit audit record",
        )
    raw_connection_status = audit.get("connection_status")
    connection_status = raw_connection_status if isinstance(raw_connection_status, str) else None
    tools = audit.get("tools")
    tool_count = len(tools) if isinstance(tools, list) else None

    def unavailable(error: str) -> McpAuditGrade:
        return McpAuditGrade(
            composite=0.0,
            high_risk=False,
            error=error,
            connected=connected,
            connection_status=connection_status,
            tool_count=tool_count,
        )

    if raw_connection_status is not None and connection_status is None:
        return unavailable("invalid MCPAudit connection status")

    rs = audit.get("risk_score")
    if not isinstance(rs, dict):
        rs = {}

    composite = risk_score(rs.get("composite"))
    if composite is None:
        return unavailable("missing or invalid capability composite score")
    dims: dict[str, float] = {}
    for key, value in rs.items():
        if key == "composite":
            continue
        if not isinstance(key, str):
            return unavailable("invalid capability score dimension name")
        score = risk_score(value)
        if score is None:
            return unavailable(f"invalid capability score dimension {key}")
        dims[key] = score

    findings, findings_error = _extract_findings(audit)
    if findings_error:
        return unavailable(findings_error)

    return McpAuditGrade(
        composite=composite,
        high_risk=composite >= 7.0,
        findings=findings,
        dimensions=dims,
        connected=connected,
        connection_status=connection_status,
        tool_count=tool_count,
    )


def grade_mcpaudit(name: str, spec: ServerSpec) -> McpAuditGrade:
    has_command = bool(spec.command and spec.command.strip())
    has_url = bool(spec.url and spec.url.strip())
    if not has_command and not has_url:
        return McpAuditGrade(
            composite=0.0,
            high_risk=False,
            error="missing usable command or URL",
        )

    try:
        from mcp_audit.api import scan_config_only_dict
    except ImportError:
        return McpAuditGrade(composite=0.0, high_risk=False, error="mcp-audits not installed")

    config = {"mcpServers": {name: _to_client_spec(spec)}}
    try:
        with muffle_stdout():
            report = scan_config_only_dict(config, redact=False)
    except Exception as exc:  # never let the engine break discovery
        return McpAuditGrade(composite=0.0, high_risk=False, error=f"{type(exc).__name__}: {exc}")

    if not isinstance(report, dict):
        return McpAuditGrade(
            composite=0.0,
            high_risk=False,
            error="invalid mcp-audits report object",
        )
    schema = report.get("schema_version", 1)
    if schema != 1:
        # The engine's report contract changed shape in a way this adapter was
        # not written for; an explicit error beats mis-parsed grades.
        return McpAuditGrade(
            composite=0.0,
            high_risk=False,
            error=f"unsupported mcp-audits report schema_version {schema}",
        )
    audits = report.get("audits")
    if not isinstance(audits, list):
        return McpAuditGrade(composite=0.0, high_risk=False, error="invalid mcp-audits audits list")
    if not audits:
        return McpAuditGrade(composite=0.0, high_risk=False, error="no audit produced")
    return audit_to_grade(audits[0], connected=False)
