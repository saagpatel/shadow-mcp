"""Filesystem locations shadow-mcp reads from.

Every path is overridable (env var or CLI) so the tool can run against
fixtures or a non-default ``$HOME`` in tests. Defaults target a standard
macOS developer machine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiscoveryPaths:
    home: Path
    claude_json: Path
    claude_desktop_config: Path
    claude_extensions_dir: Path
    codex_config: Path
    codex_profile_configs: list[Path] = field(default_factory=list)
    projects_root: Path | None = None
    project_glob_depth: int = 4  # cap recursion when hunting .mcp.json

    @classmethod
    def default(cls, home: Path | None = None) -> "DiscoveryPaths":
        h = home or Path(os.environ.get("SHADOW_MCP_HOME", Path.home()))
        codex = h / ".codex"
        app_support = h / "Library" / "Application Support" / "Claude"
        return cls(
            home=h,
            claude_json=h / ".claude.json",
            claude_desktop_config=app_support / "claude_desktop_config.json",
            claude_extensions_dir=app_support / "Claude Extensions",
            codex_config=codex / "config.toml",
            codex_profile_configs=[
                codex / "docs_curation_mcp.config.toml",
                codex / "web_research_mcp.config.toml",
            ],
            projects_root=h / "Projects",
        )


@dataclass
class GradingPaths:
    mcptrust_registry_db: Path
    mcptrust_seed: Path

    @classmethod
    def default(cls, home: Path | None = None) -> "GradingPaths":
        h = home or Path.home()
        trust = Path(os.environ.get("SHADOW_MCP_MCPTRUST_DIR", h / "Projects" / "mcp-trust"))
        return cls(
            mcptrust_registry_db=Path(
                os.environ.get("SHADOW_MCP_MCPTRUST_DB", trust / "registry.db")
            ),
            mcptrust_seed=trust / "src" / "mcp_trust" / "catalog" / "seed_servers.json",
        )
