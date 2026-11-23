import os
from contextlib import contextmanager
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


def test_bad_config_files_preserve_other_files(fake_paths):
    profile = fake_paths.codex_config.with_name("extra.config.toml")
    profile.write_text("[")
    fake_paths.codex_profile_configs.append(profile)
    bad_manifest = fake_paths.claude_extensions_dir / "bad" / "manifest.json"
    bad_manifest.parent.mkdir()
    bad_manifest.write_text('{"server":{"mcp_config":7}}')
    (fake_paths.projects_root / ".mcp.json").write_text("{")
    result = discover_all(fake_paths, include_processes=False, include_cli=False)
    assert {
        source: result.source_counts.get(source) for source in ("codex", "dxt", "project_mcp_json")
    } == {
        "codex": 3,
        "dxt": 1,
        "project_mcp_json": 2,
    }
    assert len(result.errors) == 3


def test_interrupted_profile_listing_keeps_yielded_entry(tmp_path, monkeypatch):
    profile = tmp_path / ".codex" / "visible.config.toml"
    profile.parent.mkdir()
    profile.touch()
    scandir = os.scandir

    def first_then_error(entries):
        yield next(entries)
        raise OSError("listing interrupted")

    @contextmanager
    def interrupted(path):
        assert Path(path) == profile.parent
        with scandir(path) as entries:
            yield first_then_error(entries)

    monkeypatch.setattr(os, "scandir", interrupted)
    paths = DiscoveryPaths.default(tmp_path)
    assert paths.codex_profile_configs == [profile]
    assert any("listing interrupted" in error for error in paths.codex_profile_errors)


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
    stat = Path.stat

    def deny_excluded(path, *args, **kwargs):
        if path == excluded:
            raise PermissionError("permission denied")
        return stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", deny_excluded)
    result = discover_all(paths, collectors=[ProjectMcpJsonCollector(paths)])
    assert result.errors == []
    assert result.source_counts == {"project_mcp_json": 3}
