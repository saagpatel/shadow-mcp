"""Collector: repo-local ``.mcp.json`` files under the projects root.

Bounded walk (no deeper than ``project_glob_depth``) so we never recurse the
whole disk, and we skip the usual heavy directories.
"""

from __future__ import annotations

from pathlib import Path
from stat import S_ISDIR

from ..config import directory_entries
from ..models import DiscoveredServer, SourceKind
from ._common import ConfigCollector, load_json, parse_mcp_servers_block

SOURCE: SourceKind = "project_mcp_json"

_SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "dist", "build", "__pycache__", "target"}
_MAX_FILES = 200  # hard cap so a pathological tree can't stall discovery


class ProjectMcpJsonCollector(ConfigCollector):
    source = SOURCE

    def _find_files(self, root: Path, errors: list[str]) -> tuple[list[Path], bool]:
        found: list[Path] = []
        root_depth = len(root.parts)
        stack = [root]
        while stack and len(found) < _MAX_FILES:
            current = stack.pop()
            for entry in directory_entries(current, errors, optional=current == root):
                config_name = entry.name in (".mcp.json", "mcp.json")
                visit_dir = (
                    len(entry.parts) - root_depth < self.paths.project_glob_depth
                    and entry.name not in _SKIP_DIRS
                    and (not entry.name.startswith(".") or entry.name in {".cursor", ".vscode"})
                )
                if not (config_name or visit_dir):
                    continue
                try:
                    if S_ISDIR(entry.stat().st_mode):
                        if visit_dir:
                            stack.append(entry)
                    elif config_name:
                        if len(found) == _MAX_FILES:
                            return found, True
                        found.append(entry)
                except FileNotFoundError:  # dangling symlink or removed while walking
                    if config_name:
                        errors.append(f"{entry}: listed configuration is missing")
                    continue
                except OSError as exc:
                    errors.append(f"{entry}: {exc.strerror or exc}")
        return found, bool(stack)

    def collect_with_errors(self, errors: list[str]) -> list[DiscoveredServer]:
        root = self.paths.projects_root
        if root is None:
            return []
        out: list[DiscoveredServer] = []
        files, truncated = self._find_files(root, errors)
        if truncated:
            errors.append(f"{root}: project discovery incomplete at {_MAX_FILES}-file limit")
        for f in files:
            try:
                data = load_json(f)
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
                continue
            if data is None:
                errors.append(f"{f}: listed configuration is missing")
                continue
            out.extend(
                parse_mcp_servers_block(
                    data.get("mcpServers", {}),
                    errors=errors,
                    source=SOURCE,
                    location=str(f),
                    scope="project",
                )
            )
        return out
