"""Shared parsing for the common ``mcpServers`` config shape.

Used by every collector whose source stores servers as a name -> spec map
(Claude Code, project .mcp.json, Claude Desktop). Codex (TOML), the CLI, the
DXT manifests, and process discovery have their own shapes.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, cast

from ..config import DiscoveryPaths
from ..models import DiscoveredServer, Provenance, ServerSpec, SourceKind, Transport


class ConfigCollector(ABC):
    source: SourceKind

    def __init__(self, paths: DiscoveryPaths) -> None:
        self.paths = paths

    def collect(self) -> list[DiscoveredServer]:
        errors: list[str] = []
        servers = self.collect_with_errors(errors)
        if errors:
            raise ValueError("\n".join(errors))
        return servers

    @abstractmethod
    def collect_with_errors(self, errors: list[str]) -> list[DiscoveredServer]: ...


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


MAX_CONFIG_BYTES = 16 * 1024 * 1024


def read_config(path: Path) -> bytes | None:
    """Bound the allocation even when file metadata is unavailable or stale."""
    try:
        with path.open("rb") as fh:
            data = fh.read(MAX_CONFIG_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(data) > MAX_CONFIG_BYTES:
        raise ValueError(f"{path}: configuration exceeds {MAX_CONFIG_BYTES} bytes")
    return data


def load_json(path: Path) -> dict[str, Any] | None:
    """Read an optional JSON configuration object."""
    raw = read_config(path)
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path}: invalid JSON ({type(exc).__name__})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def infer_spec(raw: dict[str, Any], base_dir: str | None = None) -> ServerSpec:
    """Normalize one raw server dict into a redacted ServerSpec.

    ``base_dir`` (the config's directory) canonicalizes relative command/script
    paths so they match the absolute form seen in the process table.
    """
    for field in ("command", "url", "serverUrl", "endpoint", "type", "transport"):
        if field in raw and not isinstance(raw[field], str):
            raise ValueError(f"{field} must be a string")
    command = raw.get("command")
    command = _resolve_rel(command, base_dir) if command else None
    args_raw = raw.get("args", [])
    if not isinstance(args_raw, list) or not all(isinstance(a, str) for a in args_raw):
        raise ValueError("args must be an array of strings")
    args = [_resolve_rel(a, base_dir) for a in args_raw]
    url = raw.get("url") or raw.get("serverUrl") or raw.get("endpoint")
    env = raw.get("env")
    if "env" in raw and not isinstance(env, dict):
        raise ValueError("env must be an object")
    env_keys = sorted(env) if isinstance(env, dict) else []

    declared = (raw.get("type") or raw.get("transport") or "").lower()
    transport: Transport
    if declared in ("stdio", "http", "sse"):
        transport = cast(Transport, declared)
    elif url and not command:
        transport = "sse" if "sse" in str(url).lower() else "http"
    elif command:
        transport = "stdio"
    else:
        transport = "unknown"

    return ServerSpec(
        transport=transport,
        command=command,
        args=args,
        url=url or None,
        env_keys=env_keys,
    )


def parse_mcp_servers_block(
    block: Any,
    *,
    source: SourceKind,
    location: str,
    scope: str,
    errors: list[str] | None = None,
) -> list[DiscoveredServer]:
    """Turn a ``mcpServers`` map into DiscoveredServer records."""
    if not isinstance(block, dict):
        return []
    base_dir = _config_base_dir(location)
    out: list[DiscoveredServer] = []
    for name, raw in block.items():
        try:
            if not isinstance(raw, dict):
                raise ValueError("server declaration must be an object")
            spec = infer_spec(raw, base_dir)
        except ValueError as exc:
            message = f"{location}: {name}: {exc}"
            if errors is None:
                raise ValueError(message) from exc
            errors.append(message)
            continue
        enabled = raw.get("enabled")
        out.append(
            DiscoveredServer(
                name=str(name),
                spec=spec,
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
