"""
Code Intelligence Agent — semantic codebase search, dependency graphs, impact analysis.

Wraps the VectorCode Intelligence MCP server (vectorcode/code_intel/) which provides:
- vc_search     : Hybrid semantic + BM25 search across any codebase
- vc_index      : Resumable batch indexing with file hash tracking
- vc_graph_*    : File-level dependency graph (18 languages, AST-based)
- vc_impact     : Blast radius — what breaks if I change function X?
- vc_flow       : Execution call flow tracing from entry points
- vc_symbol*    : Symbol lookup, 360 degree symbol view
- vc_watch      : Auto-updating file watcher (native OS level)
- vc_context*   : Searchable non-code knowledge (schemas, API specs, docs)
- vc_health     : Infrastructure health (Qdrant, Ollama, Docker)
- vc_visualize  : Interactive dependency graph (Cytoscape.js, offline)
"""

import sys
import asyncio
import subprocess
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat

_CODEBASE_ROOT = Path(__file__).parent.parent.parent.parent
_DIST = _CODEBASE_ROOT / "vectorcode" / "code_intel" / "dist" / "index.js"


def _mcp_call(tool_name: str, args: dict, timeout: int = 60) -> dict:
    """
    Call a VectorCode Intelligence MCP tool via JSON-RPC over stdio.
    Returns parsed result or error dict.
    """
    if not _DIST.exists():
        return {"error": f"vectorcode-intel not built yet. Run: cd vectorcode/code_intel && npm install && npm run build"}

    request = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": args}
    })
    try:
        env = {
            "EMBEDDING_PROVIDER": CONFIG.get("code_intel", {}).get("embedding_provider", "ollama"),
            "VECTORCODE_OLLAMA_MODE": "external",
            "VECTORCODE_OLLAMA_URL": CONFIG.get("code_intel", {}).get("ollama_url", "http://127.0.0.1:11434"),
            "VECTORCODE_QDRANT_MODE": "external",
            "VECTORCODE_QDRANT_URL": CONFIG.get("code_intel", {}).get("qdrant_url", "http://127.0.0.1:6333"),
        }
        import os
        full_env = {**os.environ, **env}
        result = subprocess.run(
            ["node", str(_DIST)],
            input=request,
            capture_output=True, text=True,
            timeout=timeout,
            env=full_env,
            cwd=str(_CODEBASE_ROOT),
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip() or "MCP call failed"}
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("{"):
                parsed = json.loads(line)
                if "result" in parsed:
                    return parsed["result"]
                if "error" in parsed:
                    return {"error": parsed["error"]}
        return {"output": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"error": f"MCP call timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


class CodeIntelAgent(AgentBase):
    """
    VectorCode Intelligence — semantic codebase understanding for VECTOR.
    Enables blast radius analysis, dependency graphs, and semantic code search.
    """

    def __init__(self):
        super().__init__(agent_id="code_intel_001", name="CodeIntelAgent", district="coding")
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        self._project_path = str(_CODEBASE_ROOT)
        logger.info("[VECTOR][code_intel] initialized")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "vc_search")
        params = task.get("params", {})
        project_path = params.get("project_path", self._project_path)

        try:
            # ── Semantic search ───────────────────────────────────────────────
            if task_type in ("vc_search", "code_search", "semantic_search"):
                query = params.get("query", "")
                result = _mcp_call("vc_search", {
                    "query": query,
                    "projectPath": project_path,
                    "limit": params.get("limit", 10),
                    "fileFilter": params.get("file_filter"),
                    "languageFilter": params.get("language"),
                    "minScore": params.get("min_score", 0.0),
                })
                self.award_points(15, "code_search_done")
                self._get_memory().store(
                    content=f"Code search: {query}",
                    tags=["coding", "code_intelligence", "search"],
                    metadata={"query": query}
                )
                return {"status": "ok", "type": task_type, "results": result}

            # ── Index codebase ────────────────────────────────────────────────
            elif task_type in ("vc_index", "code_index", "index_codebase"):
                result = _mcp_call("vc_index", {
                    "projectPath": project_path,
                    "extraExtensions": params.get("extra_extensions", []),
                }, timeout=300)
                self.award_points(30, "codebase_indexed")
                return {"status": "ok", "type": task_type, "result": result}

            # ── Incremental update ────────────────────────────────────────────
            elif task_type == "vc_update":
                result = _mcp_call("vc_update", {"projectPath": project_path}, timeout=120)
                self.award_points(20, "codebase_updated")
                return {"status": "ok", "type": task_type, "result": result}

            # ── Dependency graph ──────────────────────────────────────────────
            elif task_type in ("vc_graph", "vc_graph_build", "dependency_graph", "code_graph"):
                result = _mcp_call("vc_graph_build", {
                    "projectPath": project_path,
                    "extraExtensions": params.get("extra_extensions", []),
                }, timeout=180)
                self.award_points(25, "dependency_graph_built")
                return {"status": "ok", "type": task_type, "result": result}

            elif task_type == "vc_graph_query":
                result = _mcp_call("vc_graph_query", {
                    "projectPath": project_path,
                    "filePath": params.get("file_path", ""),
                })
                self.award_points(15, "graph_query_done")
                return {"status": "ok", "type": task_type, "result": result}

            elif task_type == "vc_graph_circular":
                result = _mcp_call("vc_graph_circular", {"projectPath": project_path})
                self.award_points(15, "circular_deps_checked")
                return {"status": "ok", "type": task_type, "circular_deps": result}

            # ── Impact analysis ───────────────────────────────────────────────
            elif task_type in ("vc_impact", "blast_radius", "impact_analysis"):
                result = _mcp_call("vc_impact", {
                    "projectPath": project_path,
                    "target": params.get("target", ""),
                    "depth": params.get("depth", 3),
                })
                self.award_points(25, "impact_analysis_done")
                self._get_memory().store(
                    content=f"Impact analysis: {params.get('target', '')}",
                    tags=["coding", "code_intelligence", "impact"],
                    metadata={"target": params.get("target")}
                )
                return {"status": "ok", "type": task_type, "impact": result}

            # ── Call flow ─────────────────────────────────────────────────────
            elif task_type in ("vc_flow", "call_flow", "execution_flow"):
                result = _mcp_call("vc_flow", {
                    "projectPath": project_path,
                    "entrypoint": params.get("entrypoint", ""),
                    "file": params.get("file"),
                    "depth": params.get("depth", 5),
                })
                self.award_points(20, "call_flow_traced")
                return {"status": "ok", "type": task_type, "flow": result}

            # ── Symbol lookup ─────────────────────────────────────────────────
            elif task_type in ("vc_symbol", "symbol_lookup", "find_symbol"):
                result = _mcp_call("vc_symbol", {
                    "projectPath": project_path,
                    "name": params.get("name", ""),
                    "file": params.get("file"),
                })
                self.award_points(15, "symbol_lookup_done")
                return {"status": "ok", "type": task_type, "symbol": result}

            elif task_type == "vc_symbols":
                result = _mcp_call("vc_symbols", {
                    "projectPath": project_path,
                    "file": params.get("file"),
                    "query": params.get("query"),
                    "limit": params.get("limit", 20),
                })
                self.award_points(15, "symbols_listed")
                return {"status": "ok", "type": task_type, "symbols": result}

            # ── File watcher ──────────────────────────────────────────────────
            elif task_type in ("vc_watch", "codebase_watch"):
                action = params.get("action", "start")
                result = _mcp_call("vc_watch", {
                    "projectPath": project_path,
                    "action": action,
                })
                self.award_points(10, "watcher_configured")
                return {"status": "ok", "type": task_type, "watcher": result}

            # ── Context artifacts ─────────────────────────────────────────────
            elif task_type in ("vc_context", "code_context", "context_artifacts"):
                result = _mcp_call("vc_context", {"projectPath": project_path})
                self.award_points(10, "context_artifacts_listed")
                return {"status": "ok", "type": task_type, "artifacts": result}

            elif task_type == "vc_context_search":
                result = _mcp_call("vc_context_search", {
                    "query": params.get("query", ""),
                    "projectPath": project_path,
                    "limit": params.get("limit", 5),
                })
                self.award_points(15, "context_search_done")
                return {"status": "ok", "type": task_type, "results": result}

            # ── Graph visualization ───────────────────────────────────────────
            elif task_type in ("vc_visualize", "vc_graph_visualize"):
                result = _mcp_call("vc_graph_visualize", {
                    "projectPath": project_path,
                    "mode": params.get("mode", "html"),
                    "open": params.get("open", False),
                })
                self.award_points(20, "graph_visualized")
                return {"status": "ok", "type": task_type, "visualization": result}

            # ── Status & health ───────────────────────────────────────────────
            elif task_type in ("vc_status", "code_status"):
                result = _mcp_call("vc_status", {"projectPath": project_path})
                return {"status": "ok", "type": task_type, "index_status": result}

            elif task_type in ("vc_health", "code_health", "codebase_health"):
                result = _mcp_call("vc_health", {})
                return {"status": "ok", "type": task_type, "health": result}

            elif task_type in ("vc_projects", "code_projects"):
                result = _mcp_call("vc_projects", {})
                return {"status": "ok", "type": task_type, "projects": result}

            else:
                return {"status": "error", "error": f"Unknown code_intel task type: {task_type}"}

        except Exception as e:
            logger.error(f"[VECTOR][code_intel] {task_type} failed: {e}")
            self.deduct_points(30, f"code_intel_{task_type}_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    async def _test():
        agent = CodeIntelAgent()
        # Test: check if MCP server is built
        built = _DIST.exists()
        result = await agent.run({
            "type": "vc_health",
            "params": {}
        })
        print("OK: CodeIntelAgent initialized" if result.get("status") in ("ok", "error") else "FAILED")
        print(f"  MCP built: {built}")
        print(f"  Health result: {result.get('health', result.get('error', 'unknown'))}")

    asyncio.run(_test())
