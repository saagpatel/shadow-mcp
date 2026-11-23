"""Collector: Claude Desktop DXT extension manifests.

Each ``Claude Extensions/<id>/manifest.json`` bundles an MCP server under a
``server`` object whose ``mcp_config`` carries the command/args/env. This is a
distinct registration surface from the ``mcpServers`` block.
"""

from __future__ import annotations

from pathlib import Path

from ..models import DiscoveredServer, Provenance, SourceKind
from ._common import ConfigCollector, infer_spec, load_json

SOURCE: SourceKind = "dxt"


class DxtCollector(ConfigCollector):
    source = SOURCE

    def collect_with_errors(self, errors: list[str]) -> list[DiscoveredServer]:
        root = self.paths.claude_extensions_dir
        if not root.exists():
            return []
        out: list[DiscoveredServer] = []
        for ext in root.iterdir():
            if ext.is_dir():
                try:
                    server = _read_manifest(ext / "manifest.json")
                except (OSError, ValueError) as exc:
                    errors.append(f"{ext.name}: {exc}")
                    continue
                if server is not None:
                    out.append(server)
        return out


def _read_manifest(path: Path) -> DiscoveredServer | None:
    manifest = load_json(path)
    if manifest is None:
        return None
    name = str(manifest.get("name") or path.parent.name)
    server = manifest.get("server")
    if not isinstance(server, dict):
        return None
    raw = server.get("mcp_config", server)
    if not isinstance(raw, dict):
        raise ValueError(f"{name}: mcp_config must be an object")
    # A DXT runtime type implies stdio when the config omits its transport.
    if "type" not in raw and "transport" not in raw and not raw.get("url"):
        if str(server.get("type") or "").lower() in ("node", "python", "binary"):
            raw = {**raw, "type": "stdio"}
    return DiscoveredServer(
        name=name,
        spec=infer_spec(raw),
        provenance=Provenance(
            source=SOURCE, location=str(path), scope="desktop", declared_name=name
        ),
    )
