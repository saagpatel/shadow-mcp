"""Shared parsing for the common ``mcpServers`` config shape.

Used by every collector whose source stores servers as a name -> spec map
(Claude Code, project .mcp.json, Claude Desktop). Codex (TOML), the CLI, the
DXT manifests, and process discovery have their own shapes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..models import DiscoveredServer, Provenance, ServerSpec, SourceKind, Transport


def _resolve_rel(value: str, base_dir: str | None) -> str:
    """Canonicalize an explicitly-relative path (``./x``, ``../x``) against the
    config's directory.

    A config that declares ``node ./mcp-server.js`` and the same server seen as an
    absolute path in the process table would otherwise produce different identity
    signatures and false-split into a config entry plus a phantom running server.
    Only ``./`` / ``../`` forms are touched, so package names and flags are left
    alone.
    """
    if base_dir and (value.startswith("./") or value.startswith("../")):
        return os.path.normpath(os.path.join(base_dir, value))
    return value


def _config_base_dir(location: str) -> str | None:
    """The filesystem directory a config's relative paths resolve against."""
    # Claude Code encodes the project dir after '#projects.' (project scope).
    if "#projects." in location:
        return location.split("#projects.", 1)[1] or None
    if "#" in location:  # other synthetic locations have no filesystem base
        return None
    return os.path.dirname(location) or None


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


def infer_spec(raw: dict[str, Any], base_dir: str | None = None) -> ServerSpec:
    """Normalize one raw server dict into a redacted ServerSpec.

    ``base_dir`` (the config's directory) canonicalizes relative command/script
    paths so they match the absolute form seen in the process table.
    """
    command = raw.get("command")
    command = _resolve_rel(str(command), base_dir) if command else None
    args_raw = raw.get("args") or []
    args = [_resolve_rel(str(a), base_dir) for a in args_raw] if isinstance(args_raw, list) else []
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
    base_dir = _config_base_dir(location)
    out: list[DiscoveredServer] = []
    for name, raw in block.items():
        if not isinstance(raw, dict):
            continue
        enabled = raw.get("enabled")
        out.append(
            DiscoveredServer(
                name=str(name),
                spec=infer_spec(raw, base_dir),
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
