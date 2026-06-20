"""Collector: Claude Code ``~/.claude.json``.

Two scopes live in this file: top-level ``mcpServers`` (user scope) and
per-project ``projects.<path>.mcpServers`` (project scope).
"""

from __future__ import annotations

from ..config import DiscoveryPaths
from ..models import DiscoveredServer
from ._common import load_json, parse_mcp_servers_block

SOURCE = "claude_code"


class ClaudeCodeCollector:
    source = SOURCE

    def __init__(self, paths: DiscoveryPaths) -> None:
        self.paths = paths

    def collect(self) -> list[DiscoveredServer]:
        data = load_json(self.paths.claude_json)
        if data is None:
            return []
        loc = str(self.paths.claude_json)
        out = parse_mcp_servers_block(
            data.get("mcpServers"), source=SOURCE, location=loc, scope="user"
        )
        projects = data.get("projects")
        if isinstance(projects, dict):
            for proj_path, proj in projects.items():
                if not isinstance(proj, dict):
                    continue
                out.extend(
                    parse_mcp_servers_block(
                        proj.get("mcpServers"),
                        source=SOURCE,
                        location=f"{loc}#projects.{proj_path}",
                        scope="project",
                    )
                )
        return out
