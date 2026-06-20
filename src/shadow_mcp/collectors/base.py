"""Discovery orchestration: run every collector, fail-soft, and tally sources.

A single collector raising must never break discovery, so each is wrapped; its
error is recorded as a note and the sweep continues.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import DiscoveryPaths
from ..models import DiscoveredServer
from .claude_cli import ClaudeCliCollector
from .claude_code import ClaudeCodeCollector
from .claude_desktop import ClaudeDesktopCollector
from .codex import CodexCollector
from .dxt import DxtCollector
from .processes import ProcessCollector
from .project_mcp import ProjectMcpJsonCollector


@dataclass
class DiscoveryResult:
    servers: list[DiscoveredServer] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def default_collectors(
    paths: DiscoveryPaths,
    *,
    include_processes: bool = True,
    include_cli: bool = True,
) -> list[object]:
    collectors: list[object] = [
        ClaudeCodeCollector(paths),
        ClaudeDesktopCollector(paths),
        CodexCollector(paths),
        DxtCollector(paths),
        ProjectMcpJsonCollector(paths),
    ]
    if include_cli:
        collectors.append(ClaudeCliCollector())
    if include_processes:
        collectors.append(ProcessCollector())
    return collectors


def discover_all(
    paths: DiscoveryPaths | None = None,
    *,
    include_processes: bool = True,
    include_cli: bool = True,
    collectors: list[object] | None = None,
) -> DiscoveryResult:
    paths = paths or DiscoveryPaths.default()
    cols = (
        collectors
        if collectors is not None
        else default_collectors(paths, include_processes=include_processes, include_cli=include_cli)
    )
    result = DiscoveryResult()
    for col in cols:
        source = getattr(col, "source", col.__class__.__name__)
        try:
            found = col.collect()  # type: ignore[attr-defined]
        except Exception as exc:  # a collector must never break the sweep
            result.errors.append(f"{source}: {type(exc).__name__}: {exc}")
            continue
        result.servers.extend(found)
        result.source_counts[source] = result.source_counts.get(source, 0) + len(found)
    return result
