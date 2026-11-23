import pytest

from shadow_mcp.collectors import discover_all
from shadow_mcp.collectors.claude_cli import ClaudeCliCollector
from shadow_mcp.collectors.processes import ProcessCollector
from shadow_mcp.config import DiscoveryPaths


@pytest.mark.parametrize(
    "collector, reply, diagnostic",
    [
        (ProcessCollector, (1, ""), "1"),
        (ProcessCollector, (0, "incomplete"), "rows"),
        (ClaudeCliCollector, (2, ""), "2"),
    ],
)
def test_failed_listing_reports_source(tmp_path, collector, reply, diagnostic):
    result = discover_all(DiscoveryPaths.default(tmp_path), collectors=[collector(lambda: reply)])
    assert result.errors, result.source_counts
    assert collector.source in result.errors[0] and diagnostic in result.errors[0]


def test_valid_process_listing_without_servers(tmp_path):
    collector = ProcessCollector(lambda: (0, "  101  1 /bin/sleep 60"))
    result = discover_all(DiscoveryPaths.default(tmp_path), collectors=[collector])
    assert result.errors == []
    assert result.source_counts == {"process": 0}
