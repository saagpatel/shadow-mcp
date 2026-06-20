"""Collector: Claude Desktop ``claude_desktop_config.json``."""

from __future__ import annotations

from ..config import DiscoveryPaths
from ..models import DiscoveredServer
from ._common import load_json, parse_mcp_servers_block

SOURCE = "claude_desktop"


class ClaudeDesktopCollector:
    source = SOURCE

    def __init__(self, paths: DiscoveryPaths) -> None:
        self.paths = paths

    def collect(self) -> list[DiscoveredServer]:
        data = load_json(self.paths.claude_desktop_config)
        if data is None:
            return []
        return parse_mcp_servers_block(
            data.get("mcpServers"),
            source=SOURCE,
            location=str(self.paths.claude_desktop_config),
            scope="desktop",
        )
