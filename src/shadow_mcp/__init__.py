"""shadow-mcp: discover and risk-grade the MCP servers present on this machine.

Discovery is strictly read-only: collectors parse configs and list processes,
and never mutate anything they find. Risk-grading delegates to the existing
engines (MCPAudit for a 0-10 capability composite, mcp-trust for an A-F danger
grade) rather than reimplementing them.
"""

__version__ = "0.1.0"
