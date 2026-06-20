"""Compose a final risk band from delegated grades + the local OWASP layer.

The numeric base stays delegated (MCPAudit composite); mcp-trust and the
config-shaped local dimensions (secrets/MCP01, transport/MCP07) adjust it, and
every contribution is recorded in ``reasons`` with its OWASP ID so the verdict
is explainable.
"""

from __future__ import annotations

from ..models import (
    Band,
    InventoryEntry,
    McpAuditGrade,
    McpTrustGrade,
    RiskAssessment,
)

_ORDER: list[Band] = ["unknown", "low", "medium", "high", "critical"]


def _bump(band: Band, steps: int = 1) -> Band:
    if band == "unknown":
        return band
    idx = min(_ORDER.index(band) + steps, len(_ORDER) - 1)
    return _ORDER[idx]


def _band_from_composite(composite: float) -> Band:
    if composite >= 7.0:
        return "critical"
    if composite >= 5.0:
        return "high"
    if composite >= 3.5:
        return "medium"
    return "low"  # 0 included: assessed as minimal, not unknown


def assess(
    entry: InventoryEntry,
    mcpaudit: McpAuditGrade | None,
    mcptrust: McpTrustGrade | None,
) -> RiskAssessment:
    reasons: list[str] = []

    if mcpaudit is None or mcpaudit.error:
        band: Band = "unknown"
        if mcpaudit and mcpaudit.error:
            reasons.append(f"capability grade unavailable ({mcpaudit.error})")
    else:
        band = _band_from_composite(mcpaudit.composite)
        reasons.append(f"MCPAudit capability composite {mcpaudit.composite:.1f}/10 (MCP02/MCP05)")
        top = next((f for f in mcpaudit.findings if f["severity"] == "high"), None)
        if top:
            reasons.append(f"high finding: {top['title']} [{top['category']}] (MCP03/MCP10)")

    # mcp-trust danger letter raises the band. A registry grade is authoritative;
    # a computed grade is derived from MCPAudit dims via mcp-trust's grade() logic.
    if mcptrust and mcptrust.grade not in (None, "unknown"):
        origin = "computed" if mcptrust.computed else "registry"
        if mcptrust.grade in ("D", "F"):
            band = _bump(band) if band != "unknown" else "high"
            reasons.append(f"mcp-trust danger grade {mcptrust.grade} ({origin})")
        else:
            reasons.append(f"mcp-trust grade {mcptrust.grade} ({origin})")

    # MCP07: network-reachable transport widens blast radius.
    if entry.spec.transport in ("http", "sse"):
        if band in ("low", "medium"):
            band = _bump(band)
        reasons.append(f"{entry.spec.transport} transport is network-reachable (MCP07)")

    # MCP01: secret-bearing launch config.
    secrets = entry.spec.secret_env_keys
    if secrets:
        reasons.append(f"handles secrets via env: {', '.join(secrets)} (MCP01)")

    # MCP09: blast radius across hosts.
    if entry.host_count >= 3:
        reasons.append(f"declared on {entry.host_count} hosts (broad reach, MCP09)")

    headline = band.upper()
    extras = []
    if mcptrust and mcptrust.grade not in (None, "unknown"):
        # a trailing ~ marks a computed grade vs an authoritative registry one
        mark = "~" if mcptrust.computed else ""
        extras.append(f"trust {mcptrust.grade}{mark}")
    if mcpaudit and not mcpaudit.error:
        extras.append(f"cap {mcpaudit.composite:.1f}")
    if extras:
        headline = f"{band.upper()} ({', '.join(extras)})"

    return RiskAssessment(
        band=band,
        headline=headline,
        mcpaudit=mcpaudit,
        mcptrust=mcptrust,
        reasons=reasons,
    )
