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


def test_empty_input():
    assert build_inventory([]) == []
