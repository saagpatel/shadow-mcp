"""Collector: Claude Code ``~/.claude.json``.

Two scopes live in this file: top-level ``mcpServers`` (user scope) and
per-project ``projects.<path>.mcpServers`` (project scope).
"""

from __future__ import annotations

from ..models import DiscoveredServer, SourceKind
from ._common import ConfigCollector, load_json, parse_mcp_servers_block

SOURCE: SourceKind = "claude_code"


class ClaudeCodeCollector(ConfigCollector):
    source = SOURCE

    def collect_with_errors(self, errors: list[str]) -> list[DiscoveredServer]:
        data = load_json(self.paths.claude_json)
        if data is None:
            return []
        loc = str(self.paths.claude_json)
        out = parse_mcp_servers_block(
            data.get("mcpServers", {}),
            errors=errors,
            source=SOURCE,
            location=loc,
            scope="user",
        )
        projects = data.get("projects", {})
        if not isinstance(projects, dict):
            errors.append(f"{loc}: projects must be an object")
            return out
        for proj_path, proj in projects.items():
            project_loc = f"{loc}#projects.{proj_path}"
            if not isinstance(proj, dict):
                errors.append(f"{project_loc}: project must be an object")
                continue
            out.extend(
                parse_mcp_servers_block(
                    proj.get("mcpServers", {}),
                    errors=errors,
                    source=SOURCE,
                    location=project_loc,
                    scope="project",
                )
            )
        return out
