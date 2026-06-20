"""Collector: repo-local ``.mcp.json`` files under the projects root.

Bounded walk (no deeper than ``project_glob_depth``) so we never recurse the
whole disk, and we skip the usual heavy directories.
"""

from __future__ import annotations

from pathlib import Path

from ..config import DiscoveryPaths
from ..models import DiscoveredServer
from ._common import load_json, parse_mcp_servers_block

SOURCE = "project_mcp_json"

_SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "dist", "build", "__pycache__", "target"}
_MAX_FILES = 200  # hard cap so a pathological tree can't stall discovery


class ProjectMcpJsonCollector:
    source = SOURCE

    def __init__(self, paths: DiscoveryPaths) -> None:
        self.paths = paths

    def _find_files(self, root: Path) -> list[Path]:
        found: list[Path] = []
        root_depth = len(root.parts)
        stack = [root]
        while stack and len(found) < _MAX_FILES:
            current = stack.pop()
            try:
                entries = list(current.iterdir())
            except OSError:
                continue
            for entry in entries:
                try:
                    if entry.is_dir():
                        if entry.name in _SKIP_DIRS or entry.name.startswith("."):
                            if entry.name not in {".cursor", ".vscode"}:
                                continue
                        if len(entry.parts) - root_depth < self.paths.project_glob_depth:
                            stack.append(entry)
                    elif entry.name in (".mcp.json", "mcp.json"):
                        found.append(entry)
                except OSError:
                    continue
        return found

    def collect(self) -> list[DiscoveredServer]:
        root = self.paths.projects_root
        if root is None or not root.exists():
            return []
        out: list[DiscoveredServer] = []
        for f in self._find_files(root):
            data = load_json(f)
            if data is None:
                continue
            out.extend(
                parse_mcp_servers_block(
                    data.get("mcpServers"),
                    source=SOURCE,
                    location=str(f),
                    scope="project",
                )
            )
        return out
