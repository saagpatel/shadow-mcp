# Future: the network-scan expansion

shadow-mcp is deliberately **local-first**. It inventories one machine by reading
its configs and process table, and it is immediately useful and dogfoodable for
exactly that. This note records what a later **network-scan** tier would add, so
the boundary is a decision and not an accident. None of this is built yet.

## What local-first already covers

- Every config host on this machine (Claude Code, Codex, Claude Desktop, DXT,
  project `.mcp.json`) plus the live process table.
- Per-server capability grade (MCPAudit), A-F danger grade (mcp-trust), and the
  config-shaped OWASP layer: secrets (MCP01), transport exposure (MCP07),
  blast radius and shadow deltas (MCP09).

## What a network-scan tier would add

1. **Remote/host discovery (the org dimension).** Probe a host list or CIDR
   range for listening MCP endpoints (HTTP/SSE) that no local config references.
   This is the true "shadow IT" inventory across many machines, vs one machine's
   configs. Needs: a target list, an async port/endpoint prober, an MCP
   handshake probe (`initialize`) to confirm a port is really MCP.
2. **Live capability enumeration.** Connect to each server and list its actual
   `tools` / `resources` / `prompts`, instead of grading from the launch config.
   This unlocks the *connected* half of MCPAudit (drift, escalation, provenance,
   integrity, tool-poisoning in real tool descriptions) that the static
   config-only path cannot see. Needs: an MCP client, a connection budget, and a
   safety model (connecting executes the server).
3. **Supply-chain / provenance depth (MCP04).** Resolve each package to its
   registry (npm/pypi), compute typosquat distance against known-good names,
   check publisher reputation and version pinning, and flag rug-pull risk
   (a tool whose description changed since last seen). Needs: registry API
   access and a baseline store of previously-seen tool descriptions.
4. **Cross-server lethal-trifecta composition.** Compute the trifecta across the
   *set* of servers reachable by one agent (private-data access + untrusted
   content + exfiltration assembled from different servers), not just per server.
5. **Continuous monitoring.** A daemon/cron that re-scans and diffs the inventory
   over time, alerting on a new server, a capability change, or a grade drop.
6. **Fleet aggregation.** Roll many machines' inventories into one org view with
   policy/allowlist enforcement (MCP09 governance at scale).

## Why it is out of scope now

Each item above adds a dependency or a safety surface the local tool does not
need: a target list, network egress, executing servers to enumerate them, a
registry client, or a persistent baseline. The local tool stays read-only,
zero-network, and instantly useful. The network tier is a separate product
decision to make when there is a fleet to inventory, not a single machine.
