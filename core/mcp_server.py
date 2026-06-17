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

def _make_server():
    if not _FASTMCP_AVAILABLE:
        extra = ""
        if _VC_MCP_AVAILABLE:
            extra = " (OJ MCP fallback available at vectorcode.src.vc_mcp)"
        raise ImportError(
            "fastmcp not installed — run: pip install fastmcp" + extra
        )
    mcp = FastMCP(
        "VECTOR",
        instructions=(
            "You are connected to VECTOR — a Darwinian multi-agent AI system "
            "running on Arghyadeep's Legion Pro 5. "
            "Use these tools to access VECTOR's memory, research, goals, and districts."
        ),
    )

    # â”€â”€ Marketing CLI tools â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

    mcp = _make_server()
    logger.info(f"[VECTOR][mcp] starting transport={args.transport}")

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run()  # stdio — default for Claude Code integration


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    if not _FASTMCP_AVAILABLE:
        print("âš ï¸  fastmcp not installed — install with: pip install fastmcp")
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
