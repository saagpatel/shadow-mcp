"""Collector: Codex ``~/.codex/config.toml`` plus per-profile config TOMLs.

Codex stores servers as ``[mcp_servers.<name>]`` tables with ``command`` (or
``url``), ``args``, ``enabled``, and a nested ``[mcp_servers.<name>.env]`` table.
Profile config files (loaded only under a named profile) declare extra servers;
we surface them with scope=profile so the report can note they are not always on.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from ..models import DiscoveredServer, Provenance, ServerSpec, SourceKind, Transport
from ._common import ConfigCollector, read_config

SOURCE: SourceKind = "codex"


def _load_toml(path: Path) -> dict[str, Any] | None:
    raw = read_config(path)
    if raw is None:
        return None
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path}: invalid TOML ({type(exc).__name__})") from exc


def _spec_from_table(table: dict[str, Any]) -> ServerSpec:
    command = table.get("command")
    args_raw = table.get("args") or []
    args = [str(a) for a in args_raw] if isinstance(args_raw, list) else []
    url = table.get("url")
    env = table.get("env")
    env_keys = sorted(env.keys()) if isinstance(env, dict) else []
    transport: Transport = "stdio" if command else ("http" if url else "unknown")
    return ServerSpec(
        transport=transport,
        command=str(command) if command else None,
        args=args,
        url=str(url) if url else None,
        env_keys=env_keys,
    )


def _parse_file(path: Path, scope: str) -> list[DiscoveredServer]:
    data = _load_toml(path)
    if not data:
        return []
    servers = data.get("mcp_servers")
    if not isinstance(servers, dict):
        return []
    out: list[DiscoveredServer] = []
    for name, table in servers.items():
        if not isinstance(table, dict):
            continue
        enabled = table.get("enabled")
        out.append(
            DiscoveredServer(
                name=str(name),
                spec=_spec_from_table(table),
                provenance=Provenance(
                    source=SOURCE,
                    location=str(path),
                    scope=scope,
                    declared_name=str(name),
                    enabled=enabled if isinstance(enabled, bool) else None,
                ),
            )
        )
    return out


class CodexCollector(ConfigCollector):
    source = SOURCE

    def collect_with_errors(self, errors: list[str]) -> list[DiscoveredServer]:
        out: list[DiscoveredServer] = []
        for path in (self.paths.codex_config, *self.paths.codex_profile_configs):
            scope = "user" if path == self.paths.codex_config else "profile"
            try:
                out.extend(_parse_file(path, scope))
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
        return out
