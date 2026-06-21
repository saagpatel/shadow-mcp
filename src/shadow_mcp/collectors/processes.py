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
# A parent process that means "this MCP server was spawned by a host/plugin"
# (a managed child), not a standalone rogue daemon.
_HOST_PARENT_MARKERS = (
    "claude",
    "codex",
    "claude.app",
    "codex.app",
    "/disclaimer",
    "cursor",
    "windsurf",
    "code helper",
    "node_modules/.bin",
    "npm exec",
    "npx ",
    "mcp-server",
    "modelcontextprotocol",
    # agent gateways/clients that spawn MCP servers but aren't config-enumerated
    "hermes",
    "hermes_cli",
    ".hermes/",
)
# Launcher shims that wrap the real owner (`uv run python ...`, `npx ...`, a
# shell). The real client is one or more levels up, so we climb past these to
# find who actually owns the MCP process before deciding it's a rogue.
_LAUNCHER_BASENAMES = {
    "uv",
    "uvx",
    "npx",
    "npm",
    "pnpm",
    "bunx",
    "yarn",
    "sh",
    "bash",
    "zsh",
    "env",
    "login",
    "exec",
}
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

_PID_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(.*)$")
_SCRIPT_RE = re.compile(r"(\S+mcp[-_]server\S*\.(?:js|mjs|ts|py))")
_RUN_PKG_RE = re.compile(r"\b(?:npx|uvx|bunx)\s+(?:(?:-y|--yes)\s+)*(@?[\w./-]+)")
_UV_RUN_RE = re.compile(r"\brun\s+(@?[\w./-]+)\s*$")
_MODULE_RE = re.compile(r"-m\s+([\w.]+)")
_DIRECTORY_RE = re.compile(r"--directory\s+(/.+?)(?:\s+(?:run|python[\d.]*|node|--)\b|$)")
_BIN_MCP_RE = re.compile(r"(?:^|/)([\w.-]+-mcp(?:-server)?)\b")


def _default_runner() -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["ps", "-axww", "-o", "pid=,ppid=,command="],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return (1, "")
    return (proc.returncode, proc.stdout or "")


def _is_host_parent(parent_cmd: str) -> bool:
    low = parent_cmd.lower()
    if not low:
        return False  # unknown parent -> treat as standalone (worth attention)
    return any(m in low for m in _HOST_PARENT_MARKERS)


def _executable_basename(cmd: str) -> str:
    toks = cmd.split()
    return toks[0].rsplit("/", 1)[-1].lower() if toks else ""


def _resolve_owner(ppid: str, pid_cmd: dict[str, str], pid_ppid: dict[str, str]) -> tuple[str, str]:
    """Climb past launcher shims (`uv run`, `npx`, a shell) to the real owner.

    A server spawned by Hermes shows an immediate parent of ``uv run ...``; the
    actual client is one or more hops up. We follow the chain past known
    launchers so an agent-managed server isn't mistaken for a standalone rogue.
    """
    cur = ppid
    seen: set[str] = set()
    depth = 0
    while cur and cur not in seen and depth < 10:
        seen.add(cur)
        cmd = pid_cmd.get(cur, "")
        if cur == "1":
            return cur, cmd  # launchd: a true standalone
        base = _executable_basename(cmd)
        if base in _LAUNCHER_BASENAMES or "disclaimer" in cmd.lower():
            nxt = pid_ppid.get(cur)
            if not nxt:
                return cur, cmd
            cur = nxt
            depth += 1
            continue
        return cur, cmd
    return cur, pid_cmd.get(cur, "")


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
    # First pass: map pid -> command and pid -> ppid so we can walk parent chains.
    rows: list[tuple[str, str, str]] = []
    pid_cmd: dict[str, str] = {}
    pid_ppid: dict[str, str] = {}
    for line in text.splitlines():
        m = _PID_RE.match(line)
        if not m:
            continue
        pid, ppid, cmdline = m.group(1), m.group(2), m.group(3).strip()
        pid_cmd[pid] = cmdline
        pid_ppid[pid] = ppid
        rows.append((pid, ppid, cmdline))

    out: list[DiscoveredServer] = []
    seen: set[str] = set()  # one sighting per identity (processes spawn many PIDs)
    for pid, ppid, cmdline in rows:
        if not _looks_like_mcp(cmdline):
            continue
        name = extract_identity(cmdline)
        if not name or name in seen:
            continue
        seen.add(name)
        # Resolve the real owner past any launcher shims, then classify on it.
        owner_pid, parent_cmd = _resolve_owner(ppid, pid_cmd, pid_ppid)
        host_managed = False if owner_pid == "1" else _is_host_parent(parent_cmd)
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
                    host_managed=host_managed,
                    parent=parent_cmd[:80] or None,
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
