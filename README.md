# shadow-mcp
<!-- mcp-name: io.github.saagpatel/shadow-mcp -->

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

1. **Discover** (read-only) MCP servers from supported configuration and runtime sources:
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

From this repository root, use Python 3.11+ and `uv`:

```bash
uv sync --locked --python 3.11   # Python version installed by CI; locked runtime and default dev group
```

The grading engines (`mcp-audits` and `mcp-trust`) are runtime dependencies
resolved from PyPI, not editable sibling checkouts or an `engines` group.
The installed mcp-trust package supplies its seed catalog; `--registry-db` or
`SHADOW_MCP_MCPTRUST_DB` selects an explicitly chosen local registry instead.

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

## Development and safe verification

The committed `uv.lock` fixes the PyPI runtime and development graph. Locked
sync validates it against `pyproject.toml` without changing the lock. After the
sync above, run from the repository root:

```bash
uv run --no-sync pytest tests/test_cli.py::test_discover_skips_grading -q
uv run --no-sync pytest tests/test_cli.py::test_scan_json_end_to_end -q
uv run --no-sync ruff check .
uv run --no-sync pytest
```

The two focused tests build a temporary synthetic home and disable both process
and CLI discovery. The scan test additionally disables MCPAudit and supplies an
absent temporary registry path. They exercise inventory/reporting without
reading workstation configs, executing servers or connecting to endpoints.

The broader suite uses fixtures and includes config-only engine integration.
Keep `SHADOW_MCP_RUN_CONNECT` unset: the explicitly opted-in connected test is a
separate server-execution lane, not the routine smoke. CI runs `uv sync --locked`, Ruff
and pytest after installing Python 3.11; see [the workflow](.github/workflows/ci.yml). There
is no separate configured formatter or typecheck lane. `uv build` is the wheel
and sdist build used by [the release workflow](.github/workflows/publish.yml);
building locally does not publish, and tagging/publishing is a separate action.

Do not use the normal `scan`, `discover`, `sources`, `grade-missing` or MCP tool
calls as a development smoke: they inventory the machine by default. CLI
`deep-scan` and `scan --connect` additionally execute servers. For changed JSON
or Markdown reports, check the corresponding fixture tests (`tests/test_report.py`)
and inspect synthetic output; this CLI has no browser UI. Actual workstation or
connected behavior requires its own explicitly authorized qualification.

## Safety

- **Read-only discovery.** Collectors parse configs, invoke `claude mcp list`
  (unless `--no-cli` is set), and list processes; nothing
  they find is ever mutated. (`--connect`/`deep-scan` is the one path that
  *executes* servers, and only when you explicitly ask.)
- **Secrets stay out.** We record env variable *names* (to flag secret-bearing
  servers per MCP01) but never their values. A captured inventory still contains
  real local paths and hostnames, so treat `*.inventory.json` as private (it is
  git-ignored by default).

## Use as an MCP server

shadow-mcp can serve its own inventory tools as an MCP server so an agent can
query your local MCP surface without leaving the conversation.

### Tools

| Tool | Description |
|---|---|
| `scan_local` | Full pipeline (discover → inventory → grade → report). Returns JSON. |
| `discover_local` | Inventory every MCP server without grading. Returns JSON. |
| `deep_scan` | Grade the named servers, or all servers when the list is empty (static, no spawning). Accepts `names: list[str]`. Returns JSON. |
| `list_sources` | Per-collector source counts from a discover run. Returns JSON. |

### Run the server

```bash
# directly from a local checkout
uv run shadow-mcp mcp-serve

# via uvx (once published to PyPI)
uvx shadow-mcp mcp-serve
```

**LOCAL only.** The MCP server never connects to hosted MCP endpoints — all
grading is static (config-based). `connect=False` is enforced unconditionally;
no server is ever spawned from an MCP tool call.

## Scope

This is the **local-first** tool: it inventories one machine from its configs
and processes. A later network-scan expansion (probing hosts/ports for remote
MCP endpoints, org-wide fleet inventory, typosquat-distance provenance checks)
is deliberately out of scope here — see the bottom of `docs/risk-model.md` and
the project notes for what that would add.
