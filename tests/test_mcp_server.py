"""Tests for the shadow-mcp MCP server payload functions."""

from __future__ import annotations

import json
import subprocess
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


def test_default_payloads_do_not_run_claude_cli(fake_home, monkeypatch) -> None:
    args = mcp_server._default_args(fake_home)
    assert args.no_cli is True
    assert args.connect is False

    def fail_if_claude_mcp_list(command, *args, **kwargs):
        if command and command[0] == "claude":
            raise AssertionError("MCP payloads must not run claude mcp list")
        if command and command[0] == "ps":
            return subprocess.CompletedProcess(command, 0, stdout="101 1 ordinary-fixture", stderr="")
        raise AssertionError(f"unexpected subprocess command: {command}")

    monkeypatch.setattr(subprocess, "run", fail_if_claude_mcp_list)
    mcp_server.scan_local_payload(mcp_server._default_args(fake_home))
    mcp_server.discover_local_payload(mcp_server._default_args(fake_home))
    mcp_server.deep_scan_payload([], mcp_server._default_args(fake_home))
    mcp_server.list_sources_payload(mcp_server._default_args(fake_home))


def test_registered_deep_scan_describes_empty_selection():
    import asyncio

    from shadow_mcp.mcp_server import build_server

    tools = {tool.name: tool for tool in asyncio.run(build_server().list_tools())}
    description = str(tools["deep_scan"].description).lower()
    assert "all servers when the list is empty" in description
    assert "static" in description and "no spawning" in description


def test_registered_static_tools_grade_in_an_event_loop(fake_home, tmp_path, monkeypatch, capsys):
    import asyncio

    import pytest
    from mcp.shared.memory import create_connected_server_and_client_session

    api = pytest.importorskip("mcp_audit.api")
    args = _test_args(fake_home, tmp_path)
    args.no_mcpaudit = False
    args.no_compute = True
    monkeypatch.setattr(mcp_server, "_default_args", lambda: args)
    monkeypatch.setenv("SHADOW_MCP_MCPTRUST_DIR", str(tmp_path / "fixture-catalog"))
    scores = dict.fromkeys(
        ("file_access", "network_access", "shell_execution", "destructive", "exfiltration"), 2.0
    )
    scores["composite"] = 2.0

    def static_scan(config, *, redact):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError("static adapter requires a synchronous thread")
        assert len(config["mcpServers"]) == 1 and redact is False
        print("fixture-engine-output")
        return {"schema_version": 1, "audits": [{"risk_score": scores}]}

    monkeypatch.setattr(api, "scan_config_only_dict", static_scan)

    async def grades():
        reports = []
        async with create_connected_server_and_client_session(mcp_server.build_server()) as client:
            for tool, params in (("scan_local", {}), ("deep_scan", {"names": ["github"]})):
                result = await client.call_tool(tool, params)
                assert not result.isError
                reports.append(json.loads(result.content[0].text))
        return reports

    reports = asyncio.run(grades())
    assert [s["entry"]["canonical_name"] for s in reports[1]["servers"]] == ["github"]
    for report in reports:
        assert report["servers"]
        for server in report["servers"]:
            grade = server["risk"]["mcpaudit"]
            assert grade["error"] is None
            assert grade["composite"] == 2.0
            assert grade["connected"] is False
    print("caller-output")
    assert capsys.readouterr().out == "caller-output\n"


def test_registered_sources_surfaces_unreadable_extension_root(fake_home, tmp_path, monkeypatch):
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from shadow_mcp.config import DiscoveryPaths

    args = _test_args(fake_home, tmp_path)
    monkeypatch.setattr(mcp_server, "_default_args", lambda: args)
    root = DiscoveryPaths.default(fake_home).claude_extensions_dir
    real_iterdir = Path.iterdir

    def list_directory(path):
        if path == root:
            raise PermissionError("fixture denied")
        return real_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", list_directory)

    async def call():
        async with create_connected_server_and_client_session(mcp_server.build_server()) as client:
            return await client.call_tool("list_sources", {})

    result = asyncio.run(call())
    assert result.isError
    assert "dxt" in result.content[0].text and "fixture denied" in result.content[0].text
