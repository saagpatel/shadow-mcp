# Changelog

## Unreleased

- Discovery reports incomplete sources and retains valid siblings in JSON server maps.
  The JSON and TOML readers accept files up to 16 MiB.
- The MCP `list_sources` tool returns an error with diagnostics when discovery is
  incomplete. Successful calls still return the source counts.
- Graded MCP reports reject non-finite scores. Missing or invalid MCPAudit scores
  produce an unavailable capability grade. Registry and catalog failures appear in
  the trust grade's `error` field and report `notes`.
