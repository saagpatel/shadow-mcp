"""Filesystem locations shadow-mcp reads from.

Every path is overridable (env var or CLI) so the tool can run against
fixtures or a non-default ``$HOME`` in tests. Defaults target a standard
macOS developer machine.
"""

from __future__ import annotations

import os
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path


def _installed_mcptrust_seed() -> Path | None:
    """Locate ``seed_servers.json`` inside an installed mcp-trust package.

    The seed catalog ships in the mcp-trust wheel, so resolving it from the
    installed package works on any machine — unlike a source-checkout path,
    which only exists on a development box. Returns None when mcp-trust is not
    installed or the resource is not a plain file (e.g. a zipped install);
    callers fall back to the source-checkout layout.
    """
    try:
        from importlib.resources import files

        res = files("mcp_trust") / "catalog" / "seed_servers.json"
    except (ImportError, ModuleNotFoundError):
        return None
    with suppress(OSError, TypeError, ValueError):
        p = Path(str(res))
        if p.is_file():
            return p
    return None


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
    def default(cls, home: Path | None = None) -> DiscoveryPaths:
        h = home or Path(os.environ.get("SHADOW_MCP_HOME", Path.home()))
        codex = h / ".codex"
        app_support = h / "Library" / "Application Support" / "Claude"
        return cls(
            home=h,
            claude_json=h / ".claude.json",
            claude_desktop_config=app_support / "claude_desktop_config.json",
            claude_extensions_dir=app_support / "Claude Extensions",
            codex_config=codex / "config.toml",
            # Any per-profile Codex config, not a hardcoded machine-specific
            # list. "*.config.toml" cannot match the main "config.toml".
            codex_profile_configs=sorted(codex.glob("*.config.toml")),
            projects_root=h / "Projects",
        )


@dataclass
class GradingPaths:
    mcptrust_registry_db: Path
    mcptrust_seed: Path

    @classmethod
    def default(cls, home: Path | None = None) -> GradingPaths:
        h = home or Path.home()
        trust_env = os.environ.get("SHADOW_MCP_MCPTRUST_DIR")
        trust = Path(trust_env) if trust_env else h / "Projects" / "mcp-trust"
        checkout_seed = trust / "src" / "mcp_trust" / "catalog" / "seed_servers.json"
        # Precedence: explicit SHADOW_MCP_MCPTRUST_DIR wins; otherwise prefer
        # the seed bundled with the installed mcp-trust package (portable to
        # any machine) and fall back to the source-checkout layout.
        seed = checkout_seed if trust_env else (_installed_mcptrust_seed() or checkout_seed)
        return cls(
            mcptrust_registry_db=Path(
                os.environ.get("SHADOW_MCP_MCPTRUST_DB", trust / "registry.db")
            ),
            mcptrust_seed=seed,
        )
