# VECTOR-INGESTED MODULE
# Source: github/open-jarvis/OpenJarvis/src/openjarvis/tools/templates/__init__.py
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""MCP tool templates — reusable tool definitions from TOML."""

from vectorcode.src.oj_tools.templates.loader import ToolTemplate, discover_templates

__all__ = ["ToolTemplate", "discover_templates"]
