"""Collector: live MCP transports from the process table.

stdio MCP servers bind no port, so a port scan misses them; they are
pipe-attached children of the host. Matching the process command line is the
only way to see them at runtime.

The launcher is almost never the identity: a server shows up as
``node .../personal-ops/.../mcp-server.js`` or
``uv --directory .../macos-mcp run macos-mcp`` (with spaces that break naive
tokenization) or behind a ``disclaimer`` wrapper. We extract the real identity
from the raw command line and, crucially, **skip any process we cannot
confidently name** rather than inventing a noisy false "shadow server".
"""

from __future__ import annotations

import re
import subprocess
from typing import Callable

from ..models import DiscoveredServer, Provenance, ServerSpec

SOURCE = "process"

Runner = Callable[[], "tuple[int, str]"]

# Strong markers that gate a line into consideration (avoid the bare token "mcp").
_MARKERS = (
    "mcp-server",
    "mcp_server",
    "start-mcp-server",
    "modelcontextprotocol",
    "context7-mcp",
    "server-github",
    "/mcp-server.js",
    "mcp_config",
    "-mcp ",
    "-mcp.js",
)
_SELF_EXCLUDE = ("shadow-mcp", "shadow_mcp")
# Path components that are scaffolding, not the project identity.
_PATH_NOISE = {
    "app",
    "dist",
    "src",
    "build",
    "lib",
    "out",
    "bin",
    "node_modules",
    ".venv",
    "venv",
    "contents",
    "helpers",
    "mcp_server",
    "mcp-server",
    "mcpserver",
    "server",
    "macos",
    "darwin",
}

_PID_RE = re.compile(r"^\s*(\d+)\s+(.*)$")
_SCRIPT_RE = re.compile(r"(\S+mcp[-_]server\S*\.(?:js|mjs|ts|py))")
_RUN_PKG_RE = re.compile(r"\b(?:npx|uvx|bunx)\s+(?:(?:-y|--yes)\s+)*(@?[\w./-]+)")
_UV_RUN_RE = re.compile(r"\brun\s+(@?[\w./-]+)\s*$")
_MODULE_RE = re.compile(r"-m\s+([\w.]+)")
_DIRECTORY_RE = re.compile(r"--directory\s+(/.+?)(?:\s+(?:run|python[\d.]*|node|--)\b|$)")
_BIN_MCP_RE = re.compile(r"(?:^|/)([\w.-]+-mcp(?:-server)?)\b")


def _default_runner() -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["ps", "-axww", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return (1, "")
    return (proc.returncode, proc.stdout or "")


def _looks_like_mcp(cmdline: str) -> bool:
    low = cmdline.lower()
    if any(s in low for s in _SELF_EXCLUDE):
        return False
    return any(m in low for m in _MARKERS)


def _project_from_path(path: str, *, drop_last: bool) -> str | None:
    parts = [p for p in path.split("/") if p]
    if drop_last:
        parts = parts[:-1]
    for p in reversed(parts):
        if p.lower() not in _PATH_NOISE:
            return p
    return parts[-1] if parts else None


def extract_identity(cmdline: str) -> str | None:
    """Pull a confident server name from a raw process command line, or None."""
    # 1. an explicit mcp-server script: identify by its project directory
    m = _SCRIPT_RE.search(cmdline)
    if m:
        name = _project_from_path(m.group(1), drop_last=True)
        if name:
            return name.lower()
    # 2. a *-mcp / *-mcp-server executable
    m = _BIN_MCP_RE.search(cmdline.split(" --", 1)[0])  # only the executable region
    if m:
        return m.group(1).lower()
    # 3. a package run: `npx @scope/pkg`, `uvx pkg`, or `... run pkg`
    m = _RUN_PKG_RE.search(cmdline) or _UV_RUN_RE.search(cmdline)
    if m:
        pkg = m.group(1)
        return pkg.split("/")[-1].lower() if "/" in pkg and not pkg.startswith("@") else pkg.lower()
    # 4. a python module
    m = _MODULE_RE.search(cmdline)
    if m:
        return m.group(1).lower()
    # 5. a working directory we can name the project from
    m = _DIRECTORY_RE.search(cmdline)
    if m:
        name = _project_from_path(m.group(1).strip(), drop_last=False)
        if name:
            return name.lower()
    return None


def parse_ps_output(text: str) -> list[DiscoveredServer]:
    out: list[DiscoveredServer] = []
    seen: set[str] = set()  # one sighting per identity (processes spawn many PIDs)
    for line in text.splitlines():
        m = _PID_RE.match(line)
        if not m:
            continue
        pid, cmdline = m.group(1), m.group(2).strip()
        if not _looks_like_mcp(cmdline):
            continue
        name = extract_identity(cmdline)
        if not name or name in seen:
            continue
        seen.add(name)
        tokens = cmdline.split()
        spec = ServerSpec(
            transport="stdio",
            command=tokens[0] if tokens else None,
            args=tokens[1:],
        )
        out.append(
            DiscoveredServer(
                name=name,
                spec=spec,
                provenance=Provenance(
                    source=SOURCE,
                    location=f"ps:pid={pid}",
                    scope="runtime",
                    declared_name=name,
                ),
            )
        )
    return out


class ProcessCollector:
    source = SOURCE

    def __init__(self, runner: Runner | None = None) -> None:
        self.runner = runner or _default_runner

    def collect(self) -> list[DiscoveredServer]:
        code, text = self.runner()
        if code != 0 or not text.strip():
            return []
        return parse_ps_output(text)
