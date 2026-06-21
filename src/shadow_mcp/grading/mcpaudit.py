"""Delegate capability grading to the MCPAudit engine.

We call ``mcp_audit.api.scan_config_only_dict`` (static, no spawn, no network)
per server so one malformed spec cannot void every grade. The engine is an
optional import: if it is not installed, grading degrades to ``error`` and
discovery still works.
"""

from __future__ import annotations

from ..models import McpAuditGrade, ServerSpec

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
_SEV_RANK = {"high": 3, "medium": 2, "low": 1}


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


def _extract_findings(audit: dict) -> list[dict]:
    out: list[dict] = []
    for key, category in _FINDING_KEYS.items():
        items = audit.get(key)
        if not isinstance(items, list):
            continue
        for f in items:
            if not isinstance(f, dict):
                continue
            out.append(
                {
                    "rule_id": f.get("rule_id"),
                    "severity": str(f.get("severity") or "").lower(),
                    "title": f.get("title") or f.get("description") or "",
                    "category": category,
                }
            )
    out.sort(key=lambda f: _SEV_RANK.get(f["severity"], 0), reverse=True)
    return out[:8]


def audit_to_grade(audit: dict, *, connected: bool = False) -> McpAuditGrade:
    """Parse one MCPAudit ServerAudit dict into our McpAuditGrade.

    Shared by the static (config-only) and connected scan paths so both surface
    the same shape.
    """
    rs = audit.get("risk_score") or {}
    composite = float(rs.get("composite") or 0.0)
    dims = {k: float(v) for k, v in rs.items() if k != "composite" and isinstance(v, (int, float))}
    tools = audit.get("tools")
    return McpAuditGrade(
        composite=composite,
        high_risk=composite >= 7.0,
        findings=_extract_findings(audit),
        dimensions=dims,
        connected=connected,
        connection_status=audit.get("connection_status"),
        tool_count=len(tools) if isinstance(tools, list) else None,
    )


def grade_mcpaudit(name: str, spec: ServerSpec) -> McpAuditGrade:
    try:
        from mcp_audit.api import scan_config_only_dict
    except ImportError:
        return McpAuditGrade(composite=0.0, high_risk=False, error="mcp-audits not installed")

    config = {"mcpServers": {name: _to_client_spec(spec)}}
    try:
        report = scan_config_only_dict(config, redact=False)
    except Exception as exc:  # never let the engine break discovery
        return McpAuditGrade(composite=0.0, high_risk=False, error=f"{type(exc).__name__}: {exc}")

    audits = report.get("audits") or []
    if not audits:
        return McpAuditGrade(composite=0.0, high_risk=False, error="no audit produced")
    return audit_to_grade(audits[0], connected=False)
