"""Shared parsing for the common ``mcpServers`` config shape.

Used by every collector whose source stores servers as a name -> spec map
(Claude Code, project .mcp.json, Claude Desktop). Codex (TOML), the CLI, the
DXT manifests, and process discovery have their own shapes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import DiscoveredServer, Provenance, ServerSpec, SourceKind, Transport


def load_json(path: Path) -> dict[str, Any] | None:
    """Read + parse a JSON file, returning None on any read/parse failure.

    Read-only and fail-soft: a missing or malformed config must never break
    discovery.
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def infer_spec(raw: dict[str, Any]) -> ServerSpec:
    """Normalize one raw server dict into a redacted ServerSpec."""
    command = raw.get("command")
    args_raw = raw.get("args") or []
    args = [str(a) for a in args_raw] if isinstance(args_raw, list) else []
    url = raw.get("url") or raw.get("serverUrl") or raw.get("endpoint")
    env = raw.get("env")
    env_keys = sorted(env.keys()) if isinstance(env, dict) else []

    declared = (raw.get("type") or raw.get("transport") or "").lower()
    transport: Transport
    if declared in ("stdio", "http", "sse"):
        transport = declared  # type: ignore[assignment]
    elif url and not command:
        transport = "sse" if "sse" in str(url).lower() else "http"
    elif command:
        transport = "stdio"
    else:
        transport = "unknown"

    return ServerSpec(
        transport=transport,
        command=str(command) if command else None,
        args=args,
        url=str(url) if url else None,
        env_keys=env_keys,
    )


def parse_mcp_servers_block(
    block: Any,
    *,
    source: SourceKind,
    location: str,
    scope: str,
) -> list[DiscoveredServer]:
    """Turn a ``mcpServers`` map into DiscoveredServer records."""
    if not isinstance(block, dict):
        return []
    out: list[DiscoveredServer] = []
    for name, raw in block.items():
        if not isinstance(raw, dict):
            continue
        enabled = raw.get("enabled")
        out.append(
            DiscoveredServer(
                name=str(name),
                spec=infer_spec(raw),
                provenance=Provenance(
                    source=source,
                    location=location,
                    scope=scope,
                    declared_name=str(name),
                    enabled=enabled if isinstance(enabled, bool) else None,
                ),
            )
        )
    return out
