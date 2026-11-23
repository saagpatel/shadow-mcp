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
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"{path}: invalid TOML ({type(exc).__name__})") from exc


def _spec_from_table(table: dict[str, Any]) -> ServerSpec:
    if not table:
        raise ValueError("empty server declaration")
    command = table.get("command")
    url = table.get("url")
    args_raw = table.get("args", [])
    env = table.get("env", {})
    if command is not None and not isinstance(command, str):
        raise ValueError("command must be a string")
    if url is not None and not isinstance(url, str):
        raise ValueError("url must be a string")
    if command is not None and not command.strip():
        raise ValueError("command must not be blank")
    if url is not None and not url.strip():
        raise ValueError("url must not be blank")
    if not command and not url:
        raise ValueError("server declaration requires a command or endpoint")
    if not isinstance(args_raw, list) or not all(isinstance(arg, str) for arg in args_raw):
        raise ValueError("args must be an array of strings")
    if not isinstance(env, dict):
        raise ValueError("env must be a table")
    env_keys = sorted(env)
    transport: Transport = "stdio" if command else "http"
    return ServerSpec(
        transport=transport,
        command=command or None,
        args=args_raw,
        url=url or None,
        env_keys=env_keys,
    )


def _parse_file(path: Path, scope: str, errors: list[str]) -> list[DiscoveredServer]:
    data = _load_toml(path)
    if data is None:
        if scope == "profile":
            errors.append(f"{path}: listed profile is missing")
        return []
    servers = data.get("mcp_servers")
    if servers is None:
        return []
    if not isinstance(servers, dict):
        raise ValueError(f"{path}: mcp_servers must be a table")
    out: list[DiscoveredServer] = []
    for name, table in servers.items():
        try:
            if not isinstance(table, dict):
                raise ValueError("server declaration must be a table")
            enabled = table.get("enabled")
            if "enabled" in table and not isinstance(enabled, bool):
                raise ValueError("enabled must be a boolean")
            spec = _spec_from_table(table)
        except ValueError as exc:
            errors.append(f"{path}: {name}: {exc}")
            continue
        out.append(
            DiscoveredServer(
                name=str(name),
                spec=spec,
                provenance=Provenance(
                    source=SOURCE,
                    location=str(path),
                    scope=scope,
                    declared_name=str(name),
                    enabled=enabled,
                ),
            )
        )
    return out


class CodexCollector(ConfigCollector):
    source = SOURCE

    def collect_with_errors(self, errors: list[str]) -> list[DiscoveredServer]:
        errors.extend(self.paths.codex_profile_errors)
        out: list[DiscoveredServer] = []
        for path in (self.paths.codex_config, *self.paths.codex_profile_configs):
            scope = "user" if path == self.paths.codex_config else "profile"
            try:
                out.extend(_parse_file(path, scope, errors))
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
        return out
