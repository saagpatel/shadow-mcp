from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from shadow_mcp.collectors import _common, discover_all
from shadow_mcp.collectors._common import load_json
from shadow_mcp.collectors.claude_code import ClaudeCodeCollector
from shadow_mcp.collectors.codex import CodexCollector, _load_toml


@pytest.mark.parametrize("loader, document", [(load_json, b"{}"), (_load_toml, b"x=1")])
def test_config_read_is_bounded(loader, document, monkeypatch):
    limit = len(document)
    monkeypatch.setattr(_common, "MAX_CONFIG_BYTES", limit, raising=False)
    handle = mock_open(read_data=document)
    with patch.object(Path, "open", handle):
        assert loader(Path("fixture")) is not None
    handle().read.assert_called_once_with(limit + 1)

    with patch.object(Path, "open", mock_open(read_data=document + b" ")):
        with pytest.raises(ValueError, match="fixture.*bytes"):
            loader(Path("fixture"))


@pytest.mark.parametrize(
    "collector, attr, content, format_name",
    [
        (ClaudeCodeCollector, "claude_json", "{", "JSON"),
        (CodexCollector, "codex_config", "[", "TOML"),
    ],
)
def test_truncated_config_reports_source(fake_paths, collector, attr, content, format_name):
    path = getattr(fake_paths, attr)
    path.write_text(content, encoding="utf-8")
    result = discover_all(fake_paths, collectors=[collector(fake_paths)])
    assert result.errors, result.source_counts
    assert collector.source in result.errors[0] and format_name in result.errors[0]
    assert str(path) in result.errors[0]
