# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""MCP tool templates — reusable tool definitions from TOML."""

from vectorcode.src.vc_tools.templates.loader import ToolTemplate, discover_templates

__all__ = ["ToolTemplate", "discover_templates"]
