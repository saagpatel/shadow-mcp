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
