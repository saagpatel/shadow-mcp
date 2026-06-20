"""Delegate the A-F danger grade to the mcp-trust registry.

mcp-trust keys everything on a curated ``slug`` and ships no
reference -> slug resolver, so we build one by inverting its seed catalog
(npm/pypi reference, command, name, url -> slug) and read the latest scan row
straight from its SQLite registry, opened read-only. Almost every locally
discovered server will be ``unknown``; that is the expected, non-error default.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..config import GradingPaths
from ..identity import normalize_name, normalize_url, signature
from ..models import InventoryEntry, McpTrustGrade


def _strip_version(pkg: str) -> str:
    if pkg.startswith("@"):
        at = pkg.find("@", 1)
        return pkg[:at] if at != -1 else pkg
    return pkg.split("@", 1)[0]


def _load_seed_index(seed_path: Path) -> dict[str, str]:
    """Map every plausible lookup key -> slug from the seed catalog."""
    index: dict[str, str] = {}
    try:
        raw = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return index
    servers = raw if isinstance(raw, list) else raw.get("servers", [])
    if not isinstance(servers, list):
        return index
    for entry in servers:
        if not isinstance(entry, dict):
            continue
        slug = entry.get("slug")
        if not slug:
            continue
        keys: set[str] = {normalize_name(str(slug)), normalize_name(str(entry.get("name") or ""))}
        source = entry.get("source")
        if isinstance(source, dict):
            ref = source.get("reference")
            if ref:
                ref_s = str(ref)
                if ref_s.lower().startswith(("http://", "https://")):
                    keys.add("url:" + normalize_url(ref_s))
                else:
                    keys.add(normalize_name(_strip_version(ref_s)))
                    keys.add(normalize_name(Path(ref_s).name))
            cmd = source.get("command")
            if cmd:
                keys.add(normalize_name(Path(str(cmd)).name))
        for k in keys:
            if k:
                index.setdefault(k, str(slug))
    return index


class McpTrustGrader:
    def __init__(self, paths: GradingPaths | None = None) -> None:
        self.paths = paths or GradingPaths.default()
        self.seed_index = _load_seed_index(self.paths.mcptrust_seed)
        self._conn: sqlite3.Connection | None = None
        self._db_ok: bool | None = None

    def _connect(self) -> sqlite3.Connection | None:
        if self._db_ok is False:
            return None
        if self._conn is not None:
            return self._conn
        try:
            uri = f"file:{self.paths.mcptrust_registry_db}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True)
            self._db_ok = True
        except sqlite3.Error:
            self._db_ok = False
            self._conn = None
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def resolve_slug(self, entry: InventoryEntry) -> str | None:
        candidates: list[str] = [normalize_name(entry.canonical_name)]
        candidates += [normalize_name(a) for a in entry.aliases]
        sig = signature(entry.spec)
        if sig.startswith("url:"):
            candidates.append(sig)
        else:
            candidates.append(normalize_name(sig[len("cmd:") :]))
        if entry.spec.command:
            candidates.append(normalize_name(Path(entry.spec.command).name))
        for c in candidates:
            if c in self.seed_index:
                return self.seed_index[c]
        return None

    def grade(self, entry: InventoryEntry) -> McpTrustGrade:
        slug = self.resolve_slug(entry)
        if slug is None:
            return McpTrustGrade(grade="unknown")
        conn = self._connect()
        if conn is None:
            return McpTrustGrade(grade="unknown", slug=slug)
        try:
            cur = conn.execute(
                "SELECT grade, transparency, risk_json, scanned_at "
                "FROM scans WHERE server_slug = ? ORDER BY scanned_at DESC LIMIT 1",
                (slug,),
            )
            row = cur.fetchone()
        except sqlite3.Error:
            return McpTrustGrade(grade="unknown", slug=slug)
        if row is None:
            return McpTrustGrade(grade="unknown", slug=slug)
        grade, transparency, risk_json, scanned_at = row
        composite = None
        if risk_json:
            try:
                composite = json.loads(risk_json).get("composite")
            except (ValueError, AttributeError):
                composite = None
        return McpTrustGrade(
            grade=str(grade) if grade else "unknown",
            transparency=str(transparency) if transparency else None,
            composite=float(composite) if isinstance(composite, (int, float)) else None,
            slug=slug,
            scanned_at=str(scanned_at) if scanned_at else None,
        )
