"""Collector: Claude Desktop DXT extension manifests.

Each ``Claude Extensions/<id>/manifest.json`` bundles an MCP server under a
``server`` object whose ``mcp_config`` carries the command/args/env. This is a
distinct registration surface from the ``mcpServers`` block.
"""

from __future__ import annotations

from ..config import DiscoveryPaths
from ..models import DiscoveredServer, Provenance, SourceKind
from ._common import infer_spec, load_json

SOURCE: SourceKind = "dxt"


class DxtCollector:
    source = SOURCE

    def __init__(self, paths: DiscoveryPaths) -> None:
        self.paths = paths

    def collect(self) -> list[DiscoveredServer]:
        root = self.paths.claude_extensions_dir
        if not root.exists():
            return []
        out: list[DiscoveredServer] = []
        try:
            ext_dirs = [d for d in root.iterdir() if d.is_dir()]
        except OSError:
            return []
        for ext in ext_dirs:
            manifest = load_json(ext / "manifest.json")
            if manifest is None:
                continue
            name = str(manifest.get("name") or ext.name)
            server_value = manifest.get("server")
            if not isinstance(server_value, dict):
                continue
            server: dict[str, object] = server_value
            config_value = server.get("mcp_config")
            raw: dict[str, object] = config_value if isinstance(config_value, dict) else server
            # A DXT server type (node/python/binary) implies a stdio transport;
            # inject it into the raw dict so infer_spec resolves it at construction
            # (rather than mutating the validated model afterward).
            if "type" not in raw and "transport" not in raw and not raw.get("url"):
                stype = str(server.get("type") or "").lower()
                if stype in ("node", "python", "binary"):
                    raw = {**raw, "type": "stdio"}
            spec = infer_spec(raw)
            out.append(
                DiscoveredServer(
                    name=name,
                    spec=spec,
                    provenance=Provenance(
                        source=SOURCE,
                        location=str(ext / "manifest.json"),
                        scope="desktop",
                        declared_name=name,
                    ),
                )
            )
        return out
