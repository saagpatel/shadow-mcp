"""Tests for the shadow-mcp MCP server payload functions."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from shadow_mcp import mcp_server
from shadow_mcp.cli import build_parser
from shadow_mcp.collectors import claude_cli, discover_all, processes
from shadow_mcp.collectors.base import default_collectors
from shadow_mcp.config import DiscoveryPaths


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


_CODEX = ".codex/config.toml"
_PROJECT = "Projects/.mcp.json"
_DESKTOP = "Library/Application Support/Claude"
_EXTENSIONS = f"{_DESKTOP}/Claude Extensions"
_VISIBLE = {"command": "x"}
_SERVER_MAP = {"mcpServers": {"visible": _VISIBLE}}
_BAD_FLAG = {"mcpServers": {"bad": {"command": "y", "enabled": "false"}, "visible": _VISIBLE}}
_CODEX_CONFIG = '[mcp_servers.visible]\ncommand = "x"'
_MANIFEST = {"server": {"mcp_config": _VISIBLE}}


# Files, simulated OS failure (operation, path), diagnostic, and surviving names.
_SOURCE_CASES = [
    (
        "claude_code",
        {
            ".claude.json": {
                "mcpServers": {
                    "missing_target": {"type": "stdio", "args": []},
                    "visible": _VISIBLE,
                    "remote": {"serverUrl": "https://example.invalid/mcp"},
                }
            }
        },
        None,
        "missing_target",
        ["remote", "visible"],
    ),
    (
        "codex",
        {_CODEX: _CODEX_CONFIG + "\n[mcp_servers.missing_target]\nargs = []"},
        None,
        "missing_target",
        ["visible"],
    ),
    (
        "dxt",
        {
            f"{_EXTENSIONS}/visible/manifest.json": _MANIFEST,
            f"{_EXTENSIONS}/missing_target/manifest.json": {
                "server": {"type": "node", "mcp_config": {}}
            },
        },
        None,
        "missing_target",
        ["visible"],
    ),
    (
        "claude_code",
        {".claude.json": {**_SERVER_MAP, "projects": []}},
        None,
        "projects",
        ["visible"],
    ),
    (
        "claude_code",
        {
            ".claude.json": {
                **_SERVER_MAP,
                "projects": {"bad-project": [], "good": {"mcpServers": {"other": _VISIBLE}}},
            }
        },
        None,
        "bad-project",
        ["other", "visible"],
    ),
    (
        "claude_desktop",
        {f"{_DESKTOP}/claude_desktop_config.json": _BAD_FLAG},
        None,
        "enabled",
        ["visible"],
    ),
    ("project_mcp_json", {_PROJECT: _BAD_FLAG}, None, "enabled", ["visible"]),
    (
        "claude_code",
        {".claude.json": {"mcpServers": {"empty": {}, "visible": _VISIBLE}}},
        None,
        "empty",
        ["visible"],
    ),
    (
        "codex",
        {_CODEX: _CODEX_CONFIG + "\n[mcp_servers.empty]"},
        None,
        "empty",
        ["visible"],
    ),
    ("codex", {_CODEX: _CODEX_CONFIG}, ("list", ".codex"), ".codex", ["visible"]),
    (
        "codex",
        {
            _CODEX: _CODEX_CONFIG,
            ".codex/one.config.toml": '[mcp_servers.profile]\ncommand = "y"',
            ".codex/bad.config.toml": "[",
        },
        None,
        "bad.config.toml",
        ["profile", "visible"],
    ),
    (
        "codex",
        {_CODEX: _CODEX_CONFIG, ".codex/lost.config.toml": ""},
        ("open", ".codex/lost.config.toml"),
        "lost.config.toml",
        ["visible"],
    ),
    (
        "dxt",
        {
            f"{_EXTENSIONS}/visible/manifest.json": _MANIFEST,
            f"{_EXTENSIONS}/denied/manifest.json": _MANIFEST,
        },
        ("stat", f"{_EXTENSIONS}/denied"),
        f"{_EXTENSIONS}/denied",
        ["visible"],
    ),
    (
        "dxt",
        {
            f"{_EXTENSIONS}/visible/manifest.json": _MANIFEST,
            f"{_EXTENSIONS}/bad/manifest.json": {**_MANIFEST, "name": []},
        },
        None,
        "name",
        ["visible"],
    ),
    (
        "project_mcp_json",
        {_PROJECT: _SERVER_MAP, "Projects/lost/.mcp.json": {}},
        ("open", "Projects/lost/.mcp.json"),
        "lost/.mcp.json",
        ["visible"],
    ),
    ("claude_cli", {}, None, "row", ["visible"]),
    ("process", {}, None, "row", ["visible-mcp"]),
]


def _inject_file_error(monkeypatch, operation, target):
    def fail_at_target(original):
        def wrapped(path, *args, **kwargs):
            if path == target or path == str(target):
                if operation == "open":
                    raise FileNotFoundError
                raise PermissionError("denied")
            return original(path, *args, **kwargs)

        return wrapped

    # pathlib uses scandir or listdir depending on the Python version.
    owner, methods = (os, ["scandir", "listdir"]) if operation == "list" else (Path, [operation])
    for method in methods:
        monkeypatch.setattr(owner, method, fail_at_target(getattr(owner, method)))


@pytest.mark.parametrize(("source", "files", "fault", "diagnostic", "expected"), _SOURCE_CASES)
def test_incomplete_source_keeps_valid_siblings(
    tmp_path, monkeypatch, source, files, fault, diagnostic, expected
):
    for location, document in files.items():
        path = tmp_path / location
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document if isinstance(document, str) else json.dumps(document))
    if fault:
        operation, location = fault
        _inject_file_error(monkeypatch, operation, tmp_path / location)

    monkeypatch.setattr(claude_cli, "_default_runner", lambda: (0, "bad:\nvisible: x"))
    monkeypatch.setattr(
        processes, "_default_runner", lambda: (0, "bad row\n101 1 /bin/visible-mcp --mcp-server")
    )
    args = _test_args(tmp_path, tmp_path)
    args.no_cli = source != "claude_cli"
    args.no_processes = source != "process"
    monkeypatch.setattr(mcp_server, "_default_args", lambda: args)

    paths = DiscoveryPaths.default(tmp_path)
    assert {c.source for c in default_collectors(paths)} == {case[0] for case in _SOURCE_CASES}
    response = _call_registered_list_sources()
    assert response.isError
    message = response.content[0].text
    assert f"{source}:" in message and diagnostic in message

    discovery = discover_all(
        paths, include_cli=not args.no_cli, include_processes=not args.no_processes
    )
    assert discovery.source_counts[source] == len(expected)
    assert sorted(s.name for s in discovery.servers if s.provenance.source == source) == expected
