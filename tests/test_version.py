import json
from importlib.metadata import version
from pathlib import Path

from shadow_mcp import __version__


def test_package_versions_match_server_metadata() -> None:
    metadata = json.loads(Path("server.json").read_text(encoding="utf-8"))
    assert __version__ == version("shadow-mcp")
    assert metadata["version"] == __version__
    assert metadata["packages"][0]["version"] == __version__
