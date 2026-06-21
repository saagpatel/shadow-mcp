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


def test_parse_ps_output_extracts_identity_and_classifies_parent():
    # columns: pid ppid command  (matches `ps -o pid=,ppid=,command=`)
    text = (
        "  123  500 /opt/homebrew/bin/node /x/personal-ops/app/dist/src/mcp-server.js\n"
        "  124  500 /opt/homebrew/bin/node /x/personal-ops/app/dist/src/mcp-server.js\n"
        "  456    1 /usr/bin/python3 -m some.other.thing\n"
        "  789 88920 npx -y @modelcontextprotocol/server-github\n"
        "  790 82845 /Applications/Claude.app/Contents/Helpers/disclaimer /opt/homebrew/bin/uv "
        "--directory /x/Claude Extensions/cursortouch.macos-mcp run macos-mcp\n"
        "  900    1 /opt/homebrew/bin/uv run --directory /x/notification-hub/mcp_server python server.py\n"
        "  999  500 /usr/bin/shadow-mcp scan\n"
        # host processes referenced as parents above:
        "  500    1 /Applications/Codex.app/Contents/Resources/codex app-server\n"
        "88920    1 claude --dangerously-skip-permissions\n"
        "82845    1 /Applications/Claude.app/Contents/MacOS/Claude\n"
    )
    servers = parse_ps_output(text)
    by_name = {s.name: s for s in servers}
    # identity extraction
    assert "personal-ops" in by_name  # script path -> project
    assert "macos-mcp" in by_name  # `run macos-mcp` -> package
    assert "@modelcontextprotocol/server-github" in by_name
    assert "notification-hub" in by_name  # --directory -> project
    assert "some.other.thing" not in by_name  # no marker
    assert not any("shadow" in n for n in by_name)
    assert len([s for s in servers if s.name == "personal-ops"]) == 1
    # parent classification: host-spawned vs standalone (the thread-1 signal)
    assert by_name["personal-ops"].provenance.host_managed is True  # parent = codex
    assert (
        by_name["@modelcontextprotocol/server-github"].provenance.host_managed is True
    )  # parent = claude
    assert by_name["notification-hub"].provenance.host_managed is False  # ppid 1 = launchd


def test_parse_ps_output_climbs_past_launchers_to_real_owner():
    # The real Hermes case: the MCP process's immediate parent is a `uv run`
    # launcher shim; the actual owner (the Hermes gateway) is one hop up. We must
    # climb past the shim and recognize Hermes, not flag a managed server as rogue.
    text = (
        "  600  650 /opt/homebrew/bin/uv run --directory /x/notification-hub/mcp_server python server.py\n"
        "  650  660 /opt/homebrew/bin/uv run --frozen wrapper\n"  # launcher shim, climb past
        "  660    1 /Users/dev/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway run\n"
        # a genuinely standalone server (launchd-direct, no host ancestor)
        "  700    1 /opt/homebrew/bin/uv run --directory /x/rogue-thing/mcp_server python server.py\n"
    )
    servers = parse_ps_output(text)
    by_name = {s.name: s for s in servers}
    # Hermes-owned server is correctly host-managed (not a rogue)
    assert by_name["notification-hub"].provenance.host_managed is True
    assert "hermes" in (by_name["notification-hub"].provenance.parent or "").lower()
    # the launchd-direct one stays standalone
    assert by_name["rogue-thing"].provenance.host_managed is False
