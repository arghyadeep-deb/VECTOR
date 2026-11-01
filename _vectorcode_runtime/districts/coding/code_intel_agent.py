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

import asyncio
import subprocess
import json
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat

_CODEBASE_ROOT = Path(__file__).resolve().parents[2]  # districts/coding/x.py -> repo root (was one level too high: it pointed at the parent of the repo, so the built server was never found)
_DIST = _CODEBASE_ROOT / "vectorcode" / "code_intel" / "dist" / "index.js"

def _mcp_env() -> dict:
    """Environment for the code-intelligence MCP server, using the variable names it actually reads (src/constants.ts,
    src/services/embedding-config.ts). The old names (VECTORCODE_QDRANT_MODE, VECTORCODE_OLLAMA_MODE, ...) were never
    read, so the server always fell back to "managed" mode and demanded Docker."""
    import os

    ci = CONFIG.get("code_intel", {})
    return {
        **os.environ,
        "EMBEDDING_PROVIDER": ci.get("embedding_provider", "ollama"),
        "EMBEDDING_MODEL": ci.get("embedding_model", "nomic-embed-text"),
        "OLLAMA_MODE": "external",
        "OLLAMA_URL": ci.get("ollama_url", "http://127.0.0.1:11434"),
        "QDRANT_MODE": "external",
        "QDRANT_URL": ci.get("qdrant_url", "http://127.0.0.1:6333"),
    }


class _McpSession:
    """One long-lived VectorCode Intelligence MCP server process, shared by every call.

    It has to stay alive: vc_index, vc_update and vc_graph_build return immediately ("indexing started in the background")
    and keep working INSIDE the server process. The first version spawned a fresh server per call and closed it right
    after, which killed every index job the moment it was started (found by indexing a two-file project: vc_status then
    found nothing). Requests are serialized; the process is restarted if it dies and closed at interpreter exit."""

    def __init__(self) -> None:
        import queue
        import threading

        self._lock = threading.RLock()
        self._proc: subprocess.Popen | None = None
        self._lines: "queue.Queue[str | None]" = queue.Queue()
        self._next_id = 100

    # -- process management -------------------------------------------------------------------------------------------
    def _start(self) -> str | None:
        """Spawn + handshake. Returns an error string, or None when ready."""
        import queue
        import threading
        import time

        try:
            self._proc = subprocess.Popen(
                ["node", str(_DIST)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=_mcp_env(), cwd=str(_CODEBASE_ROOT), text=True, encoding="utf-8", errors="replace",
            )
        except FileNotFoundError:
            self._proc = None
            return "NODE_MISSING"
        except Exception as e:
            self._proc = None
            return str(e)
        self._lines = queue.Queue()
        proc, lines = self._proc, self._lines

        def _pump() -> None:
            for line in proc.stdout:  # type: ignore[union-attr]
                lines.put(line)
            lines.put(None)

        threading.Thread(target=_pump, daemon=True, name="code-intel-mcp-reader").start()
        rid = self._new_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "vector-code-intel-agent", "version": "1"}}})
        if self._reply(rid, time.time() + 30) is None:
            self.close()
            return "the code-intelligence server did not answer the MCP handshake"
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return None

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.stdin.close()  # type: ignore[union-attr]
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _send(self, obj: dict) -> None:
        self._proc.stdin.write(json.dumps(obj) + "\n")  # type: ignore[union-attr]
        self._proc.stdin.flush()  # type: ignore[union-attr]

    def _reply(self, msg_id: int, deadline: float) -> dict | None:
        import queue
        import time

        while time.time() < deadline:
            try:
                line = self._lines.get(timeout=max(0.1, min(1.0, deadline - time.time())))
            except queue.Empty:
                continue
            if line is None:
                return None
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == msg_id:
                return msg
        return None

    # -- public -------------------------------------------------------------------------------------------------------
    def call(self, tool_name: str, args: dict, timeout: int) -> dict:
        import time

        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                err = self._start()
                if err == "NODE_MISSING":
                    return {"error": "Node.js is not installed or not on PATH -- code intelligence cannot run",
                            "unavailable": True}
                if err:
                    return {"error": err}
            try:
                rid = self._new_id()
                self._send({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                            "params": {"name": tool_name, "arguments": args}})
                msg = self._reply(rid, time.time() + timeout)
            except Exception as e:
                self.close()
                return {"error": str(e)}
            if msg is None:
                if self._proc is not None and self._proc.poll() is not None:
                    self._proc = None
                    return {"error": f"the code-intelligence server exited during {tool_name}"}
                return {"error": f"MCP call {tool_name} timed out after {timeout}s"}
            if "error" in msg:
                return {"error": str((msg["error"] or {}).get("message", msg["error"]))}
            result = msg.get("result", {})
            text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text").strip()
            if result.get("isError"):
                low = text.lower()
                unavailable = "could not connect to qdrant" in low or "docker is required" in low
                if unavailable and "start_code_intel" not in low:
                    text = (text + " Start the local Qdrant with scripts/start_code_intel.bat.").strip()
                return {"error": text or "tool reported an error", **({"unavailable": True} if unavailable else {})}
            return {"text": text}


import atexit as _atexit
import time  # noqa: E402  (used by _McpSession)

_SESSION = _McpSession()
_atexit.register(_SESSION.close)


def _mcp_call(tool_name: str, args: dict, timeout: int = 60) -> dict:
    """Call one VectorCode Intelligence MCP tool through the shared server session.

    Returns {"text": <tool output>} on success or {"error": ...} (plus "unavailable": True when the tool is simply not
    installed/running, which must not be held against an agent)."""
    if not _DIST.exists():
        return {"error": "vectorcode-intel is not built yet. Run: cd vectorcode/code_intel && npm install && npm run build "
                         "(it also needs Node, a local Qdrant -- scripts\\start_code_intel.bat -- and an embedding model)",
                "unavailable": True}
    # The server validates arguments with a strict schema: an optional string must be OMITTED, not sent as null (the agent
    # passed file_filter=None, language=None, ... and every search/index call was rejected with "Expected string, received
    # null"). Drop None-valued arguments.
    args = {k: v for k, v in (args or {}).items() if v is not None}
    # extraExtensions is ONE comma-separated string in the server's schema; the agent sends a list ("Expected string,
    # received array"). An empty list means "none": omit it.
    ext = args.get("extraExtensions")
    if isinstance(ext, (list, tuple, set)):
        joined = ",".join(str(e).strip() for e in ext if str(e).strip())
        if joined:
            args["extraExtensions"] = joined
        else:
            args.pop("extraExtensions")
    return _SESSION.call(tool_name, args, timeout)


async def _amcp(tool_name: str, args: dict, timeout: int = 60) -> dict:
    """_mcp_call off the event loop (a call can take minutes; it used to freeze the loop for the whole time)."""
    return await asyncio.to_thread(_mcp_call, tool_name, args, timeout)


class CodeIntelAgent(AgentBase):
    """
    VectorCode Intelligence — semantic codebase understanding for VECTOR.
    Enables blast radius analysis, dependency graphs, and semantic code search.
    """

    def __init__(self):
        super().__init__(agent_id="code_intel_001", name="CodeIntelAgent", district="coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = [
            "vc_search", "code_search", "semantic_search",
            "vc_index", "code_index", "index_codebase",
            "vc_update",
            "vc_graph", "vc_graph_build", "dependency_graph", "code_graph",
            "vc_graph_query", "vc_graph_circular",
            "vc_impact", "blast_radius", "impact_analysis",
            "vc_flow", "call_flow", "execution_flow",
            "vc_symbol", "symbol_lookup", "find_symbol", "vc_symbols",
            "vc_watch", "codebase_watch",
            "vc_context", "code_context", "context_artifacts", "vc_context_search",
            "vc_visualize", "vc_graph_visualize",
            "vc_status", "code_status",
            "vc_health", "code_health", "codebase_health",
            "vc_projects", "code_projects",
        ]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        self._project_path = str(_CODEBASE_ROOT)
        logger.info("[VECTOR][code_intel] initialized")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _remember(self, event_type: str, content: str, tags: list, context: dict) -> None:
        """Best-effort episodic note about a query. It called store(content=..., metadata=...), but the real signature is
        store(event_type, content, tags, context, source): every successful search/impact query raised a TypeError and came
        back as an error. Logging a query must never break the query."""
        try:
            self._get_memory().store(event_type, content, tags=tags, context=context, source="code_intel")
        except Exception as exc:
            logger.debug("[VECTOR][code_intel] episodic note skipped: {}", exc)

    def _check_mcp_result(self, result: dict, task_type: str, hp: int, reason: str) -> dict | None:
        """If result contains an error key, deduct HP and return an error response.
        Returns None when result is clean (caller should proceed to award HP)."""
        if result.get("unavailable"):
            # The tool is simply not installed. That is not the agent's failure, so it must not cost HP
            # (each call used to take 30 HP off CodeIntelAgent until it died over missing infrastructure).
            return {"status": "unavailable", "type": task_type, "error": result["error"]}
        if result.get("error"):
            self.deduct_points(30, f"{task_type}_mcp_error")
            return {"status": "error", "type": task_type, "error": result["error"]}
        return None

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "vc_search")
        params = task.get("params", {})
        project_path = params.get("project_path", self._project_path)

        try:
            # ── Semantic search ───────────────────────────────────────────────
            if task_type in ("vc_search", "code_search", "semantic_search"):
                query = params.get("query", "")
                result = await _amcp("vc_search", {
                    "query": query,
                    "projectPath": project_path,
                    "limit": params.get("limit", 10),
                    "fileFilter": params.get("file_filter"),
                    "languageFilter": params.get("language"),
                    "minScore": params.get("min_score", 0.0),
                })
                if err := self._check_mcp_result(result, task_type, 15, "code_search_done"):
                    return err
                self.award_points(15, "code_search_done")
                self._remember("code_intel_search", f"Code search: {query}", ["coding", "code_intelligence", "search"],
                               {"query": query})
                return {"status": "ok", "type": task_type, "results": result}

            # ── Index codebase ────────────────────────────────────────────────
            elif task_type in ("vc_index", "code_index", "index_codebase"):
                result = await _amcp("vc_index", {
                    "projectPath": project_path,
                    "extraExtensions": params.get("extra_extensions", []),
                }, timeout=300)
                if err := self._check_mcp_result(result, task_type, 30, "codebase_indexed"):
                    return err
                self.award_points(30, "codebase_indexed")
                return {"status": "ok", "type": task_type, "result": result}

            # ── Incremental update ────────────────────────────────────────────
            elif task_type == "vc_update":
                result = await _amcp("vc_update", {"projectPath": project_path}, timeout=120)
                if err := self._check_mcp_result(result, task_type, 20, "codebase_updated"):
                    return err
                self.award_points(20, "codebase_updated")
                return {"status": "ok", "type": task_type, "result": result}

            # ── Dependency graph ──────────────────────────────────────────────
            elif task_type in ("vc_graph", "vc_graph_build", "dependency_graph", "code_graph"):
                result = await _amcp("vc_graph_build", {
                    "projectPath": project_path,
                    "extraExtensions": params.get("extra_extensions", []),
                }, timeout=180)
                if err := self._check_mcp_result(result, task_type, 25, "dependency_graph_built"):
                    return err
                self.award_points(25, "dependency_graph_built")
                return {"status": "ok", "type": task_type, "result": result}

            elif task_type == "vc_graph_query":
                result = await _amcp("vc_graph_query", {
                    "projectPath": project_path,
                    "filePath": params.get("file_path", ""),
                })
                if err := self._check_mcp_result(result, task_type, 15, "graph_query_done"):
                    return err
                self.award_points(15, "graph_query_done")
                return {"status": "ok", "type": task_type, "result": result}

            elif task_type == "vc_graph_circular":
                result = await _amcp("vc_graph_circular", {"projectPath": project_path})
                if err := self._check_mcp_result(result, task_type, 15, "circular_deps_checked"):
                    return err
                self.award_points(15, "circular_deps_checked")
                return {"status": "ok", "type": task_type, "circular_deps": result}

            # ── Impact analysis ───────────────────────────────────────────────
            elif task_type in ("vc_impact", "blast_radius", "impact_analysis"):
                result = await _amcp("vc_impact", {
                    "projectPath": project_path,
                    "target": params.get("target", ""),
                    "depth": params.get("depth", 3),
                })
                if err := self._check_mcp_result(result, task_type, 25, "impact_analysis_done"):
                    return err
                self.award_points(25, "impact_analysis_done")
                self._remember("code_intel_impact", f"Impact analysis: {params.get('target', '')}",
                               ["coding", "code_intelligence", "impact"], {"target": params.get("target")})
                return {"status": "ok", "type": task_type, "impact": result}

            # ── Call flow ─────────────────────────────────────────────────────
            elif task_type in ("vc_flow", "call_flow", "execution_flow"):
                result = await _amcp("vc_flow", {
                    "projectPath": project_path,
                    "entrypoint": params.get("entrypoint", ""),
                    "file": params.get("file"),
                    "depth": params.get("depth", 5),
                })
                if err := self._check_mcp_result(result, task_type, 20, "call_flow_traced"):
                    return err
                self.award_points(20, "call_flow_traced")
                return {"status": "ok", "type": task_type, "flow": result}

            # ── Symbol lookup ─────────────────────────────────────────────────
            elif task_type in ("vc_symbol", "symbol_lookup", "find_symbol"):
                result = await _amcp("vc_symbol", {
                    "projectPath": project_path,
                    "name": params.get("name", ""),
                    "file": params.get("file"),
                })
                if err := self._check_mcp_result(result, task_type, 15, "symbol_lookup_done"):
                    return err
                self.award_points(15, "symbol_lookup_done")
                return {"status": "ok", "type": task_type, "symbol": result}

            elif task_type == "vc_symbols":
                result = await _amcp("vc_symbols", {
                    "projectPath": project_path,
                    "file": params.get("file"),
                    "query": params.get("query"),
                    "limit": params.get("limit", 20),
                })
                if err := self._check_mcp_result(result, task_type, 15, "symbols_listed"):
                    return err
                self.award_points(15, "symbols_listed")
                return {"status": "ok", "type": task_type, "symbols": result}

            # ── File watcher ──────────────────────────────────────────────────
            elif task_type in ("vc_watch", "codebase_watch"):
                action = params.get("action", "start")
                result = await _amcp("vc_watch", {
                    "projectPath": project_path,
                    "action": action,
                })
                if err := self._check_mcp_result(result, task_type, 10, "watcher_configured"):
                    return err
                self.award_points(10, "watcher_configured")
                return {"status": "ok", "type": task_type, "watcher": result}

            # ── Context artifacts ─────────────────────────────────────────────
            elif task_type in ("vc_context", "code_context", "context_artifacts"):
                result = await _amcp("vc_context", {"projectPath": project_path})
                if err := self._check_mcp_result(result, task_type, 10, "context_artifacts_listed"):
                    return err
                self.award_points(10, "context_artifacts_listed")
                return {"status": "ok", "type": task_type, "artifacts": result}

            elif task_type == "vc_context_search":
                result = await _amcp("vc_context_search", {
                    "query": params.get("query", ""),
                    "projectPath": project_path,
                    "limit": params.get("limit", 5),
                })
                if err := self._check_mcp_result(result, task_type, 15, "context_search_done"):
                    return err
                self.award_points(15, "context_search_done")
                return {"status": "ok", "type": task_type, "results": result}

            # ── Graph visualization ───────────────────────────────────────────
            elif task_type in ("vc_visualize", "vc_graph_visualize"):
                result = await _amcp("vc_graph_visualize", {
                    "projectPath": project_path,
                    "mode": params.get("mode", "html"),
                    "open": params.get("open", False),
                })
                if err := self._check_mcp_result(result, task_type, 20, "graph_visualized"):
                    return err
                self.award_points(20, "graph_visualized")
                return {"status": "ok", "type": task_type, "visualization": result}

            # ── Status & health (read-only — no HP involved) ──────────────────
            elif task_type in ("vc_status", "code_status"):
                result = await _amcp("vc_status", {"projectPath": project_path})
                if err := self._check_mcp_result(result, task_type, 0, ""):
                    return err
                return {"status": "ok", "type": task_type, "index_status": result}

            elif task_type in ("vc_health", "code_health", "codebase_health"):
                result = await _amcp("vc_health", {})
                if err := self._check_mcp_result(result, task_type, 0, ""):
                    return err
                return {"status": "ok", "type": task_type, "health": result}

            elif task_type in ("vc_projects", "code_projects"):
                result = await _amcp("vc_projects", {})
                if err := self._check_mcp_result(result, task_type, 0, ""):
                    return err
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
