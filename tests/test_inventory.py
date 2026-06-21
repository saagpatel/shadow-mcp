from shadow_mcp.inventory import build_inventory
from shadow_mcp.models import DiscoveredServer, Provenance, ServerSpec


def _disc(name, source, command=None, url=None, args=None, enabled=None):
    return DiscoveredServer(
        name=name,
        spec=ServerSpec(
            transport="http" if url else "stdio",
            command=command,
            url=url,
            args=args or [],
        ),
        provenance=Provenance(
            source=source, location=source, scope="user", declared_name=name, enabled=enabled
        ),
    )


def test_merges_across_hosts_by_normalized_name():
    discovered = [
        _disc("personal-ops", "claude_code", command="/a/personal-ops-mcp"),
        _disc("personal_ops", "codex", command="/b/personal-ops-mcp"),
    ]
    entries = build_inventory(discovered)
    assert len(entries) == 1
    e = entries[0]
    assert set(e.sources) == {"claude_code", "codex"}
    assert e.host_count == 2
    assert "personal_ops" in e.aliases or "personal-ops" in e.aliases


def test_merges_by_signature_when_names_differ():
    # same command target, cosmetically different names -> one entry
    discovered = [
        _disc("ctx7", "claude_code", command="npx", args=["@upstash/context7-mcp"]),
        _disc("context7", "codex", command="npx", args=["@upstash/context7-mcp@1.0"]),
    ]
    entries = build_inventory(discovered)
    assert len(entries) == 1


def test_distinct_servers_stay_separate():
    discovered = [
        _disc("serena", "claude_code", command="serena", args=["start-mcp-server"]),
        _disc("engraph", "claude_code", command="engraph", args=["serve"]),
    ]
    entries = build_inventory(discovered)
    assert len(entries) == 2


def test_process_reconciles_into_configured_twin_by_relaxed_name():
    # the running `github-mcp-server` is the configured `github` via its wrapper
    discovered = [
        _disc("github", "codex", command="/x/.codex/bin/github-mcp"),
        _disc("github-mcp-server", "process", command="/x/.codex/bin/github-mcp-server"),
    ]
    entries = build_inventory(discovered)
    assert len(entries) == 1
    (entry,) = entries
    assert entry.running and entry.configured


def test_relaxed_reconciliation_does_not_overmerge_distinct_servers():
    # two genuinely different configured servers must not collapse via relaxed names
    discovered = [
        _disc("github", "codex", command="github"),
        _disc("gitlab", "codex", command="gitlab"),
    ]
    assert len(build_inventory(discovered)) == 2


def test_running_and_configured_flags():
    discovered = [
        _disc("serena", "claude_code", command="serena"),
        _disc("serena", "process", command="serena"),
    ]
    (entry,) = build_inventory(discovered)
    assert entry.running is True
    assert entry.configured is True


def test_disabled_only_when_all_states_disabled():
    discovered = [_disc("serena", "codex", command="serena", enabled=False)]
    (entry,) = build_inventory(discovered)
    assert entry.disabled is True

    mixed = [
        _disc("serena", "codex", command="serena", enabled=False),
        _disc("serena", "claude_code", command="serena", enabled=True),
    ]
    (entry2,) = build_inventory(mixed)
    assert entry2.disabled is False


def test_distinct_script_servers_do_not_false_merge():
    # two genuinely different servers in different projects, both `node server.js`,
    # must stay separate — a discovery tool must never drop a server via false-merge.
    discovered = [
        _disc("alpha", "project_mcp_json", command="node", args=["/projA/server.js"]),
        _disc("beta", "project_mcp_json", command="node", args=["/projB/server.js"]),
    ]
    entries = build_inventory(discovered)
    assert len(entries) == 2
    assert {e.canonical_name for e in entries} == {"alpha", "beta"}


def test_same_script_full_path_still_merges():
    # the same server seen in config and as a running process (identical full path)
    # must still collapse into one entry.
    discovered = [
        _disc("alpha", "project_mcp_json", command="node", args=["/projA/server.js"]),
        _disc("alpha", "process", command="node", args=["/projA/server.js"]),
    ]
    (entry,) = build_inventory(discovered)
    assert entry.running and entry.configured


def test_relative_config_merges_with_absolute_process():
    # a config-relative `node ./mcp-server.js` and its absolute running form must
    # collapse into one entry, not split into config + false running_unconfigured.
    from shadow_mcp.collectors._common import parse_mcp_servers_block

    cfg = parse_mcp_servers_block(
        {"docs": {"command": "node", "args": ["./mcp-server.js"]}},
        source="project_mcp_json",
        location="/repo/.mcp.json",
        scope="project",
    )
    proc = DiscoveredServer(
        name="repo",
        spec=ServerSpec(transport="stdio", command="node", args=["/repo/mcp-server.js"]),
        provenance=Provenance(
            source="process", location="ps", scope="runtime", declared_name="repo"
        ),
    )
    entries = build_inventory(cfg + [proc])
    assert len(entries) == 1
    assert entries[0].running and entries[0].configured


def test_empty_input():
    assert build_inventory([]) == []
