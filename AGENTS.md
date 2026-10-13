# Purpose

shadow-mcp discovers and risk-grades configured MCP servers from local
configuration and the process table. Keep routine work local and read-only.

# Layout

- `src/shadow_mcp/`: CLI, MCP server, collectors, inventory, grading, and reports.
- `tests/`: pytest coverage using synthetic homes and process output.
- `docs/`: risk model and project documentation.
- `server.json`: MCP registry metadata; keep both package versions aligned with
  the project version.
- `uv.lock`: locked runtime and development dependency graph.

# Setup

Install the latest stable Python 3.x and uv, then run `make setup`.

# Checks

Run `make check` for the lock check, Ruff lint and format checks, mypy, and
pytest. Run `make build` to create the wheel and sdist.

# Boundaries

- Tests use only synthetic homes and synthetic process output.
- Never run `scan`, `discover`, or `deep-scan` against the real machine during
  development or verification.
- Keep `SHADOW_MCP_RUN_CONNECT` unset. Do not run connected grading as part of
  routine checks.
- Do not inspect or disclose real workstation configuration, process details,
  secrets, or captured inventories.
- MCP tools are local-only: they read configs and the process table, skip
  `claude mcp list`, and never connect to or spawn MCP servers.

# Delivery

Keep changes scoped to the requested behavior. Run the relevant checks and
report their actual results. CI uses `.github/workflows/ci.yml`; tagged package
publishing is configured in `.github/workflows/publish.yml` and requires the
repository's PyPI trusted-publisher setup.
