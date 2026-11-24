"""Collector: repo-local ``.mcp.json`` files under the projects root.

Bounded walk (no deeper than ``project_glob_depth``) so we never recurse the
whole disk, and we skip the usual heavy directories.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from stat import S_ISDIR

from ..config import DiscoveryPaths
from ..models import DiscoveredServer, SourceKind
from ._common import load_json, parse_mcp_servers_block
from ._diagnostics import report_entry_error

SOURCE: SourceKind = "project_mcp_json"

_SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "dist", "build", "__pycache__", "target"}
_MAX_FILES = 200  # hard cap so a pathological tree can't stall discovery


def _directory_entries(path: Path, errors: list[str], *, optional: bool = False) -> Iterator[Path]:
    """List a discovery directory, retaining entries seen before a listing error."""
    try:
        entries = os.scandir(path)
    except OSError as exc:
        if not (optional and isinstance(exc, FileNotFoundError)):
            errors.append(f"{path}: {exc.strerror or exc}")
        return
    with entries as iterator:
        try:
            for entry in iterator:
                yield Path(entry.path)
        except OSError as exc:
            errors.append(f"{path}: {exc.strerror or exc}")


class ProjectMcpJsonCollector:
    source = SOURCE

    def __init__(self, paths: DiscoveryPaths) -> None:
        self.paths = paths

    def _find_files(self, root: Path, errors: list[str]) -> tuple[list[Path], bool]:
        found: list[Path] = []
        root_depth = len(root.parts)
        stack = [root]
        while stack and len(found) < _MAX_FILES:
            current = stack.pop()
            for entry in _directory_entries(current, errors, optional=current == root):
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

    def collect(self) -> list[DiscoveredServer]:
        root = self.paths.projects_root
        if root is None:
            return []
        out: list[DiscoveredServer] = []
        errors: list[str] = []
        files, truncated = self._find_files(root, errors)
        if truncated:
            errors.append(f"{root}: project discovery incomplete at {_MAX_FILES}-file limit")
        for message in errors:
            report_entry_error(message)
        for f in files:
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
