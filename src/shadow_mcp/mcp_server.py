"""Expose shadow-mcp as a read-only MCP server (stdio).

Inventories and risk-grades the MCP servers configured on this machine.
Never connects to or spawns any MCP server — grading is static (config-based).

Launched as ``shadow-mcp mcp-serve`` (or ``uvx shadow-mcp mcp-serve``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse

from .cli import _discovery_paths, _run_pipeline, build_parser
from .collectors import discover_all


def _default_args(home: Path | str | None = None) -> argparse.Namespace:
    """Build a default 'scan' Namespace with connect=False forced.

    Args:
        home: Override $HOME for discovery (used in tests with a fixture tree).
    """
    args = build_parser().parse_args(["scan"])
    args.connect = False  # CRITICAL: never spawn/connect to any local server
    if home is not None:
        args.home = str(home)
    return args


def scan_local_payload(_args: argparse.Namespace | None = None) -> str:
    """Full pipeline (discover -> inventory -> grade -> report). Returns report JSON."""
    args = _args if _args is not None else _default_args()
    report = _run_pipeline(args, grade=True)
    return json.dumps(report.model_dump(mode="json"), indent=2)


def discover_local_payload(_args: argparse.Namespace | None = None) -> str:
    """Inventory every MCP server without grading. Returns report JSON."""
    args = _args if _args is not None else _default_args()
    report = _run_pipeline(args, grade=False)
    return json.dumps(report.model_dump(mode="json"), indent=2)


def deep_scan_payload(
    names: list[str],
    _args: argparse.Namespace | None = None,
) -> str:
    """Grade only the named servers (static, no server spawning). Returns report JSON."""
    args = _args if _args is not None else _default_args()
    report = _run_pipeline(args, grade=True, only=names or None)
    return json.dumps(report.model_dump(mode="json"), indent=2)


def list_sources_payload(_args: argparse.Namespace | None = None) -> str:
    """Per-collector source counts from a discover run. Returns JSON dict."""
    args = _args if _args is not None else _default_args()
    paths = _discovery_paths(args)
    result = discover_all(
        paths,
        include_processes=not args.no_processes,
        include_cli=not args.no_cli,
    )
    return json.dumps(result.source_counts, indent=2)


def build_server() -> Any:
    """Build the FastMCP server with shadow-mcp tools registered."""
    from mcp.server import FastMCP

    app: Any = FastMCP(
        name="shadow-mcp",
        instructions=(
            "Inventory and risk-grade MCP servers configured on this machine. "
            "LOCAL only — reads configs, never connects to or spawns any MCP server."
        ),
    )

    @app.tool()  # type: ignore[misc]
    def scan_local() -> str:
        """Run the full pipeline: discover, inventory, grade, and report. Returns JSON."""
        return scan_local_payload()

    @app.tool()  # type: ignore[misc]
    def discover_local() -> str:
        """Inventory every MCP server on this machine without grading. Returns JSON."""
        return discover_local_payload()

    @app.tool()  # type: ignore[misc]
    def deep_scan(names: list[str]) -> str:
        """Grade only the named servers (static, no spawning). Returns JSON."""
        return deep_scan_payload(names)

    @app.tool()  # type: ignore[misc]
    def list_sources() -> str:
        """Show per-collector source counts from a discover run. Returns JSON."""
        return list_sources_payload()

    return app


def run() -> None:
    """Run the MCP server on stdio."""
    import asyncio
    import sys

    app = build_server()
    sys.stderr.write("shadow-mcp MCP server starting on stdio...\n")
    asyncio.run(app.run_stdio_async())
