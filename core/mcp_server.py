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
    "main",
]

import asyncio
import argparse
from pathlib import Path


from loguru import logger
from core.mcp_tools.code_graph import add_code_graph_tools as _add_code_graph_tools
from core.mcp_tools.error_handling import (
    mcp_call_json as _mcp_call_json,
    safe_json as _safe_json,
    register_stub_tool as _reg,
)
from core.mcp_tools.expansion import add_expansion_tools as _add_expansion_tools
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    MEMORY_EXPORT_DIRNAME as _MEMORY_EXPORT_DIRNAME,
    memory_export_dir as _memory_export_dir,
    resolve_memory_path as _resolve_memory_path,
)
from core.mcp_tools.security import mcp_secure_call as _mcp_secure_call

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

from core.config import CONFIG


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

    @mcp.tool
    def marketing_cli(tool_name: str, input_data: str = "{}") -> str:
        """
        Run any of 60+ live marketing API CLI tools.
        tool_name: ga4 | google-ads | meta-ads | ahrefs | semrush | klaviyo | hubspot |
                   apollo | clearbit | g2 | exa | buffer | mailchimp | amplitude |
                   hotjar | optimizely | intercom | stripe | paddle | typeform | ...
        input_data: JSON string of tool-specific parameters
        Returns tool output or error message.
        """
        import subprocess
        import json as _json
        import re as _re
        if not _re.fullmatch(r"[a-zA-Z0-9_-]+", tool_name):
            return f"Invalid tool name '{tool_name}'. Only alphanumeric, hyphens, underscores allowed."
        if not _mcp_secure_call(tool_name, "marketing", {"input_data": input_data[:200]}):
            return f"Tool '{tool_name}' blocked by MCP security rate limit."
        cli_dir = Path(__file__).parent.parent / "districts" / "marketing" / "tools" / "clis"
        script = (cli_dir / f"{tool_name}.js").resolve()
        if not str(script).startswith(str(cli_dir.resolve())):
            return f"Access denied: tool path outside CLI directory."
        if not script.exists():
            available = sorted(f.stem for f in cli_dir.glob("*.js"))
            return f"Tool '{tool_name}' not found. Available ({len(available)}): {', '.join(available)}"
        try:
            parsed = _json.loads(input_data) if input_data else {}
            result = subprocess.run(
                ["node", str(script)],
                input=_json.dumps(parsed),
                capture_output=True, text=True, timeout=30,
                cwd=str(cli_dir),
            )
            out = result.stdout.strip() or result.stderr.strip() or "No output"
            logger.info(f"[VECTOR][mcp] marketing_cli {tool_name} → {len(out)} chars")
            return out
        except subprocess.TimeoutExpired:
            return f"CLI tool '{tool_name}' timed out after 30s"
        except Exception as e:
            return f"CLI error for '{tool_name}': {e}"

    @mcp.tool
    def list_marketing_tools() -> str:
        """List all available marketing CLI tools grouped by category."""
        cli_dir = Path(__file__).parent.parent / "districts" / "marketing" / "tools" / "clis"
        tools = sorted(f.stem for f in cli_dir.glob("*.js"))
        skills_dir = Path(__file__).parent.parent / "districts" / "marketing" / "skills"
        skills = sorted(d.name for d in skills_dir.iterdir() if d.is_dir())
        return (
            f"Marketing CLI tools ({len(tools)}): {', '.join(tools)}\n\n"
            f"Expert skill prompts ({len(skills)}): {', '.join(skills)}\n\n"
            "Use marketing_cli(tool_name, input_data) to call any CLI tool."
        )

    # â”€â”€ Intelligence tools (VectorIntel / Shadowbroker) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @mcp.tool
    async def intelligence_query(
        action: str,
        lat: float = 0.0,
        lon: float = 0.0,
        radius_km: int = 500,
        label: str = "",
    ) -> str:
        """
        Query VECTOR's real-time global intelligence platform (Shadowbroker).
        action: flights | vessels | satellites | cctv | sigint | conflicts | fires |
                outages | earthquakes | markets | correlations | search | near_me |
                news | report | summary | sar | satellite_image | geocode | pin |
                analysis_zone | infonet | alert | brief
        lat/lon: for near_me, news, pin, sar/near, satellite_image, brief
        label:   for place_pin  |  pass query param via label for search
        Requires VectorIntel server running: cd Shadowbroker-main && docker-compose up -d
        """
        from districts.intelligence.vectorintel_agent import VectorIntelAgent
        agent = VectorIntelAgent()
        if not agent._available:
            return "VectorIntel offline. Start: cd Shadowbroker-main && docker-compose up -d"
        task = {
            "type": action,
            "params": {"lat": lat, "lon": lon, "radius_km": radius_km, "label": label},
        }
        result = await agent.run(task)
        return result.get("message", str(result))

    # â”€â”€ Memory tools â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @mcp.tool
    def recall_memory(query: str, limit: int = 5) -> str:
        """Search VECTOR's episodic memory for past events and observations."""
        try:
            from core.memory.episodic import EpisodicMemory
            mem = EpisodicMemory()
            results = mem.recall(query, limit=limit)
            if not results:
                return "No memories found for that query."
            lines = [f"[{r.get('timestamp', '?')}] {r.get('content', '')}" for r in results]
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] recall_memory failed: {e}")
            return f"Memory recall failed: {e}"

    @mcp.tool
    def store_memory(content: str, event_type: str = "mcp_event", tags: str = "") -> str:
        """Store an event in VECTOR's episodic memory. tags: comma-separated string."""
        if not _mcp_secure_call("store_memory", "mcp_client", {"event_type": event_type}):
            return "store_memory blocked by MCP security rate limit."
        try:
            from core.memory.episodic import EpisodicMemory
            mem = EpisodicMemory()
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            mem.store(event_type=event_type, content=content, tags=tag_list, source="mcp")
            return f"Stored event '{event_type}' in episodic memory."
        except Exception as e:
            logger.error(f"[VECTOR][mcp] store_memory failed: {e}")
            return f"Memory store failed: {e}"

    # â”€â”€ World state / goals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @mcp.tool
    def get_world_state() -> str:
        """Get VECTOR's current world state: comms, health, active goals, time."""
        try:
            from core.loop.context_engine import ContextEngine
            ctx = ContextEngine()
            state = ctx.get_world_state()
            import json
            return json.dumps(state, indent=2, default=str)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] get_world_state failed: {e}")
            return f"World state unavailable: {e}"

    @mcp.tool
    def get_goals() -> str:
        """Get VECTOR's current goals across all three horizons (LONG/MID/SHORT)."""
        try:
            from core.brain.goal_system import GoalSystem
            gs = GoalSystem()
            actions = gs.generate_immediate_actions()
            import json
            return json.dumps(actions, indent=2, default=str)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] get_goals failed: {e}")
            return f"Goals unavailable: {e}"

    # â”€â”€ Research tools â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @mcp.tool
    async def search_web(query: str, max_results: int = 5) -> str:
        """Search the web for information using VECTOR's WebScout agent."""
        try:
            from districts.research.web_scout import WebScout
            scout = WebScout()
            result = await scout.search(query, max_results=max_results)
            return str(result)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] search_web failed: {e}")
            return f"Web search failed: {e}"

    @mcp.tool
    async def mine_reddit(subreddit: str = "LocalLLaMA", limit: int = 10) -> str:
        """Get hot posts from a subreddit via VECTOR's RedditMiner (no OAuth needed)."""
        try:
            from districts.research.reddit_miner import RedditMiner
            miner = RedditMiner()
            result = await miner.mine_subreddit(subreddit, limit=limit)
            import json
            return json.dumps(result, indent=2, default=str)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] mine_reddit failed: {e}")
            return f"Reddit mining failed: {e}"

    @mcp.tool
    async def read_paper(url: str) -> str:
        """Fetch and summarise an ArXiv paper or research URL using VECTOR's PaperReader."""
        try:
            from districts.research.paper_reader import PaperReader
            reader = PaperReader()
            result = await reader.read(url)
            return str(result)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] read_paper failed: {e}")
            return f"Paper reading failed: {e}"

    # â”€â”€ Governance tools â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @mcp.tool
    async def convene_council(question: str, stakes: str = "high") -> str:
        """
        Convene the VECTOR LLM Council for a high-stakes decision.
        stakes: 'high' or 'critical'. Requires 700+ HP gate. Max 10 sessions/week.
        """
        try:
            from districts.governance.llm_council import LLMCouncil
            council = LLMCouncil()
            result = await council.convene(question=question, stakes=stakes)
            verdict = result.get("verdict", "No verdict produced.")
            session_id = result.get("session_id", "?")
            return f"[Session {session_id}]\n{verdict}"
        except Exception as e:
            logger.error(f"[VECTOR][mcp] convene_council failed: {e}")
            return f"Council session failed: {e}"

    # â”€â”€ Coding tools â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @mcp.tool
    async def review_code(file_path: str) -> str:
        """Run VECTOR's CodeReviewer on a Python file and return the review report."""
        try:
            from districts.coding.code_reviewer import CodeReviewer
            reviewer = CodeReviewer()
            _root = Path(__file__).parent.parent.resolve()
            path = Path(file_path).resolve()
            if not str(path).startswith(str(_root)):
                return f"Access denied: '{file_path}' is outside the VECTOR codebase."
            if not path.exists():
                return f"File not found: {file_path}"
            result = await reviewer.review_file(str(path))
            return str(result)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] review_code failed: {e}")
            return f"Code review failed: {e}"

    @mcp.tool
    async def git_status() -> str:
        """Get the current git status of the VECTOR codebase."""
        try:
            from districts.coding.git_bot import GitBot
            bot = GitBot()
            result = await asyncio.to_thread(bot.get_status)
            return str(result)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] git_status failed: {e}")
            return f"Git status failed: {e}"

    # â”€â”€ Karpathy / training tools â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @mcp.tool
    def karpathy_session(topic: str, file_path: str = "") -> str:
        """
        Start a tracked 30-minute Karpathy typing session (RULE 12).
        topic: what you're typing today (e.g. 'bigram LM', 'attention forward pass').
        """
        try:
            from districts.karpathy_lab.code_typer import CodeTyper
            typer = CodeTyper()
            result = typer.start_session(topic=topic, file_path=file_path or None)
            return str(result)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] karpathy_session failed: {e}")
            return f"Karpathy session start failed: {e}"

    @mcp.tool
    def karpathy_streak() -> str:
        """Check current Karpathy daily coding streak (RULE 12: 30 min/day)."""
        try:
            from districts.karpathy_lab.code_typer import CodeTyper
            typer = CodeTyper()
            streak = typer.get_streak()
            today = typer.get_today_summary()
            return f"Streak: {streak} day(s)\nToday: {today}"
        except Exception as e:
            logger.error(f"[VECTOR][mcp] karpathy_streak failed: {e}")
            return f"Streak check failed: {e}"

    # â”€â”€ Obsidian tools â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @mcp.tool
    def write_note(title: str, content: str, folder: str = "Research", tags: str = "") -> str:
        """Write a note to the VECTOR Obsidian vault."""
        try:
            from core.memory.obsidian_sync import ObsidianSync
            sync = ObsidianSync()
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            sync.write_note(title=title, content=content, folder=folder, tags=tag_list)
            return f"Note '{title}' written to vault/{folder}/"
        except Exception as e:
            logger.error(f"[VECTOR][mcp] write_note failed: {e}")
            return f"Note write failed: {e}"

    @mcp.tool
    def search_vault(query: str, top_k: int = 5) -> str:
        """Search the VECTOR Obsidian vault via LightRAG semantic search."""
        try:
            from core.memory.obsidian_sync import ObsidianSync
            sync = ObsidianSync()
            results = sync.query(query, top_k=top_k)
            return str(results)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] search_vault failed: {e}")
            return f"Vault search failed: {e}"

    # â”€â”€ System resource â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @mcp.resource("vector://status")
    def vector_status() -> str:
        """Current VECTOR system status as a resource."""
        import json, datetime
        return json.dumps({
            "system": CONFIG["system_name"],
            "version": CONFIG["version"],
            "env": CONFIG["env"],
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "ollama_host": CONFIG["ollama_host"],
        }, indent=2)

    @mcp.tool
    def find_public_api(query: str, category: str = "", free_only: bool = True) -> str:
        """Search the public-apis catalog (1000+ free APIs) to find data sources for any topic."""
        try:
            from districts.research.api_catalog import search_apis, get_stats
            results = search_apis(query, category=category, free_only=free_only, limit=10)
            if not results:
                stats = get_stats()
                return f"No APIs found for '{query}'. Catalog has {stats['total']} total APIs."
            lines = [f"Found {len(results)} APIs for '{query}':"]
            for r in results:
                lines.append(f"• {r['name']} ({r['category']}): {r['description'][:80]}")
                if r.get("url"):
                    lines.append(f"  URL: {r['url']}")
            return "\n".join(lines)
        except Exception as e:
            return f"API catalog search failed: {e}"

    # â”€â”€ OpenMythos training tools â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @mcp.tool
    def openmythos_check() -> str:
        """Check if OpenMythos training environment is ready."""
        try:
            from core.training.openmythos.trainer import check_setup
            import json
            result = check_setup()
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"OpenMythos check failed: {e}"

    @mcp.tool
    def openmythos_export(min_reward: float = 0.7) -> str:
        """Export VECTOR's high-reward reasoning chains as OpenMythos training data."""
        try:
            from core.training.openmythos.trainer import export_training_data
            path = export_training_data(min_reward=min_reward)
            if path:
                return f"Exported training data to: {path}"
            return "No training data found. Run VECTOR longer to accumulate reasoning chains."
        except Exception as e:
            return f"Export failed: {e}"

    @mcp.tool
    def openmythos_train(epochs: int = 3) -> str:
        """
        Fine-tune OpenMythos 1B on VECTOR's reasoning chains to create vector-chairman.
        Requires: torch, peft, datasets. RTX 5070 Ti: ~1-2 hours.
        """
        try:
            from core.training.openmythos.trainer import export_training_data, train, create_modelfile
            data_path = export_training_data()
            if not data_path:
                return "No training data. Run VECTOR longer first."
            model_dir = train(data_path, epochs=epochs)
            if model_dir:
                modelfile = create_modelfile(model_dir)
                return (
                    f"Training complete!\n"
                    f"Model: {model_dir}\n"
                    f"To activate: ollama create vector-chairman -f {modelfile}"
                )
            return "Training failed. Check logs."
        except Exception as e:
            return f"Training failed: {e}"

    # ── ask_user_question — owner input during agent tasks ─────────────────────

    @mcp.tool
    async def ask_user_question(question: str, options: list[str] = None) -> str:
        """Ask the owner a structured question during an agent task. Options are selectable choices."""
        try:
            from core.loop.nudge_engine import NudgeEngine
            nudge = NudgeEngine()
            opts_str = "\n".join(f"{i+1}. {o}" for i, o in enumerate(options)) if options else ""
            message = f"❓ VECTOR needs input:\n{question}"
            if opts_str:
                message += f"\n\nOptions:\n{opts_str}"
            await nudge.push(message, priority=10)
            return f"Question sent to owner: {question}"
        except Exception as e:
            from loguru import logger
            logger.warning("[VECTOR][mcp] ask_user_question failed: {}", e)
            return f"Could not send question: {e}"

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




def _add_collections_tools(mcp) -> None:
    """Expose the VECTOR collections engine (PocketBase absorption) to MCP clients so
    VECTOR's own agents can store/query structured data. Reads + a gated create."""
    import json as _json
    try:
        from core.collections import CollectionEngine, FilterError, ValidationError
    except Exception as e:
        logger.warning(f"[VECTOR][mcp] collections tools unavailable: {e}")
        return

    _holder: dict = {}

    def _engine():
        if "eng" not in _holder:
            _holder["eng"] = CollectionEngine()   # shares the encrypted DB connection
        return _holder["eng"]

    @mcp.tool
    def collection_list() -> str:
        """List all VECTOR collections with their field summaries."""
        if not _mcp_secure_call("collection_list", "collections", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            out = [{"name": c.name, "type": c.type.value,
                    "fields": [{"name": f.name, "type": f.type.value} for f in c.fields]}
                   for c in _engine().list_collections()]
            return _safe_json({"collections": out})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def collection_query(name: str, filter: str = "", sort: str = "",
                         page: int = 1, per_page: int = 30) -> str:
        """Query records in a VECTOR collection. filter/sort use the PocketBase-style
        syntax, e.g. filter='views > 10 && title ~ "foo"', sort='-created'. The filter
        parser is parameterized — bad/unknown fields return an error, never raw SQL."""
        if not _mcp_secure_call("collection_query", "collections",
                                {"name": name, "filter": filter[:200]}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            return _safe_json(_engine().list_records(
                name, filter=filter or None, sort=sort or None,
                page=int(page), per_page=int(per_page)))
        except (FilterError, ValidationError) as e:
            return _safe_json({"error": str(e)})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def collection_record_create(name: str, data_json: str = "{}") -> str:
        """Create a record in a VECTOR collection. data_json is a JSON object string of
        the record fields. Returns the created record (passwords are never returned)."""
        if not _mcp_secure_call("collection_record_create", "collections", {"name": name}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            data = _json.loads(data_json) if data_json else {}
            if not isinstance(data, dict):
                return _safe_json({"error": "data_json must be a JSON object"})
            return _safe_json(_engine().create_record(name, data))
        except (FilterError, ValidationError) as e:
            return _safe_json({"error": str(e)})
        except Exception as e:
            return _safe_json({"error": str(e)})


def _add_voice_profile_tools(mcp) -> None:
    """Expose voice profile management to MCP clients (voicebox absorption)."""
    try:
        from core.voice.voice_profiles import get_profile_store  # noqa: F401
    except Exception as e:
        logger.warning(f"[VECTOR][mcp] voice profile tools unavailable: {e}")
        return

    @mcp.tool
    def list_voice_profiles() -> str:
        """List all stored VECTOR voice profiles (name, type, engine, is_default)."""
        if not _mcp_secure_call("list_voice_profiles", "voice", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            store = get_profile_store()
            return _safe_json({"profiles": [p.to_dict() for p in store.list_all()]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def speak_as(profile_name: str, text: str) -> str:
        """Speak `text` using the named voice profile (cloned local voice if available,
        otherwise the profile's configured engine). Returns status JSON."""
        if not _mcp_secure_call("speak_as", "voice", {"profile": profile_name}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            from core.voice.tts import VoiceTTS
            tts = VoiceTTS()
            tts.speak(text, profile_name=profile_name)
            return _safe_json({"status": "spoken", "profile": profile_name})
        except Exception as e:
            return _safe_json({"error": str(e)})


def _add_browser_tools(mcp) -> None:
    """Expose browser absorption tools (auto-browser-main) to MCP clients.
    3 tools: browser_prune_dom, browser_list_auth_profiles, browser_save_auth_profile."""
    try:
        from core.browser.dom_pruner import get_dom_pruner as _get_pruner
        from core.browser.auth_profiles import get_auth_store as _get_store
        from core.browser.pii_scrub import scrub_text as _scrub_text
    except Exception as e:
        logger.warning(f"[VECTOR][mcp] browser tools unavailable: {e}")
        return

    @mcp.tool
    def browser_prune_dom(elements_json: str, task_goal: str = "", max_elements: int = 20) -> str:
        """Prune a raw DOM interactable-element list to the top-N most relevant for task_goal.
        elements_json: JSON array of element dicts (from browser observe).
        Returns pruned JSON array — reduces ~18k token observations to ~500."""
        if not _mcp_secure_call("browser_prune_dom", "browser", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            import json as _json
            elements = _json.loads(elements_json)
            pruner = _get_pruner()
            pruned = pruner.prune(elements, task_goal=task_goal, max_elements=max_elements)
            return _safe_json({"pruned": pruned, "count": len(pruned), "original_count": len(elements)})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def browser_list_auth_profiles() -> str:
        """List all saved named browser auth profiles (login-once, reuse-later)."""
        if not _mcp_secure_call("browser_list_auth_profiles", "browser", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            return _safe_json({"profiles": _get_store().list()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def browser_save_auth_profile(profile_name: str, state_json: str) -> str:
        """Save a Playwright storage state (cookies + localStorage) under profile_name.
        state_json: JSON string from `await context.storage_state()`.
        Returns saved profile metadata."""
        if not _mcp_secure_call("browser_save_auth_profile", "browser", {"profile": profile_name}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            import json as _json
            state = _json.loads(state_json)
            return _safe_json(_get_store().save(profile_name, state))
        except Exception as e:
            return _safe_json({"error": str(e)})


def _add_knowledge_tools(mcp) -> None:
    """Expose the VECTOR knowledge layer (Understand-Anything absorption) to MCP clients.
    3 tools: knowledge_scan_domain, knowledge_parse_wiki, knowledge_merge_wiki."""
    try:
        from core.knowledge.domain_extractor import DomainExtractor as _DomainExtractor
        from core.knowledge.wiki_parser import WikiParser as _WikiParser
        from core.knowledge.wiki_merger import WikiMerger as _WikiMerger
    except Exception as e:
        logger.warning(f"[VECTOR][mcp] knowledge tools unavailable: {e}")
        return

    @mcp.tool
    def knowledge_scan_domain(project_path: str = "", output_filename: str = "") -> str:
        """Scan a project directory and extract domain context (entry points, file signatures, metadata).
        project_path: absolute path to project root (defaults to VECTOR codebase).
        output_filename: optional filename to write JSON output (e.g. 'my-project.json').
        Returns JSON with projectRoot, fileCount, entryPoints, fileSignatures, metadata."""
        if not _mcp_secure_call("knowledge_scan_domain", "knowledge", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            from pathlib import Path as _Path
            from core.config import CONFIG as _CONFIG
            root = _Path(project_path).resolve() if project_path else _Path(__file__).parent.parent
            if not root.is_dir():
                return _safe_json({"error": f"Not a directory: {root}"})
            output_path = None
            if output_filename:
                out_dir = _Path(_CONFIG["knowledge"]["output_dir"])
                out_dir.mkdir(parents=True, exist_ok=True)
                output_path = out_dir / _Path(output_filename).name
            extractor = _DomainExtractor()
            ctx = extractor.scan(root, output_path=output_path)
            result = ctx.to_dict()
            result["_outputPath"] = str(output_path) if output_path else None
            return _safe_json(result)
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def knowledge_parse_wiki(wiki_root: str = "") -> str:
        """Parse a Karpathy-format markdown wiki into a scan manifest (nodes, edges, categories).
        wiki_root: path to wiki directory (defaults to Obsidian brain vault).
        Writes scan-manifest.json to <wiki_root>/.understand-anything/intermediate/.
        Returns node_count, edge_count, category_count, and manifest_path."""
        if not _mcp_secure_call("knowledge_parse_wiki", "knowledge", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            import json as _json
            from pathlib import Path as _Path
            from core.config import CONFIG as _CONFIG
            root = _Path(wiki_root).resolve() if wiki_root else _Path(_CONFIG["knowledge"]["wiki_root"])
            if not root.is_dir():
                return _safe_json({"error": f"Wiki root not found: {root}"})
            parser = _WikiParser()
            out_path = parser.parse_to_file(root)
            manifest = _json.loads(out_path.read_text(encoding="utf-8"))
            return _safe_json({
                "wiki_root": str(root),
                "manifest_path": str(out_path),
                "node_count": len(manifest.get("nodes", [])),
                "edge_count": len(manifest.get("edges", [])),
                "category_count": len(manifest.get("categories", [])),
            })
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def knowledge_merge_wiki(wiki_root: str = "") -> str:
        """Merge a parsed wiki's scan manifest with any LLM analysis batches into an assembled graph.
        wiki_root: path to wiki directory (defaults to Obsidian brain vault).
        Requires parse_wiki to have run first. Writes assembled-graph.json.
        Returns node_count, edge_count, layer_count, tour_steps, graph_path."""
        if not _mcp_secure_call("knowledge_merge_wiki", "knowledge", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            from pathlib import Path as _Path
            from core.config import CONFIG as _CONFIG
            root = _Path(wiki_root).resolve() if wiki_root else _Path(_CONFIG["knowledge"]["wiki_root"])
            if not root.is_dir():
                return _safe_json({"error": f"Wiki root not found: {root}"})
            merger = _WikiMerger()
            graph = merger.merge_from_disk(root)
            out_path = merger.write(root, graph)
            return _safe_json({
                "wiki_root": str(root),
                "graph_path": str(out_path),
                "node_count": len(graph["nodes"]),
                "edge_count": len(graph["edges"]),
                "layer_count": len(graph["layers"]),
                "tour_steps": len(graph["tour"]),
                "project": graph.get("project", {}),
            })
        except FileNotFoundError as e:
            return _safe_json({"error": f"scan-manifest.json not found — run knowledge_parse_wiki first. {e}"})
        except Exception as e:
            return _safe_json({"error": str(e)})


def _add_claims_tools(mcp) -> None:
    """Wire vectorcode/src/claims.py MCP tools into the server."""
    try:
        from vectorcode.src.claims import (
            mcp_claim_task as _claim,
            mcp_release_task as _release,
            mcp_list_claims as _list,
            mcp_steal_task as _steal,
            mcp_get_stealable as _stealable,
            mcp_rebalance_load as _rebalance,
            mcp_claim_stats as _stats,
        )
        import json as _json
        import asyncio as _asyncio

        @mcp.tool
        async def claim_task(issue_id: str, agent_id: str, agent_name: str, title: str = "", priority: str = "medium") -> str:
            """Claim a task for a VECTOR agent — registers distributed ownership."""
            result = _claim(issue_id, agent_id, agent_name, capabilities=[], title=title, priority=priority)
            return _json.dumps(result)

        @mcp.tool
        async def release_task(issue_id: str, agent_id: str) -> str:
            """Release a task claim — makes it available for other districts."""
            return _json.dumps(_release(issue_id, agent_id))

        @mcp.tool
        async def list_claims(agent_id: str = "") -> str:
            """List active task claims — optionally filter by agent_id."""
            return _json.dumps(_list(agent_id or None))

        @mcp.tool
        async def steal_task(issue_id: str, stealer_id: str, stealer_name: str) -> str:
            """Steal a stale/stealable task from another agent."""
            return _json.dumps(_steal(issue_id, stealer_id, stealer_name))

        @mcp.tool
        async def get_stealable_tasks() -> str:
            """List all tasks currently marked as stealable."""
            return _json.dumps(_stealable())

        @mcp.tool
        async def rebalance_agent_load(agent_ids: str) -> str:
            """Rebalance task load across districts. Pass comma-separated agent IDs."""
            ids = [a.strip() for a in agent_ids.split(",") if a.strip()]
            return _json.dumps(_rebalance(ids))

        @mcp.tool
        async def claim_stats() -> str:
            """Get summary statistics for all task claims."""
            return _json.dumps(_stats())

        logger.info("[VECTOR][mcp] claims tools registered (7 tools)")
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] claims tools unavailable: {e}")


def _add_guidance_tools(mcp) -> None:
    """Wire vectorcode/src/guidance.py threat detection into the server."""
    try:
        from vectorcode.src.guidance import create_guidance_system
        import json as _json

        _gsys = None

        def _get_gsys():
            nonlocal _gsys
            if _gsys is None:
                _gsys = create_guidance_system()
            return _gsys

        @mcp.tool
        async def scan_for_threats(text: str, agent_id: str = "user") -> str:
            """Scan text for prompt injection, privilege escalation, or data exfiltration threats."""
            gsys = _get_gsys()
            signals = gsys["threat_detector"].analyze_input(text, agent_id)
            return _json.dumps([{"category": s.category, "severity": s.severity, "description": s.description, "evidence": s.evidence[:2]} for s in signals])

        @mcp.tool
        async def get_agent_coherence(agent_id: str) -> str:
            """Get coherence score and privilege level for a VECTOR agent."""
            gsys = _get_gsys()
            score = gsys["coherence_scheduler"].compute_score(agent_id)
            level = gsys["coherence_scheduler"].get_privilege_level(agent_id)
            return _json.dumps({"agent_id": agent_id, "coherence": round(score.overall * 100, 1), "privilege": level, "components": {"violations": round(score.violation_component, 3), "rework": round(score.rework_component, 3), "drift": round(score.drift_component, 3)}})

        @mcp.tool
        async def check_action_authority(action: str, current_level: str = "agent") -> str:
            """Check if action requires authority escalation (agent→human→institutional)."""
            gsys = _get_gsys()
            irrev = gsys["authority_gate"].classify_action(action)
            needs_esc, req_level = gsys["authority_gate"].requires_escalation(action, current_level)
            return _json.dumps({"action": action, "irreversibility": irrev, "needs_escalation": needs_esc, "required_level": req_level})

        logger.info("[VECTOR][mcp] guidance tools registered (3 tools)")
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] guidance tools unavailable: {e}")


def _add_kanban_tools(mcp) -> None:
    """Register kanban task-management tools (4 tools: list, create, update, complete)."""
    try:
        from tools.kanban_tools import (
            list_kanban_tasks,
            create_kanban_task,
            update_kanban_task,
            complete_kanban_task,
        )

        @mcp.tool
        def kanban_list(status: str = "active", limit: int = 20) -> str:
            """List VECTOR kanban tasks. status: active|done|all."""
            return _mcp_call_json(
                "kanban_list",
                list_kanban_tasks,
                status=status,
                limit=limit,
            )

        @mcp.tool
        def kanban_create(title: str, description: str = "", priority: str = "normal") -> str:
            """Create a new kanban task in VECTOR's task board."""
            return _mcp_call_json(
                "kanban_create",
                create_kanban_task,
                title=title,
                description=description,
                priority=priority,
            )

        @mcp.tool
        def kanban_update(task_id: str, status: str = None, description: str = None) -> str:
            """Update a kanban task's status or description."""
            return _mcp_call_json(
                "kanban_update",
                update_kanban_task,
                task_id=task_id,
                status=status,
                description=description,
            )

        @mcp.tool
        def kanban_complete(task_id: str) -> str:
            """Mark a kanban task as complete."""
            return _mcp_call_json("kanban_complete", complete_kanban_task, task_id=task_id)

        logger.info("[VECTOR][mcp] kanban tools registered (4 tools)")
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] kanban tools unavailable: {e}")


def _add_email_tools(mcp) -> None:
    """Register email tools from agentic-inbox (13 tools).

    Mirrors EmailMCP from cloud/email/workers/mcp/index.ts.
    Clients: Claude Code, Cursor — connect via /mcp endpoint.
    """
    import json as _json

    try:
        from districts.communications.email_agent import EmailAgent
        _email_agent = EmailAgent()

        @mcp.tool
        def email_list(folder: str = "inbox", limit: int = 20, page: int = 1) -> str:
            """List emails in a folder (inbox/sent/draft/archive/trash/spam)."""
            try:
                emails = _email_agent.list_emails(folder, limit, page)
                return _json.dumps({"emails": emails, "count": len(emails)})
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_get(email_id: str) -> str:
            """Get a single email with full body content and attachments."""
            try:
                email = _email_agent.get_email(email_id)
                if not email:
                    return _json.dumps({"error": "Email not found"})
                return _json.dumps(email)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_get_thread(thread_id: str) -> str:
            """Get all emails in a conversation thread, sorted chronologically."""
            try:
                thread = _email_agent.get_thread(thread_id)
                return _json.dumps({"thread": thread, "count": len(thread)})
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_search(query: str, folder: str = "") -> str:
            """Search emails by subject and body text. Optional folder filter."""
            try:
                results = _email_agent.search_emails(query, folder or None)
                return _json.dumps({"results": results, "count": len(results)})
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_draft_reply(original_email_id: str, to: str, subject: str, body: str) -> str:
            """Draft a reply to an existing email. Saves to Drafts folder. Does NOT send.
            Body must be plain text — no HTML, no markdown."""
            try:
                result = _email_agent.draft_reply(original_email_id, to, subject, body)
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_draft_new(to: str, subject: str, body: str) -> str:
            """Draft a new outbound email (not a reply). Saves to Drafts. Does NOT send.
            Arghyadeep reviews all drafts before sending."""
            try:
                result = _email_agent.draft_email(to, subject, body)
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_discard_draft(draft_id: str) -> str:
            """Delete a draft email that is no longer needed."""
            try:
                result = _email_agent.discard_draft(draft_id)
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_mark_read(email_id: str, read: bool = True) -> str:
            """Mark an email as read or unread."""
            try:
                result = _email_agent.mark_email_read(email_id, read)
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_move(email_id: str, folder: str) -> str:
            """Move an email to a folder (inbox/sent/draft/archive/trash/spam)."""
            try:
                result = _email_agent.move_email(email_id, folder)
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_delete(email_id: str) -> str:
            """Permanently delete an email."""
            try:
                result = _email_agent.delete_email(email_id)
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_status() -> str:
            """Get email inbox status: unread count and total emails."""
            try:
                import asyncio as _asyncio
                result = _asyncio.get_event_loop().run_until_complete(
                    _email_agent.run({"type": "status"})
                )
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_check_injection(body: str) -> str:
            """Scan an email body for prompt injection attempts. Returns {is_injection: bool}."""
            try:
                from core.email.ai_security import is_prompt_injection
                result = is_prompt_injection(body)
                return _json.dumps({"is_injection": result})
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_verify_draft(body: str) -> str:
            """Verify a draft email body — removes agent artifacts. Returns cleaned body."""
            try:
                from core.email.ai_security import verify_draft
                cleaned = verify_draft(body)
                return _json.dumps({"verified_body": cleaned, "ok": bool(cleaned)})
            except Exception as e:
                return _json.dumps({"error": str(e)})

        logger.info("[VECTOR][mcp] email tools registered (13 tools)")
    except Exception as e:
        logger.warning(f"[VECTOR][mcp] email tools unavailable: {e}")


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


def _add_research_tools(mcp) -> None:
    """Register deep research tools (4 tools) using VECTOR Research Engine.

    All research uses local Ollama models (VECTOR Rule 11 — no cloud API).
    Default search: DuckDuckGo + Wikipedia + ArXiv (no API key required).
    """
    import json as _json

    try:
        from districts.research.research_api import (
            quick_research as _qr,
            generate_report as _gr,
            research_papers as _rp,
            research_news as _rn,
        )
        _research_available = True
    except ImportError as e:
        logger.warning("[VECTOR][mcp] research tools unavailable: {}", e)
        _research_available = False

    if not _research_available:
        return

    @mcp.tool
    def research_quick(query: str, save_to_brain: bool = True) -> str:
        """Quick research summary using local Ollama (1-3 min).
        Uses DuckDuckGo + Wikipedia + ArXiv. No API key required.
        Returns: summary, findings, sources."""
        try:
            result = _qr(query, save_to_brain=save_to_brain)
            return _json.dumps({
                "summary": result.get("summary", ""),
                "sources": result.get("sources", [])[:10],
                "findings_count": len(result.get("findings", [])),
                "brain_path": result.get("brain_path", ""),
            })
        except Exception as e:
            return _json.dumps({"error": str(e)})

    @mcp.tool
    def research_report(query: str, searches_per_section: int = 2) -> str:
        """Generate full structured research report (10-30 min).
        Multi-section markdown with citations. Saves to VECTOR Brain.
        Returns: content (markdown), metadata."""
        try:
            result = _gr(query, searches_per_section=searches_per_section,
                          save_to_brain=True)
            content = result.get("content", "")
            return _json.dumps({
                "content": content[:5000],  # truncate for MCP response
                "full_length": len(content),
                "metadata": result.get("metadata", {}),
                "brain_path": result.get("brain_path", ""),
            })
        except Exception as e:
            return _json.dumps({"error": str(e)})

    @mcp.tool
    def research_papers(query: str, max_results: int = 10) -> str:
        """Academic paper research via ArXiv + PubMed + Semantic Scholar.
        Returns: summary of papers, findings with citations."""
        try:
            result = _rp(query, max_results=max_results)
            return _json.dumps({
                "summary": result.get("summary", ""),
                "sources": result.get("sources", [])[:15],
                "findings_count": len(result.get("findings", [])),
            })
        except Exception as e:
            return _json.dumps({"error": str(e)})

    @mcp.tool
    def research_news(query: str, max_results: int = 10) -> str:
        """Fast news research using DuckDuckGo + Wikinews.
        No API key required. Best for current events.
        Returns: summary, sources."""
        try:
            result = _rn(query, max_results=max_results)
            return _json.dumps({
                "summary": result.get("summary", ""),
                "sources": result.get("sources", [])[:10],
            })
        except Exception as e:
            return _json.dumps({"error": str(e)})

    logger.info("[VECTOR][mcp] Research tools registered: research_quick, research_report, research_papers, research_news")


def _add_brain_vault_tools(mcp) -> None:
    """Expose brain vault commands, skills, and agents to MCP clients (3 tools)."""
    import os as _os

    @mcp.tool
    async def run_command(command: str, params: str = "") -> str:
        """Run a brain/.claude/commands/ command by name. params is a JSON string."""
        try:
            from vectorcode.src.command_registry import get_command_registry
            import json as _json
            p = _json.loads(params) if params.strip() else {}
            reg = get_command_registry()
            result = await reg.execute(command, p)
            return str(result.get("result", result))
        except Exception as e:
            return f"Error running command '{command}': {e}"

    @mcp.tool
    def list_commands() -> str:
        """List all available brain commands from brain/.claude/commands/."""
        try:
            from vectorcode.src.command_registry import get_command_registry
            reg = get_command_registry()
            cmds = reg.list_commands()
            return "\n".join(f"/{c['name']}: {c['description']}" for c in cmds[:30])
        except Exception as e:
            return f"Error listing commands: {e}"

    @mcp.tool
    def list_skills() -> str:
        """List available brain skills from brain/.claude/skills/."""
        brain = r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain\.claude\skills"
        fallback = str(Path(__file__).parent.parent / "brain" / ".claude" / "skills")
        for skills_dir in [brain, fallback]:
            if _os.path.exists(skills_dir):
                skills = sorted(_os.listdir(skills_dir))
                return f"{len(skills)} skills available:\n" + "\n".join(skills[:50])
        return "Brain skills directory not accessible"

    logger.info("[VECTOR][mcp] Brain vault tools registered: run_command, list_commands, list_skills")


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
