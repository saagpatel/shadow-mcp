"""Read-only collectors, one per place an MCP server can be declared or run."""

from .base import DiscoveryResult, discover_all

__all__ = ["DiscoveryResult", "discover_all"]
