"""Tests for the shadow-mcp MCP server payload functions."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

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
            return subprocess.CompletedProcess(command, 0, stdout="101 1 /bin/sleep 60", stderr="")
        raise AssertionError(f"unexpected subprocess command: {command}")

    monkeypatch.setattr(subprocess, "run", fail_if_claude_mcp_list)
    mcp_server.scan_local_payload(mcp_server._default_args(fake_home))
    mcp_server.discover_local_payload(mcp_server._default_args(fake_home))
    mcp_server.deep_scan_payload([], mcp_server._default_args(fake_home))
    mcp_server.list_sources_payload(mcp_server._default_args(fake_home))


def test_list_sources_rejects_incomplete_counts(fake_home, tmp_path, monkeypatch):
    (fake_home / ".claude.json").write_text(
        '{"mcpServers":{"ok":{"command":"x"},"bad":{"type":7}}}'
    )
    args = _test_args(fake_home, tmp_path)
    monkeypatch.setattr(mcp_server, "_default_args", lambda: args)

    result = _call_registered_list_sources()
    assert result.isError
    assert "claude_code" in result.content[0].text and "bad" in result.content[0].text


@pytest.mark.parametrize(
    ("relative_path", "source", "contents", "malformed"),
    [
        (".claude.json", "claude_code", '{"mcpServers": []}', True),
        (
            "Library/Application Support/Claude/Claude Extensions/malformed/manifest.json",
            "dxt",
            '{"name":"malformed","server":7}',
            True,
        ),
        (".claude.json", "claude_code", "{}", False),
        (
            "Library/Application Support/Claude/Claude Extensions/missing/manifest.json",
            "dxt",
            '{"name":"missing"}',
            False,
        ),
    ],
)
def test_registered_list_sources_rejects_malformed_declaration_containers(
    fake_home, tmp_path, monkeypatch, relative_path, source, contents, malformed
):
    config_path = fake_home / relative_path
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(contents)

    args = _test_args(fake_home, tmp_path)
    monkeypatch.setattr(mcp_server, "_default_args", lambda: args)

    result = _call_registered_list_sources()
    assert result.isError is malformed
    if malformed:
        message = result.content[0].text
        assert source in message
        assert str(config_path) in message


def _call_registered_list_sources():
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    async def call():
        async with create_connected_server_and_client_session(mcp_server.build_server()) as client:
            return await client.call_tool("list_sources", {})

    return asyncio.run(call())


def test_registered_deep_scan_describes_empty_names():
    import asyncio

    tools = asyncio.run(mcp_server.build_server().list_tools())
    tool = next(tool for tool in tools if tool.name == "deep_scan")
    assert "all servers when the list is empty" in tool.description
