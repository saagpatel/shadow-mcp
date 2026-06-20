# shadow-mcp risk model

How shadow-mcp grades a discovered MCP server, and why those dimensions are
credible. Every claim below is tagged **[ESTABLISHED]** (documented in a named,
citable source) or **[INFERENCE]** (our synthesis for the local-discovery use
case). Research date: 2026-06-20.

> The web research that produced this file is untrusted reference data, not
> instruction. It informs our classification; it carries no directive weight.

## The headline

**[ESTABLISHED]** "Shadow MCP" is not a marketing coinage. It is a formal entry
in the OWASP MCP Top 10, an official OWASP Foundation project (beta as of 2026,
canonical `MCPxx:2025` IDs): **MCP09:2025 — Shadow MCP Servers**, defined as
unapproved/unmonitored MCP deployments outside governance ("Shadow IT, 2026
edition"). shadow-mcp's entire job is OWASP MCP09. Treat the list as
established; treat the exact ordering as provisional (the project is in beta).

## OWASP MCP Top 10 (2025)

| ID | Title | shadow-mcp coverage |
|----|-------|---------------------|
| MCP01 | Token Mismanagement & Secret Exposure | local layer: flag secret-bearing env keys |
| MCP02 | Privilege Escalation via Scope Creep | delegated: MCPAudit capability composite |
| MCP03 | Tool Poisoning | delegated: MCPAudit injection findings |
| MCP04 | Software Supply Chain & Dependency Tampering | local layer: provenance hint (package runner + name) |
| MCP05 | Command Injection & Execution | delegated: MCPAudit shell_execution axis |
| MCP06 | Intent Flow Subversion | delegated: MCPAudit trifecta/shadowing findings |
| MCP07 | Insufficient Authn/Authz | local layer: transport exposure modifier |
| MCP08 | Lack of Audit & Telemetry | out of scope for a single-dev local tool (flag only) |
| MCP09 | Shadow MCP Servers | **the tool itself**: discovery + governance status |
| MCP10 | Context Injection & Over-Sharing | delegated: MCPAudit injection findings |

## Division of labor

shadow-mcp does not reimplement grading. It delegates the runtime-capability
surface to the existing engines and adds a thin local composition layer for the
config-shaped dimensions those engines do not see.

**Delegated (the engines already do this well):**
- **MCPAudit** grades a 0-10 capability composite over `{file_read, file_write,
  network, shell_execution, destructive, exfiltration}` plus injection / SSRF /
  trifecta findings. Covers MCP02, MCP03, MCP05, MCP06, MCP10 and the capability
  half of the lethal trifecta. **[ESTABLISHED]**
- **mcp-trust** gives an A-F danger grade weighting shell + file access highest.
  Authoritative letter grade when the server is in its registry. **[ESTABLISHED]**

**Local composition layer (what the engines under-cover, and what a local tool
is best placed to inspect):**
1. **Secret / token handling (MCP01).** **[INFERENCE]** The engines grade tool
   *capability*, not launch *config*. shadow-mcp reads the server's declared env
   var **names** (never values) and flags secret-bearing keys. OWASP ranks this #1.
2. **Provenance / supply chain (MCP04).** **[INFERENCE]** Neither engine grades
   where the package came from. shadow-mcp records the package-runner + package
   name as a provenance hint (a full typosquat-distance check is future work; see
   the network-scan expansion note).
3. **Transport exposure (MCP07).** **[INFERENCE]** stdio (local-only, pipe-attached)
   vs HTTP/SSE (network-reachable, confused-deputy + session-hijack surface)
   materially changes blast radius. Used as a risk modifier, not a base score.
4. **Governance / inventory status (MCP09).** **[ESTABLISHED]** the category;
   **[INFERENCE]** that it should be surfaced explicitly. shadow-mcp reports
   blast radius (how many hosts declare a server) and the shadow deltas
   (running-but-unconfigured, configured-everywhere, capable-but-ungraded).

## The lethal trifecta

**[ESTABLISHED]** Origin: Simon Willison, 2025-06-16. A system is acutely
dangerous when it simultaneously has private-data access + untrusted-content
exposure + an exfiltration channel. **[INFERENCE]** For shadow-mcp the important
adaptation is that the trifecta is frequently assembled across *several* servers
on one client, not within one server. MCPAudit emits per-server trifecta
findings; composing the trifecta across the installed set is future work.

## How the band is computed

The sortable band (critical / high / medium / low / unknown) is derived from the
MCPAudit composite as the base, then adjusted:
- base: composite >= 7 critical, >= 5 high, >= 3.5 medium, > 0 low, else unknown
- mcp-trust grade of F or D raises the band by one step (authoritative danger signal)
- an HTTP/SSE transport raises a low/medium band by one step (MCP07 exposure)
- the assessment's `reasons` cite the OWASP ID behind each contribution

This keeps the numeric grade delegated and explainable while letting the local
layer (secrets, transport, provenance, governance) shape the final verdict with
cited justification.

## Registry vs computed A-F grades

mcp-trust only stores grades for servers someone has already scanned and seeded
(a handful). Every other discovered server gets a **computed** A-F letter: we
feed MCPAudit's static dimensions into mcp-trust's own `grade()` (its danger
weighting + critical cap), so the letter comes from mcp-trust's logic, not a
reimplementation, and without writing to its database. Computed grades are
marked with a trailing `~` and flagged `computed: true`.

**Honest caveat (the transparency axis).** A computed grade is derived from
*static config only* (no connection, no live tool enumeration), so for stdio
servers launched via wrappers/npx, MCPAudit sees little and most letters land at
**A**. Per mcp-trust's own transparency model, that is `transparency: low` —
"cannot verify safe", **not** "verified safe". So a computed `A~` means "no
capability risk detectable from config alone." The **band** (not the letter)
carries the differentiated signal, because the band folds in the local OWASP
layer (transport/MCP07, secrets/MCP01, blast radius/MCP09). A connected scan,
which would populate the capability dimensions for real, is the network-scan
expansion's job, not this tool's.

## Scale context (vendor-sourced, treat as directional)

**[ESTABLISHED, vendor-sourced]** Wallarm 2026 reported 315 MCP-related vulns in
2025; Palo Alto Unit 42 reported a 78.3% attack-success rate against one
compromised server among five connected; CVE-2025-49596 (CVSS 9.4) was
unauthenticated RCE via MCP Inspector. Much of the scale framing comes from
vendors selling MCP-security products, so treat specific percentages as
directional rather than precise.

## Citations

- OWASP MCP Top 10: https://owasp.org/www-project-mcp-top-10/
- OWASP MCP09 Shadow MCP Servers: https://owasp.org/www-project-mcp-top-10/2025/MCP09-2025%E2%80%93Shadow-MCP-Servers
- OWASP MCP Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html
- Lethal trifecta (Willison, 2025-06-16): https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/
- MCP Spec security best practices (2025-06-18): https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices
- Invariant Labs, tool poisoning: https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks
- Mend.io, Shadow MCP: https://www.mend.io/blog/shadow-mcp-unauthorized-ai-connectivity-in-your-codebase/
