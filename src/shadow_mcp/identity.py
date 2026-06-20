"""Server identity: how shadow-mcp decides two sightings are the same server.

The hard part of discovery is that one logical server appears under different
names and command shapes across hosts:

    ~/.claude.json   personal-ops -> /Users/dev/.claude/bin/personal-ops-mcp
    ~/.codex          personal_ops -> /Users/dev/.codex/bin/personal-ops-mcp
    a running process              -> node .../mcp-server.js (no clean name)

We derive a stable *signature* from the command/url and a *normalized name*,
then the inventory layer unions sightings that share either one.
"""

from __future__ import annotations

import os

from .models import ServerSpec

# Tools that *run a package* — the meaningful identity is the package, not the runner.
PACKAGE_RUNNERS = {"npx", "bunx", "uvx", "pnpm", "yarn", "dlx"}
# Interpreters/launchers — identity is the module (-m) or the script.
LAUNCHERS = {"python", "python3", "uv", "uvx", "poetry", "pipx", "node", "bun", "deno"}
# Shell shims to see through to the real first argument.
SHIMS = {"sh", "bash", "zsh", "env", "exec"}


def normalize_name(name: str) -> str:
    """Fold name variants together: 'personal_ops' / 'Personal-Ops' -> 'personal-ops'."""
    return name.strip().lower().replace("_", "-").replace(" ", "-")


# Suffixes a resolved binary/process name carries that its config name omits,
# e.g. the running `github-mcp-server` is the configured `github`.
_RELAX_SUFFIXES = ("-mcp-server", "-mcp-srv", "-mcp", "-server")


def relaxed_name(name: str) -> str:
    """Strip trailing -mcp/-server decorations so a process can match its config twin."""
    n = normalize_name(name)
    changed = True
    while changed:
        changed = False
        for suf in _RELAX_SUFFIXES:
            if n.endswith(suf) and len(n) > len(suf):
                n = n[: -len(suf)]
                changed = True
    return n


def normalize_url(url: str) -> str:
    """Strip scheme + trailing slash, lowercase host/path for stable comparison."""
    u = url.strip().lower()
    for scheme in ("https://", "http://", "sse://", "ws://", "wss://"):
        if u.startswith(scheme):
            u = u[len(scheme) :]
            break
    return u.rstrip("/")


def _strip_version(pkg: str) -> str:
    """'@scope/pkg@1.2.3' -> '@scope/pkg'; 'pkg@latest' -> 'pkg'."""
    if pkg.startswith("@"):
        # scoped: keep the leading @, only split a version after the package name
        at = pkg.find("@", 1)
        return pkg[:at] if at != -1 else pkg
    return pkg.split("@", 1)[0]


def _first_non_flag(args: list[str]) -> str | None:
    for a in args:
        if a and not a.startswith("-"):
            return a
    return None


def _first_package(args: list[str]) -> str | None:
    skip = {"exec", "dlx", "run", "tool"}
    for a in args:
        if not a or a.startswith("-"):
            continue
        if a in skip:
            continue
        return _strip_version(a)
    return None


def _module_after_m(args: list[str]) -> str | None:
    for i, a in enumerate(args):
        if a == "-m" and i + 1 < len(args):
            return args[i + 1]
    return None


def stdio_reference(spec: ServerSpec) -> str:
    """Reduce a stdio command+args to its stable identity token."""
    cmd = (spec.command or "").strip()
    base = os.path.basename(cmd).lower()
    args = list(spec.args)

    # See through a shell shim: `sh -c "real ..."` or `env FOO=bar real ...`
    if base in SHIMS:
        nxt = _first_non_flag([a for a in args if "=" not in a])
        if nxt:
            base = os.path.basename(nxt).lower()
            args = args[args.index(nxt) + 1 :] if nxt in args else args

    if base in PACKAGE_RUNNERS:
        pkg = _first_package(args)
        if pkg:
            return (
                os.path.basename(pkg).lower()
                if "/" in pkg and not pkg.startswith("@")
                else pkg.lower()
            )

    if base in LAUNCHERS:
        mod = _module_after_m(args)
        if mod:
            return mod.lower()
        script = _first_non_flag([a for a in args if a not in PACKAGE_RUNNERS])
        if script:
            return os.path.basename(script).lower()

    if base:
        return base
    script = _first_non_flag(args)
    return os.path.basename(script).lower() if script else "unknown"


def signature(spec: ServerSpec) -> str:
    """A stable cross-source key for one server."""
    if spec.url:
        return "url:" + normalize_url(spec.url)
    return "cmd:" + stdio_reference(spec)
