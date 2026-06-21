"""Core data model for shadow-mcp.

Invariant: we record env variable *names* (``env_keys``) but never their
values. Collectors must redact at parse time so a secret never enters the
inventory, the JSON deliverable, or a log line.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

from .redact import scrub_args, scrub_url

Transport = Literal["stdio", "http", "sse", "unknown"]

SourceKind = Literal[
    "claude_code",  # ~/.claude.json mcpServers (user + per-project scope)
    "claude_cli",  # `claude mcp list` resolved roster (incl. remote + plugin)
    "codex",  # ~/.codex/config.toml + profile TOMLs
    "project_mcp_json",  # repo-local .mcp.json
    "claude_desktop",  # Claude Desktop app config
    "dxt",  # Claude Desktop DXT extension manifests
    "process",  # live stdio/daemon process (ps / lsof)
]

# Substrings that mark an env var name as secret-bearing. Used only to *flag*
# a server as handling secrets; we never read the value either way.
SECRET_NAME_HINTS = (
    "token",
    "key",
    "secret",
    "password",
    "passwd",
    "auth",
    "credential",
    "apikey",
    "api_key",
    "access",
    "private",
)


class Provenance(BaseModel):
    """Where one sighting of a server came from."""

    source: SourceKind
    location: str  # file path, "claude mcp list", or "ps"
    scope: str = "user"  # user | project | profile | runtime | desktop
    declared_name: str
    enabled: bool | None = None  # None = source doesn't express enable state
    host_managed: bool | None = None  # process-only: spawned by a known MCP host
    parent: str | None = None  # process-only: parent process command (provenance)


class ServerSpec(BaseModel):
    """A normalized, redacted server specification."""

    transport: Transport = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    env_keys: list[str] = Field(default_factory=list)  # NAMES only, never values

    @model_validator(mode="after")
    def _scrub_inline_secrets(self) -> ServerSpec:
        """Single chokepoint: no inline secret in args/url ever reaches storage."""
        if self.args:
            self.args = scrub_args(self.args)
        if self.url:
            self.url = scrub_url(self.url)
        return self

    @property
    def secret_env_keys(self) -> list[str]:
        """Env var names that look secret-bearing (by name only; value never read)."""
        return sorted(k for k in self.env_keys if any(h in k.lower() for h in SECRET_NAME_HINTS))


class DiscoveredServer(BaseModel):
    """A single raw sighting from one collector, before cross-source merge."""

    name: str
    spec: ServerSpec
    provenance: Provenance


class InventoryEntry(BaseModel):
    """One logical server, merged across every source that referenced it."""

    identity: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    spec: ServerSpec
    provenances: list[Provenance] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sources(self) -> list[SourceKind]:
        return list(dict.fromkeys(p.source for p in self.provenances))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def running(self) -> bool:
        return any(p.source == "process" for p in self.provenances)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def standalone_process(self) -> bool:
        """A live process NOT spawned by a known MCP host (a genuine rogue, not a
        host/plugin-managed child)."""
        return any(p.source == "process" and p.host_managed is False for p in self.provenances)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def configured(self) -> bool:
        return any(p.source != "process" for p in self.provenances)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def host_count(self) -> int:
        """Distinct config hosts (excludes the runtime/process sighting)."""
        hosts = {p.source for p in self.provenances if p.source != "process"}
        return len(hosts)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def disabled(self) -> bool:
        """True only if every provenance that expresses state says disabled."""
        states = [p.enabled for p in self.provenances if p.enabled is not None]
        return bool(states) and not any(states)


class McpAuditGrade(BaseModel):
    composite: float  # 0-10 capability risk
    high_risk: bool  # composite >= 7.0
    findings: list[dict] = Field(default_factory=list)  # {rule_id, severity, title, category}
    dimensions: dict[str, float] = Field(default_factory=dict)
    error: str | None = None
    connected: bool = False  # True = graded by spawning the server + enumerating tools
    connection_status: str | None = None  # connected | failed | skipped
    tool_count: int | None = None  # tools enumerated (connected path only)


class McpTrustGrade(BaseModel):
    grade: str  # "A".."F" or "unknown"
    transparency: str | None = None  # high | medium | low
    composite: float | None = None
    slug: str | None = None
    scanned_at: str | None = None
    computed: bool = False  # True = derived via mcp-trust grade() from MCPAudit dims,
    #                         not a persisted registry scan


Band = Literal["critical", "high", "medium", "low", "unknown"]


class RiskAssessment(BaseModel):
    band: Band
    headline: str
    mcpaudit: McpAuditGrade | None = None
    mcptrust: McpTrustGrade | None = None
    reasons: list[str] = Field(default_factory=list)


class GradedServer(BaseModel):
    entry: InventoryEntry
    risk: RiskAssessment


class ShadowFinding(BaseModel):
    """A delta worth the operator's attention (the 'shadow' layer)."""

    # kind: running_unconfigured | host_spawned_unconfigured | broad_blast_radius
    #       | ungraded_capable | disabled_present | adversarial_fixture
    kind: str
    server: str
    detail: str
    band: Band = "medium"


class Report(BaseModel):
    generated_at: str
    host: str
    servers: list[GradedServer]
    shadow: list[ShadowFinding] = Field(default_factory=list)
    source_summary: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
