"""Merge raw sightings into one entry per logical server.

Two sightings are the same server if they share a command/url *signature* OR a
normalized name. We resolve this with a union-find over both keys, so a server
seen as `personal-ops` (Claude Code) and `personal_ops` (Codex) collapses into a
single entry carrying both provenances.
"""

from __future__ import annotations

from collections import Counter

from .identity import normalize_name, relaxed_name, signature
from .models import DiscoveredServer, InventoryEntry, ServerSpec


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _pick_canonical_spec(specs: list[ServerSpec]) -> ServerSpec:
    """Prefer the richest spec: a URL or command with the most detail wins."""

    def richness(s: ServerSpec) -> tuple[int, int, int]:
        has_endpoint = 1 if (s.url or s.command) else 0
        return (has_endpoint, len(s.args), len(s.env_keys))

    return max(specs, key=richness)


def build_inventory(discovered: list[DiscoveredServer]) -> list[InventoryEntry]:
    """Group raw sightings into merged inventory entries."""
    if not discovered:
        return []

    uf = _UnionFind()
    sig_rep: dict[str, int] = {}
    name_rep: dict[str, int] = {}

    # A process sighting may be the resolved form of a configured server
    # (`github-mcp-server` running as the configured `github`). Pre-register the
    # relaxed names of config sightings so a process can reconcile into its twin.
    relaxed_config_rep: dict[str, int] = {}
    for i, d in enumerate(discovered):
        if d.provenance.source != "process":
            rk = relaxed_name(d.name)
            if len(rk) >= 3:
                relaxed_config_rep.setdefault(rk, i)

    for i, d in enumerate(discovered):
        uf.find(i)  # ensure node exists
        sig = signature(d.spec)
        nkey = normalize_name(d.name)
        if sig in sig_rep:
            uf.union(sig_rep[sig], i)
        else:
            sig_rep[sig] = i
        # Only union by name when the name is meaningful (a real, non-empty token).
        if nkey and nkey != "unknown":
            if nkey in name_rep:
                uf.union(name_rep[nkey], i)
            else:
                name_rep[nkey] = i
        # Conservative reconciliation: a process whose relaxed name matches a
        # configured server's relaxed name is that server running.
        if d.provenance.source == "process":
            rk = relaxed_name(d.name)
            if len(rk) >= 3 and rk in relaxed_config_rep:
                uf.union(relaxed_config_rep[rk], i)

    groups: dict[int, list[int]] = {}
    for i in range(len(discovered)):
        groups.setdefault(uf.find(i), []).append(i)

    entries: list[InventoryEntry] = []
    for members in groups.values():
        items = [discovered[i] for i in members]
        names = [d.name for d in items]
        name_counts = Counter(names)
        # names from a config (not a synthesized process name) are preferred.
        config_names = {d.name for d in items if d.provenance.source != "process"}
        # canonical = most frequent; prefer config-sourced; then shortest; then alpha
        canonical = sorted(
            name_counts,
            key=lambda n: (-name_counts[n], 0 if n in config_names else 1, len(n), n),
        )[0]
        aliases = sorted({n for n in names if n != canonical})
        spec = _pick_canonical_spec([d.spec for d in items])
        provenances = [d.provenance for d in items]
        # stable identity string for the entry
        ident = signature(spec)
        entries.append(
            InventoryEntry(
                identity=ident,
                canonical_name=canonical,
                aliases=aliases,
                spec=spec,
                provenances=provenances,
            )
        )

    entries.sort(key=lambda e: e.canonical_name.lower())
    return entries
