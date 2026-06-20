"""Shared fixtures: a synthetic $HOME tree mirroring this machine's real layout."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shadow_mcp.config import DiscoveryPaths


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def fake_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()

    # Claude Code: a secret-bearing stdio server + a remote http server + empty project scope
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "personal-ops": {
                    "command": str(home / ".claude/bin/personal-ops-mcp"),
                    "env": {"PERSONAL_OPS_CLIENT_ID": "s3cr3t-sentinel-DO-NOT-LEAK"},
                },
                "context7": {"url": "https://mcp.context7.com/mcp", "type": "http"},
            },
            "projects": {str(home / "Projects/x"): {"mcpServers": {}}},
        },
    )

    # Codex: same personal-ops under a different name shape + a disabled server
    codex = home / ".codex"
    codex.mkdir(parents=True, exist_ok=True)
    (codex / "config.toml").write_text(
        "\n".join(
            [
                "[mcp_servers.personal_ops]",
                f'command = "{home / ".codex/bin/personal-ops-mcp"}"',
                "",
                "[mcp_servers.github]",
                'command = "github-mcp"',
                'args = ["--read-only"]',
                "",
                "[mcp_servers.serena]",
                "enabled = false",
                'command = "serena"',
                'args = ["start-mcp-server"]',
            ]
        ),
        encoding="utf-8",
    )

    # Claude Desktop: bridge-db
    _write_json(
        home / "Library/Application Support/Claude/claude_desktop_config.json",
        {
            "mcpServers": {
                "bridge-db": {
                    "command": "uv",
                    "args": ["run", "--directory", "/x", "python", "-m", "bridge_db"],
                    "env": {"BRIDGE_DB_PRINCIPAL_TOKEN": "s3cr3t-sentinel-DO-NOT-LEAK"},
                }
            }
        },
    )

    # DXT extension manifest
    _write_json(
        home
        / "Library/Application Support/Claude/Claude Extensions/anthropic.filesystem/manifest.json",
        {
            "name": "filesystem",
            "server": {"type": "node", "mcp_config": {"command": "node", "args": ["fs.js"]}},
        },
    )

    # Project .mcp.json (real) + an adversarial poisoned fixture
    _write_json(
        home / "Projects/reliquary/.mcp.json",
        {"mcpServers": {"reliquary": {"command": "uv", "args": ["run", "-m", "reliquary.server"]}}},
    )
    _write_json(
        home / "Projects/evals/fixtures/adv-poisoned-mcp-description/.mcp.json",
        {"mcpServers": {"fake-docs-helper": {"command": "node", "args": ["./fake-mcp-server.js"]}}},
    )

    return home


@pytest.fixture
def fake_paths(fake_home: Path) -> DiscoveryPaths:
    return DiscoveryPaths.default(fake_home)
