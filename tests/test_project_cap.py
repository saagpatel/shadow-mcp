import os
from pathlib import Path

import pytest

from shadow_mcp.collectors import discover_all
from shadow_mcp.collectors.project_mcp import ProjectMcpJsonCollector
from shadow_mcp.config import DiscoveryPaths


@pytest.mark.parametrize("manifests", [200, 201])
def test_project_cap_reports_unvisited_directories(tmp_path, manifests):
    paths = DiscoveryPaths.default(tmp_path)
    for i in range(manifests):
        directory = paths.projects_root / str(i)
        directory.mkdir(parents=True)
        (directory / ".mcp.json").write_text('{"mcpServers":{"x":{"command":"x"}}}')
    result = discover_all(paths, collectors=[ProjectMcpJsonCollector(paths)])
    assert result.source_counts == {"project_mcp_json": 200}
    if manifests > 200:
        assert any("project_mcp_json" in err and "200" in err for err in result.errors), (
            result.errors
        )
    else:
        assert result.errors == []


def test_project_walk_reports_denied_directory_and_keeps_readable_sibling(tmp_path, monkeypatch):
    paths = DiscoveryPaths.default(tmp_path)
    denied = paths.projects_root / "denied"
    readable = paths.projects_root / "readable"
    denied.mkdir(parents=True)
    readable.mkdir()
    (readable / ".mcp.json").write_text('{"mcpServers":{"visible":{"command":"x"}}}')
    scandir = os.scandir

    def list_directory(path):
        if path == denied:
            raise PermissionError("permission denied")
        return scandir(path)

    monkeypatch.setattr(os, "scandir", list_directory)
    result = discover_all(paths, collectors=[ProjectMcpJsonCollector(paths)])
    assert [server.name for server in result.servers] == ["visible"]
    assert result.source_counts == {"project_mcp_json": 1}
    assert any("project_mcp_json" in err and str(denied) in err for err in result.errors)


def test_project_walk_skips_excluded_names_before_stat(tmp_path, monkeypatch):
    paths = DiscoveryPaths.default(tmp_path)
    excluded = paths.projects_root / "node_modules"
    excluded.mkdir(parents=True)
    for directory in (
        paths.projects_root,
        paths.projects_root / ".cursor",
        paths.projects_root / ".vscode",
    ):
        directory.mkdir(exist_ok=True)
        (directory / ".mcp.json").write_text('{"mcpServers":{"visible":{"command":"x"}}}')
    excluded_calls = []
    stat = Path.stat

    def deny_excluded(path, *args, **kwargs):
        if path == excluded:
            excluded_calls.append(path)
            raise PermissionError("permission denied")
        return stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", deny_excluded)
    result = discover_all(paths, collectors=[ProjectMcpJsonCollector(paths)])
    assert result.errors == []
    assert result.source_counts == {"project_mcp_json": 3}
    assert excluded_calls == []


def test_final_directory_with_two_manifests_respects_cap(tmp_path, monkeypatch):
    monkeypatch.setattr("shadow_mcp.collectors.project_mcp._MAX_FILES", 1)
    paths = DiscoveryPaths.default(tmp_path)
    paths.projects_root.mkdir(parents=True)
    for name in [".mcp.json", "mcp.json"]:
        (paths.projects_root / name).write_text('{"mcpServers":{"entry":{"command":"x"}}}')
    result = discover_all(paths, collectors=[ProjectMcpJsonCollector(paths)])
    assert len(result.servers) == 1
    assert result.source_counts == {"project_mcp_json": 1}
    assert any("limit" in err for err in result.errors)


def test_mid_listing_error_retains_manifest(tmp_path, monkeypatch):
    paths = DiscoveryPaths.default(tmp_path)
    root = paths.projects_root
    root.mkdir(parents=True)
    (root / ".mcp.json").write_text('{"mcpServers":{"visible":{"command":"x"}}}')
    scandir = os.scandir

    class InterruptedListing:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, value, traceback):
            return None

        def __iter__(self):
            with scandir(root) as entries:
                yield next(entries)
            raise OSError("listing interrupted")

    monkeypatch.setattr(
        os, "scandir", lambda path: InterruptedListing() if path == root else scandir(path)
    )
    result = discover_all(paths, collectors=[ProjectMcpJsonCollector(paths)])
    assert [s.name for s in result.servers] == ["visible"]
    assert result.source_counts == {"project_mcp_json": 1}
    assert any(str(root) in err and "listing interrupted" in err for err in result.errors)
