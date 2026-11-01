"""
VECTOR Coding Assistant — core/coding_assistant/

A full-featured AI coding assistant engine for VECTOR.
Provides the agent loop, tool implementations, ACP protocol,
session management, hooks, skills parser, and LLM backends
that power VECTOR's coding district.

Subpackages:
    acp/         — Agent Communication Protocol (session-based agent interaction)
    core/        — Core engine (agent_loop, tools, skills, hooks, middleware)
    cli/         — CLI adapters (autocompletion, history, voice)

Key entry points:
    core.coding_assistant.core.programmatic  — programmatic agent execution
    core.coding_assistant.acp.entrypoint     — ACP server entry point
    core.coding_assistant.core.tools         — all tool implementations
"""
from __future__ import annotations
from pathlib import Path

VECTOR_CA_ROOT = Path(__file__).parent
VIBE_ROOT = VECTOR_CA_ROOT  # alias — internal modules import VIBE_ROOT from here
__version__ = "2.9.6"
