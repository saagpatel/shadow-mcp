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


def _run_pipeline(args: argparse.Namespace, *, grade: bool, only: list[str] | None = None):
    paths = _discovery_paths(args)
    result = discover_all(
        paths,
        include_processes=not args.no_processes,
        include_cli=not args.no_cli,
    )
    inventory = build_inventory(result.servers)
    if only:
        wanted = {n.lower() for n in only}
        inventory = [
            e
            for e in inventory
            if e.canonical_name.lower() in wanted or any(a.lower() in wanted for a in e.aliases)
        ]
    if grade:
        connect = getattr(args, "connect", False)
        if connect:
            print(
                "warning: --connect spawns each stdio MCP server to enumerate its "
                "tools. Servers needing real secrets will fail to start and fall "
                "back to their static grade.",
                file=sys.stderr,
            )
        graded = grade_inventory(
            inventory,
            grading_paths=_grading_paths(args),
            run_mcpaudit=not getattr(args, "no_mcpaudit", False),
            compute_missing=not getattr(args, "no_compute", False),
            connect=connect,
            connect_timeout=getattr(args, "connect_timeout", 8),
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


def cmd_deep_scan(args: argparse.Namespace) -> int:
    """Connect to (spawn) the named servers (or all), enumerate tools, grade."""
    args.connect = True
    report = _run_pipeline(args, grade=True, only=args.names or None)
    _emit(report, args)
    return 0


def cmd_grade_missing(args: argparse.Namespace) -> int:
    """Show servers the mcp-trust registry had no grade for, with a computed letter."""
    report = _run_pipeline(args, grade=True)
    computed = [g for g in report.servers if g.risk.mcptrust and g.risk.mcptrust.computed]
    in_registry = [
        g
        for g in report.servers
        if g.risk.mcptrust
        and g.risk.mcptrust.grade not in ("unknown",)
        and not g.risk.mcptrust.computed
    ]
    if args.format == "json":
        payload = {
            "computed": [g.model_dump(mode="json") for g in computed],
            "in_registry": [g.entry.canonical_name for g in in_registry],
        }
        print(json.dumps(payload, indent=2))
        return 0
    print(
        f"{len(in_registry)} server(s) graded by the mcp-trust registry; "
        f"{len(computed)} computed from MCPAudit dimensions via mcp-trust grade():\n"
    )
    for g in sorted(computed, key=lambda g: g.risk.mcptrust.grade):
        e = g.entry
        print(f"  {g.risk.mcptrust.grade}  {e.canonical_name:28} ({','.join(e.sources)})")
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
    p_scan.add_argument(
        "--no-compute",
        action="store_true",
        help="don't compute a grade for servers the registry hasn't scanned",
    )
    p_scan.add_argument(
        "--connect",
        action="store_true",
        help="spawn each stdio server to grade its real tools (opt-in; executes servers)",
    )
    p_scan.add_argument(
        "--connect-timeout", type=int, default=8, help="per-server connect timeout (s)"
    )
    p_scan.set_defaults(func=cmd_scan)

    p_disc = sub.add_parser("discover", help="inventory only, no grading")
    _add_common(p_disc)
    p_disc.set_defaults(func=cmd_discover)

    p_deep = sub.add_parser(
        "deep-scan",
        help="connect to (spawn) named servers (or all), enumerate tools, grade",
    )
    _add_common(p_deep)
    p_deep.add_argument("names", nargs="*", help="server names to connect to (default: all stdio)")
    p_deep.add_argument("--no-mcpaudit", action="store_true", help="skip MCPAudit grading")
    p_deep.add_argument("--no-compute", action="store_true", help="skip computed grade fill")
    p_deep.add_argument("--registry-db", help="path to mcp-trust registry.db")
    p_deep.add_argument(
        "--connect-timeout", type=int, default=10, help="per-server connect timeout (s)"
    )
    p_deep.set_defaults(func=cmd_deep_scan)

    p_grade = sub.add_parser(
        "grade-missing",
        help="grade servers the mcp-trust registry has no scan for, via mcp-trust grade()",
    )
    _add_common(p_grade)
    p_grade.add_argument("--no-mcpaudit", action="store_true", help="skip MCPAudit grading")
    p_grade.add_argument("--registry-db", help="path to mcp-trust registry.db")
    p_grade.set_defaults(func=cmd_grade_missing)

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
