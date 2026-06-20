"""shadow-mcp command line: discover -> inventory -> grade -> report.

    shadow-mcp scan                 full pipeline, rich terminal report
    shadow-mcp scan --json out.json write the machine-readable inventory
    shadow-mcp scan --format markdown
    shadow-mcp discover             inventory only, skip grading
    shadow-mcp sources              what each collector found, no grading

Discovery is read-only throughout.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

from .collectors import discover_all
from .config import DiscoveryPaths, GradingPaths
from .grading import grade_inventory
from .inventory import build_inventory
from .models import GradedServer, RiskAssessment
from .report import build_report, render_markdown, render_terminal


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _discovery_paths(args: argparse.Namespace) -> DiscoveryPaths:
    home = Path(args.home).expanduser() if args.home else None
    return DiscoveryPaths.default(home)


def _grading_paths(args: argparse.Namespace) -> GradingPaths:
    gp = GradingPaths.default()
    if args.registry_db:
        gp.mcptrust_registry_db = Path(args.registry_db).expanduser()
    return gp


def _run_pipeline(args: argparse.Namespace, *, grade: bool):
    paths = _discovery_paths(args)
    result = discover_all(
        paths,
        include_processes=not args.no_processes,
        include_cli=not args.no_cli,
    )
    inventory = build_inventory(result.servers)
    if grade:
        graded = grade_inventory(
            inventory,
            grading_paths=_grading_paths(args),
            run_mcpaudit=not args.no_mcpaudit,
        )
    else:
        graded = [
            GradedServer(
                entry=e,
                risk=RiskAssessment(band="unknown", headline="ungraded"),
            )
            for e in inventory
        ]
    report = build_report(
        graded,
        host=socket.gethostname(),
        generated_at=_now_iso(),
        source_counts=result.source_counts,
        errors=result.errors,
    )
    return report


def _emit(report, args: argparse.Namespace) -> None:
    if args.json:
        Path(args.json).write_text(
            json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
        print(f"wrote {args.json}", file=sys.stderr)
    fmt = args.format
    if fmt == "json" and not args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    elif fmt == "markdown":
        print(render_markdown(report))
    elif fmt == "terminal":
        render_terminal(report)


def cmd_scan(args: argparse.Namespace) -> int:
    report = _run_pipeline(args, grade=True)
    _emit(report, args)
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    report = _run_pipeline(args, grade=False)
    _emit(report, args)
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    paths = _discovery_paths(args)
    result = discover_all(
        paths,
        include_processes=not args.no_processes,
        include_cli=not args.no_cli,
    )
    for source, count in sorted(result.source_counts.items()):
        print(f"{source:18} {count}")
    if result.errors:
        print("\nerrors:")
        for e in result.errors:
            print(f"  {e}")
    return 0


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--home", help="override $HOME for discovery (testing)")
    p.add_argument("--no-processes", action="store_true", help="skip live process scan")
    p.add_argument("--no-cli", action="store_true", help="skip `claude mcp list`")
    p.add_argument("--json", metavar="PATH", help="write machine-readable inventory JSON")
    p.add_argument(
        "--format",
        choices=["terminal", "json", "markdown"],
        default="terminal",
        help="output format (default: terminal)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shadow-mcp",
        description="Discover and risk-grade the MCP servers present on this machine.",
    )
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="discover, grade, and report (default)")
    _add_common(p_scan)
    p_scan.add_argument("--no-mcpaudit", action="store_true", help="skip MCPAudit grading")
    p_scan.add_argument("--registry-db", help="path to mcp-trust registry.db")
    p_scan.set_defaults(func=cmd_scan)

    p_disc = sub.add_parser("discover", help="inventory only, no grading")
    _add_common(p_disc)
    p_disc.set_defaults(func=cmd_discover)

    p_src = sub.add_parser("sources", help="per-collector counts")
    _add_common(p_src)
    p_src.set_defaults(func=cmd_sources)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        # default to scan with terminal output
        args = parser.parse_args(["scan", *(argv or [])])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
