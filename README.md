# shadow-mcp

Discover and risk-grade the MCP servers actually present on **this** machine.

Most MCP security tooling assumes you already have a list of servers to audit.
On a real developer machine you don't: servers are scattered across Claude Code,
Codex, Claude Desktop, project-local `.mcp.json` files, DXT extensions, and live
processes that bind no port. shadow-mcp finds them first, then grades them.

This is the local-first answer to **OWASP MCP09:2025 — Shadow MCP Servers**.

## What it does

```
discover  ->  inventory  ->  risk-grade  ->  report
```

1. **Discover** (read-only) every place an MCP server is declared or running:
   Claude Code (`~/.claude.json`, user + project scope), `claude mcp list`
   (catches remote + plugin servers no file contains), Codex
   (`~/.codex/config.toml` + profiles), project `.mcp.json`, Claude Desktop
   config + DXT extension manifests, and the live process table.
2. **Inventory**: merge sightings into one entry per logical server, even when a
   server appears under different names across hosts (`personal-ops` vs
   `personal_ops`), tracking every provenance.
3. **Risk-grade** by **delegating** to the existing engines rather than
   reimplementing them:
   - [MCPAudit](../MCPAudit) for a 0-10 capability composite + injection findings
   - [mcp-trust](../mcp-trust) for an authoritative A-F danger grade (when known)
   - a thin local layer for the config-shaped OWASP dimensions the engines under-cover
     (secrets/MCP01, supply-chain provenance/MCP04, transport exposure/MCP07).
4. **Report**: a ranked terminal table, a machine-readable JSON inventory, or
   markdown — plus a **Shadow & attention** section for the deltas that matter
   (running-but-unconfigured, broad blast radius, capable-but-ungraded).

The risk model and its OWASP mapping live in [docs/risk-model.md](docs/risk-model.md).

## Install

```bash
uv sync                 # installs deps incl. MCPAudit as a local editable engine
```

shadow-mcp grades against your local checkouts of MCPAudit (`../MCPAudit`) and
mcp-trust (`../mcp-trust/registry.db`). Override with `SHADOW_MCP_MCPTRUST_DB`
or `--registry-db`.

## Use

```bash
uv run shadow-mcp scan                      # full pipeline, terminal report
uv run shadow-mcp scan --json out.json      # machine-readable inventory
uv run shadow-mcp scan --format markdown    # markdown report
uv run shadow-mcp discover                  # inventory only, no grading
uv run shadow-mcp sources                   # per-collector counts
uv run shadow-mcp grade-missing             # A-F for servers the registry hasn't scanned
uv run shadow-mcp deep-scan cost-tracker    # connect to a server, grade its real tools
```

Useful flags: `--no-processes` (skip the live process scan), `--no-cli` (skip
`claude mcp list`), `--no-mcpaudit` (inventory + mcp-trust only), `--home PATH`
(point discovery at a fixture tree).

### Static vs connected grading

By default grading is **static** (config-only): no server is spawned, so grades
reflect what's visible in the config. That's safe but coarse — a server's real
capability only shows once you connect and list its tools.

`shadow-mcp scan --connect` (or `deep-scan [names...]`) **spawns** each stdio
server and enumerates its real tools, delegating to MCPAudit's connected engine
for a capability grade that actually differentiates (a filesystem server jumps
from a static `A` to a connected `D`). This is **opt-in** because connecting
executes the server; remote endpoints are never spawned (that's the network-scan
tier), and a server that needs real secrets to start falls back to its static
grade.

## Safety

- **Read-only discovery.** Collectors parse configs and list processes; nothing
  they find is ever mutated. (`--connect`/`deep-scan` is the one path that
  *executes* servers, and only when you explicitly ask.)
- **Secrets stay out.** We record env variable *names* (to flag secret-bearing
  servers per MCP01) but never their values. A captured inventory still contains
  real local paths and hostnames, so treat `*.inventory.json` as private (it is
  git-ignored by default).

## Scope

This is the **local-first** tool: it inventories one machine from its configs
and processes. A later network-scan expansion (probing hosts/ports for remote
MCP endpoints, org-wide fleet inventory, typosquat-distance provenance checks)
is deliberately out of scope here — see the bottom of `docs/risk-model.md` and
the project notes for what that would add.
