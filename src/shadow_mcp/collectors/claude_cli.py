"""Collector: ``claude mcp list``.

The CLI roster is the ground truth for Claude Code: it resolves servers that no
JSON file contains (remote ``claude.ai`` HTTP servers and plugin servers). We
shell out read-only and parse the line-oriented output tolerantly across CLI
versions.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable

from ..models import DiscoveredServer, Provenance, ServerSpec, SourceKind, Transport
from ._common import PartialCollector

SOURCE: SourceKind = "claude_cli"

Runner = Callable[[], "tuple[int, str]"]

_URL_RE = re.compile(r"https?://\S+")
# Trailing status decoration: " - ✓ Connected", " (HTTP)", " - Failed to connect"
_STATUS_RE = re.compile(r"(?:^|\s+)-\s+.*$")


def _default_runner() -> tuple[int, str]:
    exe = shutil.which("claude")
    if not exe:
        return (127, "")
    try:
        proc = subprocess.run(
            [exe, "mcp", "list"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return (1, "")
    return (proc.returncode, proc.stdout or "")


def parse_claude_mcp_list(text: str, errors: list[str] | None = None) -> list[DiscoveredServer]:
    """Parse ``claude mcp list`` output into DiscoveredServer records."""
    out: list[DiscoveredServer] = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if (
            not line
            or line.rstrip(".…") == "Checking MCP server health"
            or line.partition(".")[0] == "No MCP servers configured"
        ):
            continue
        name, _, rest = line.partition(":")
        name = name.strip()
        rest = rest.strip()
        # drop a "- Connected" / "- Failed" status tail and any "(HTTP)" hint
        had_http_hint = "(http" in rest.lower()
        rest = _STATUS_RE.sub("", rest).strip()
        rest = re.sub(r"\((?:HTTP|SSE|STDIO)\)", "", rest, flags=re.IGNORECASE).strip()
        if not name or not rest:
            if errors is not None:
                errors.append(f"malformed claude mcp list row {number}")
            continue

        url_match = _URL_RE.search(rest)
        if url_match:
            url = url_match.group(0)
            transport: Transport = "sse" if "sse" in url.lower() else "http"
            spec = ServerSpec(transport=transport, url=url)
        else:
            tokens = rest.split()
            transport = "http" if had_http_hint else "stdio"
            spec = ServerSpec(
                transport=transport,
                command=tokens[0],
                args=tokens[1:],
            )
        out.append(
            DiscoveredServer(
                name=name,
                spec=spec,
                provenance=Provenance(
                    source=SOURCE,
                    location="claude mcp list",
                    scope="user",
                    declared_name=name,
                ),
            )
        )
    return out


class ClaudeCliCollector(PartialCollector):
    source = SOURCE

    def __init__(self, runner: Runner | None = None) -> None:
        self.runner = runner or _default_runner

    def collect_with_errors(self, errors: list[str]) -> list[DiscoveredServer]:
        code, text = self.runner()
        if code != 0:
            errors.append(f"claude mcp list failed with exit status {code}")
        return parse_claude_mcp_list(text, errors)
