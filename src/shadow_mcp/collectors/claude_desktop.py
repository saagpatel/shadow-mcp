"""Collector: Claude Desktop ``claude_desktop_config.json``."""

from __future__ import annotations

from ..models import DiscoveredServer, SourceKind
from ._common import ConfigCollector, load_json, parse_mcp_servers_block

SOURCE: SourceKind = "claude_desktop"


class ClaudeDesktopCollector(ConfigCollector):
    source = SOURCE

    def collect_with_errors(self, errors: list[str]) -> list[DiscoveredServer]:
        data = load_json(self.paths.claude_desktop_config)
        if data is None:
            return []
        return parse_mcp_servers_block(
            data.get("mcpServers"),
            errors=errors,
            source=SOURCE,
            location=str(self.paths.claude_desktop_config),
            scope="desktop",
        )
