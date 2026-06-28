"""Tests for the shadow-mcp MCP server payload functions."""

from __future__ import annotations

import json
from pathlib import Path

from shadow_mcp import mcp_server
from shadow_mcp.cli import build_parser


def _test_args(fake_home: Path, tmp_path: Path):
    """Build a minimal args Namespace pointing at the fixture tree."""
    args = build_parser().parse_args(
        [
            "scan",
            "--home",
            str(fake_home),
            "--no-processes",
            "--no-cli",
            "--no-mcpaudit",
            "--registry-db",
            str(tmp_path / "absent.db"),
        ]
    )
    args.connect = False
    return args


def test_scan_local_returns_valid_json(fake_home, tmp_path) -> None:
    args = _test_args(fake_home, tmp_path)
    payload = json.loads(mcp_server.scan_local_payload(_args=args))
    assert "servers" in payload
    assert "host" in payload
    assert "generated_at" in payload
    assert "source_summary" in payload
    assert isinstance(payload["servers"], list)


def test_scan_local_server_entries_have_expected_keys(fake_home, tmp_path) -> None:
    args = _test_args(fake_home, tmp_path)
    payload = json.loads(mcp_server.scan_local_payload(_args=args))
    assert len(payload["servers"]) >= 1
    sample = payload["servers"][0]
    assert "entry" in sample
    assert "risk" in sample
    assert "canonical_name" in sample["entry"]


def test_discover_local_returns_valid_json(fake_home, tmp_path) -> None:
    args = _test_args(fake_home, tmp_path)
    payload = json.loads(mcp_server.discover_local_payload(_args=args))
    assert "servers" in payload
    assert "host" in payload
    # discover skips grading — all servers should be ungraded
    assert all(s["risk"]["headline"] == "ungraded" for s in payload["servers"])


def test_deep_scan_empty_names_returns_valid_json(fake_home, tmp_path) -> None:
    args = _test_args(fake_home, tmp_path)
    payload = json.loads(mcp_server.deep_scan_payload([], _args=args))
    assert "servers" in payload
    assert isinstance(payload["servers"], list)


def test_deep_scan_named_filters_to_server(fake_home, tmp_path) -> None:
    args = _test_args(fake_home, tmp_path)
    payload = json.loads(mcp_server.deep_scan_payload(["github"], _args=args))
    names = {s["entry"]["canonical_name"] for s in payload["servers"]}
    assert names == {"github"}


def test_list_sources_returns_source_dict(fake_home, tmp_path) -> None:
    args = _test_args(fake_home, tmp_path)
    payload = json.loads(mcp_server.list_sources_payload(_args=args))
    assert isinstance(payload, dict)
    # The fixture has codex + claude_code + claude_desktop + dxt + project_mcp_json sources
    assert "codex" in payload
    assert "claude_code" in payload


def test_build_server_name() -> None:
    app = mcp_server.build_server()
    assert app is not None
    assert app.name == "shadow-mcp"
