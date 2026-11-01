"""
VECTOR MCP Server — exposes district capabilities as MCP tools.

Run:  python core/mcp_server.py
Transport: stdio (default) → works with Claude Code, Cursor, any MCP client.
HTTP/SSE:  python core/mcp_server.py --transport sse --port 9000

RULE 11: All Ollama calls go through ollama_safe, never direct.
RULE 3:  All write/execute actions gate through permission_gateway.

MCP Client (outbound):
  To consume EXTERNAL MCP servers from VECTOR's Python code, use:
    from core.mcp.client import MCPClient
  This is the opposite direction — VECTOR as MCP consumer, not server.
"""
import sys
from pathlib import Path

# When run as a direct script ("python core/mcp_server.py" -- the documented
# usage above, and exactly what districts/coding/vectorcode_bridge.py's
# subprocess.Popen does), Python auto-prepends this file's own directory
# (core/) to sys.path[0]. Since core/ contains a real subpackage named
# core/email/, every module inside core/ becomes importable by its bare
# name -- the first transitive `import email` anywhere downstream (pydantic's
# plugin loader does this via importlib.metadata) then resolves to VECTOR's
# core/email/ instead of the stdlib email package, crashing with a confusing,
# unrelated "cannot import name 'CONFIG' from 'core.config'" error. Strip it
# and ensure the real repo root is present instead, before any other import.
_this_dir = str(Path(__file__).resolve().parent)
sys.path[:] = [p for p in sys.path if p != _this_dir]
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import inspect
from types import SimpleNamespace

__all__ = [
    "create_mcp_app",
    "create_mcp_server",
    "main",
]

import argparse


from loguru import logger
from core.mcp_tools.builtins import add_builtin_tools as _add_builtin_tools
from core.mcp_tools.brain_vault import add_brain_vault_tools as _add_brain_vault_tools
from core.mcp_tools.browser import add_browser_tools as _add_browser_tools
from core.mcp_tools.collections import add_collections_tools as _add_collections_tools
from core.mcp_tools.communications import add_email_tools as _add_email_tools
from core.mcp_tools.coordination import (
    add_claims_tools as _add_claims_tools,
    add_guidance_tools as _add_guidance_tools,
    add_kanban_tools as _add_kanban_tools,
)
from core.mcp_tools.code_graph import add_code_graph_tools as _add_code_graph_tools
from core.mcp_tools.db_control import add_db_control_tools as _add_db_control_tools
from core.mcp_tools.expansion import add_expansion_tools as _add_expansion_tools
from core.mcp_tools.knowledge import add_knowledge_tools as _add_knowledge_tools
from core.mcp_tools.research import add_research_tools as _add_research_tools
from core.mcp_tools.voice import add_voice_profile_tools as _add_voice_profile_tools
from core.mcp_tools.security import mcp_secure_call as _mcp_secure_call
from core.mcp_tools.memory_safety import (
    resolve_memory_path as _resolve_memory_path,
    memory_export_dir as _memory_export_dir,
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
)
from core.mcp_tools.error_handling import mcp_call_json as _mcp_call_json

try:
    from fastmcp import FastMCP
    _FASTMCP_AVAILABLE = True
except ImportError:
    _FASTMCP_AVAILABLE = False
    logger.warning("[VECTOR][mcp] fastmcp not installed — run: pip install fastmcp")

# Absorbed OJ MCP layer — provides transport fallback when FastMCP is absent
try:
    from vectorcode.src.vc_mcp import MCPServer, MCPClient, StreamableHTTPTransport
    _VC_MCP_AVAILABLE = True
except Exception:
    _VC_MCP_AVAILABLE = False

class _FallbackMCP:
    """Minimal in-process MCP facade for tests when FastMCP is unavailable."""

    def __init__(self, name: str, instructions: str = ""):
        self.name = name
        self.instructions = instructions
        self._tools = {}
        self._resources = {}

    def tool(self, fn=None, **metadata):
        def decorator(func):
            name = metadata.get("name") or func.__name__
            self._tools[name] = SimpleNamespace(
                name=name,
                description=metadata.get("description") or inspect.getdoc(func) or "",
                fn=func,
            )
            return func

        if fn is None:
            return decorator
        return decorator(fn)

    def resource(self, uri=None, **metadata):
        def decorator(func):
            resource_uri = uri or metadata.get("uri") or func.__name__
            self._resources[resource_uri] = SimpleNamespace(
                uri=resource_uri,
                name=metadata.get("name") or func.__name__,
                description=metadata.get("description") or inspect.getdoc(func) or "",
                fn=func,
            )
            return func

        if callable(uri) and not metadata:
            fn = uri
            uri = None
            return decorator(fn)
        return decorator

    async def list_tools(self):
        return [self._tools[name] for name in sorted(self._tools)]

    async def call_tool(self, name: str, arguments: dict | None = None):
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unknown MCP tool: {name}")
        result = tool.fn(**(arguments or {}))
        if inspect.isawaitable(result):
            result = await result
        return result

    def run(self, *args, **kwargs):
        raise RuntimeError("FastMCP is required for MCP transports; fallback is test-only")


def _make_server():
    if not _FASTMCP_AVAILABLE:
        extra = " with vc_mcp available" if _VC_MCP_AVAILABLE else ""
        logger.warning("[VECTOR][mcp] using in-process fallback MCP%s", extra)
        mcp_cls = _FallbackMCP
    else:
        mcp_cls = FastMCP

    mcp = mcp_cls(
        "VECTOR",
        instructions=(
            "You are connected to VECTOR — a Darwinian multi-agent AI system "
            "running on Arghyadeep's Legion Pro 5. "
            "Use these tools to access VECTOR's memory, research, goals, and districts."
        ),
    )

    # Marketing CLI tools

    _add_builtin_tools(mcp)

    _add_expansion_tools(mcp)
    _add_claims_tools(mcp)
    _add_guidance_tools(mcp)
    _add_kanban_tools(mcp)
    _add_email_tools(mcp)
    _add_research_tools(mcp)
    _add_collections_tools(mcp)
    _add_voice_profile_tools(mcp)
    _add_browser_tools(mcp)
    _add_knowledge_tools(mcp)
    _add_code_graph_tools(mcp)
    _add_brain_vault_tools(mcp)
    _add_db_control_tools(mcp)
    return mcp


# Public alias required by tests and VectorCode MCP client
create_mcp_app = _make_server
create_mcp_server = _make_server


# Backwards-compatible private names imported by existing tests and tools.
_add_collections_tools = _add_collections_tools
_add_voice_profile_tools = _add_voice_profile_tools
_add_browser_tools = _add_browser_tools
_add_knowledge_tools = _add_knowledge_tools
_add_claims_tools = _add_claims_tools
_add_guidance_tools = _add_guidance_tools
_add_kanban_tools = _add_kanban_tools
_add_email_tools = _add_email_tools
_add_research_tools = _add_research_tools
_add_brain_vault_tools = _add_brain_vault_tools




def main():
    if not _FASTMCP_AVAILABLE:
        logger.critical("[VECTOR][mcp] fastmcp not installed. Install: pip install fastmcp")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="VECTOR MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if args.transport == "sse" and args.host not in ("127.0.0.1", "::1", "localhost"):
        # FLAG FOR OWNER (Phase 3 audit, 2026-10-02): this warning used to tell
        # the operator to "Set VECTOR_MCP_API_KEY env var for auth" -- but
        # nothing in this codebase ever reads that env var (confirmed via
        # repo-wide grep: zero references outside this one message). Setting
        # it had zero actual effect -- an operator who did so on a trusted
        # tip would believe the SSE transport is now authenticated when it
        # is exactly as open as before. Removed the false claim; this
        # server genuinely has no SSE auth mechanism today, same class as
        # the already-documented "UNGATED tools" gap below (Task 60).
        # Adding real auth is a design decision (what scheme, where enforced
        # in fastmcp's request path), not a narrow patch -- not done here.
        logger.warning(f"[VECTOR][mcp] SSE binding to {args.host} — NOT localhost! "
                       "This server has no SSE authentication mechanism today. "
                       "Use 127.0.0.1 unless you have added your own auth in front of it.")

    # P0-D (M1c/M1d, 2026-09-09): this is unconditional and unmissable by design,
    # not gated on transport/host. Task 60's own dedicated red-team audit already
    # established this server exposes 14+ tools -- including db_quarantine, email
    # deletion, and browser actions -- with NO PermissionGateway enforcement and a
    # fail-open security wrapper (VECTOR_TECHNICAL_KNOWLEDGE/60_FINAL_PRE_EXPERIMENT_
    # AUTONOMOUS_SIDE_EFFECT_RED_TEAM.md). This is a pre-existing, known, deliberately
    # out-of-scope-for-remediation gap (Task 60 classified it "Class A / user-only",
    # not reachable from the autonomous loop) -- this warning does not weaken or
    # redesign any capability, it only makes the risk unmissable to whoever is about
    # to actually start serving, since M1c's own audit found this reachable from a
    # routine "does this file still work" developer invocation with no prior warning
    # at all. See VECTOR_TECHNICAL_KNOWLEDGE/M1c_DEVELOPMENT_TEST_ISOLATION_SAFETY_
    # AUDIT.md (finding P0-D) for the full history.
    logger.warning(
        "[VECTOR][mcp] Starting MCP server with UNGATED tools (no PermissionGateway "
        "enforcement) -- includes db_quarantine, email deletion, and browser actions. "
        "Only connect trusted clients. See Task 60's own red-team finding for the full "
        "scope of this known, pre-existing gap."
    )

    mcp = _make_server()
    logger.info(f"[VECTOR][mcp] starting transport={args.transport}")

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run()  # stdio — default for Claude Code integration


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # Real production entry point ("Run: python core/mcp_server.py
    # --transport sse --port 9000" per this file's own docstring): if
    # server-dispatch args are present, actually serve -- main() parses
    # them and calls mcp.run(), which blocks. This was a real bug found
    # 2026-06-24: this block previously ALWAYS ran the bare scaffold
    # self-test below regardless of args, so the server printed a banner
    # and exited with rc=0 immediately, every time, never actually serving
    # a single request.
    _server_args = {"--transport", "--port", "--host"}
    if _server_args & set(sys.argv[1:]):
        main()
    elif not _FASTMCP_AVAILABLE:
        print("⚠️  fastmcp not installed — install with: pip install fastmcp")
        print("   Verifying server scaffold only...")
        print("✅ mcp_server.py scaffold OK (fastmcp not installed)")
    else:
        mcp = _make_server()
        tools = [t for t in dir(mcp) if not t.startswith("_")]
        print(f"✅ mcp_server.py OK — {mcp.name} server built")
        print("   Tools exposed: recall_memory, store_memory, get_world_state, get_goals,")
        print("                  search_web, mine_reddit, read_paper, convene_council,")
        print("                  review_code, git_status, karpathy_session, karpathy_streak,")
        print("                  write_note, search_vault")
        print("   Resource: vector://status")
        print("   Run: python core/mcp_server.py              (stdio for Claude Code)")
        print("   Run: python core/mcp_server.py --transport sse --port 9000")
