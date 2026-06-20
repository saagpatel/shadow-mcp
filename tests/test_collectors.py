from shadow_mcp.collectors import discover_all
from shadow_mcp.collectors.claude_cli import parse_claude_mcp_list
from shadow_mcp.collectors.claude_code import ClaudeCodeCollector
from shadow_mcp.collectors.codex import CodexCollector
from shadow_mcp.collectors.processes import parse_ps_output


def test_claude_code_collector_redacts_env_to_keys(fake_paths):
    servers = ClaudeCodeCollector(fake_paths).collect()
    by_name = {s.name: s for s in servers}
    assert "personal-ops" in by_name
    po = by_name["personal-ops"]
    assert po.spec.env_keys == ["PERSONAL_OPS_CLIENT_ID"]
    # the secret VALUE must never appear anywhere in the spec, only the key name
    assert "s3cr3t-sentinel-DO-NOT-LEAK" not in po.spec.model_dump_json()


def test_claude_code_http_transport(fake_paths):
    servers = ClaudeCodeCollector(fake_paths).collect()
    ctx7 = next(s for s in servers if s.name == "context7")
    assert ctx7.spec.transport == "http"
    assert ctx7.spec.url == "https://mcp.context7.com/mcp"


def test_codex_collector_parses_toml_and_enabled(fake_paths):
    servers = CodexCollector(fake_paths).collect()
    by_name = {s.name: s for s in servers}
    assert {"personal_ops", "github", "serena"} <= set(by_name)
    assert by_name["serena"].provenance.enabled is False


def test_discover_all_is_fail_soft_on_missing_sources(fake_paths):
    # no processes / cli in the fixture; everything else present
    result = discover_all(fake_paths, include_processes=False, include_cli=False)
    assert result.errors == []
    assert result.source_counts.get("claude_code", 0) >= 2
    assert result.source_counts.get("codex", 0) == 3
    assert result.source_counts.get("claude_desktop", 0) == 1
    assert result.source_counts.get("dxt", 0) == 1
    # two project .mcp.json files (reliquary + adversarial fixture)
    assert result.source_counts.get("project_mcp_json", 0) == 2


def test_parse_claude_mcp_list_handles_http_and_stdio():
    text = (
        "personal-ops: /Users/dev/.claude/bin/personal-ops-mcp - ✓ Connected\n"
        "context7: https://mcp.context7.com/mcp (HTTP) - ✓ Connected\n"
        "serena: /Users/dev/.local/bin/serena start-mcp-server --context=claude-code - ✓ Connected\n"
    )
    servers = parse_claude_mcp_list(text)
    by_name = {s.name: s for s in servers}
    assert by_name["context7"].spec.transport == "http"
    assert by_name["context7"].spec.url == "https://mcp.context7.com/mcp"
    assert by_name["personal-ops"].spec.transport == "stdio"
    assert by_name["serena"].spec.command.endswith("serena")


def test_parse_ps_output_keeps_only_mcp_markers():
    text = (
        "  123 /opt/homebrew/bin/node /x/personal-ops/app/dist/src/mcp-server.js\n"
        "  124 /opt/homebrew/bin/node /x/personal-ops/app/dist/src/mcp-server.js\n"
        "  456 /usr/bin/python3 -m some.other.thing\n"
        "  789 npx -y @modelcontextprotocol/server-github\n"
        "  790 /Applications/Claude.app/Contents/Helpers/disclaimer /opt/homebrew/bin/uv "
        "--directory /x/Claude Extensions/cursortouch.macos-mcp run macos-mcp\n"
        "  999 /usr/bin/shadow-mcp scan\n"
    )
    servers = parse_ps_output(text)
    names = {s.name for s in servers}
    # script path resolves to the project, not "mcp-server.js"
    assert "personal-ops" in names
    # `run macos-mcp` resolves to the package, not "disclaimer"/"application"
    assert "macos-mcp" in names
    assert "@modelcontextprotocol/server-github" in names
    # no-marker python line and self line are dropped; duplicate PID collapses
    assert "some.other.thing" not in names
    assert not any("shadow" in n for n in names)
    assert len([s for s in servers if s.name == "personal-ops"]) == 1
    assert all(s.provenance.source == "process" for s in servers)
