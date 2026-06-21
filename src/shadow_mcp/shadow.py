"""Derive the 'shadow' deltas — the findings that make this more than a list.

These are the MCP09 signals: servers running outside any config, servers wired
into many hosts (broad reach), capable servers with no authoritative grade,
disabled-but-still-present servers, and known adversarial fixtures.
"""

from __future__ import annotations

from .models import GradedServer, ShadowFinding

_ADVERSARIAL_HINTS = ("adv-", "poisoned", "fixture", "fake-")


def _is_adversarial(graded: GradedServer) -> bool:
    name = graded.entry.canonical_name.lower()
    if any(h in name for h in _ADVERSARIAL_HINTS):
        return True
    for p in graded.entry.provenances:
        loc = p.location.lower()
        if any(h in loc for h in _ADVERSARIAL_HINTS):
            return True
    return False


def build_shadow_findings(graded: list[GradedServer]) -> list[ShadowFinding]:
    findings: list[ShadowFinding] = []
    for g in graded:
        e = g.entry

        if _is_adversarial(g):
            findings.append(
                ShadowFinding(
                    kind="adversarial_fixture",
                    server=e.canonical_name,
                    detail="matches a known adversarial/poisoned MCP fixture pattern",
                    band="high",
                )
            )

        if e.running and not e.configured:
            if e.standalone_process:
                findings.append(
                    ShadowFinding(
                        kind="running_unconfigured",
                        server=e.canonical_name,
                        detail=(
                            "live MCP process not spawned by any MCP host and absent "
                            "from every config (MCP09 shadow server)"
                        ),
                        band="high",
                    )
                )
            else:
                findings.append(
                    ShadowFinding(
                        kind="host_spawned_unconfigured",
                        server=e.canonical_name,
                        detail=(
                            "running form of a host/plugin-managed server (spawned by "
                            "an MCP host, not in any user config)"
                        ),
                        band="low",
                    )
                )

        if e.host_count >= 3:
            findings.append(
                ShadowFinding(
                    kind="broad_blast_radius",
                    server=e.canonical_name,
                    detail=f"declared across {e.host_count} hosts: {', '.join(e.sources)}",
                    band="medium",
                )
            )

        if g.risk.band in ("high", "critical") and (
            g.risk.mcptrust is None or g.risk.mcptrust.grade in (None, "unknown")
        ):
            findings.append(
                ShadowFinding(
                    kind="ungraded_capable",
                    server=e.canonical_name,
                    detail=f"{g.risk.band} capability but no authoritative mcp-trust grade",
                    band="medium",
                )
            )

        if e.disabled:
            findings.append(
                ShadowFinding(
                    kind="disabled_present",
                    server=e.canonical_name,
                    detail="disabled in config but still present on disk",
                    band="low",
                )
            )

    rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unknown": 0}
    findings.sort(key=lambda f: rank.get(f.band, 0), reverse=True)
    return findings
