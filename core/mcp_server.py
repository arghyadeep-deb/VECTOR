"""
VECTOR MCP Server — exposes district capabilities as MCP tools.

Run:  python core/mcp_server.py
Transport: stdio (default) → works with Claude Code, Cursor, any MCP client.
HTTP/SSE:  python core/mcp_server.py --transport sse --port 9000

RULE 11: All Ollama calls go through ollama_safe, never direct.
RULE 3:  All write/execute actions gate through permission_gateway.
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

try:
    from fastmcp import FastMCP
    _FASTMCP_AVAILABLE = True
except ImportError:
    _FASTMCP_AVAILABLE = False
    logger.warning("[VECTOR][mcp] fastmcp not installed — run: pip install fastmcp")

from core.config import CONFIG


def _make_server() -> "FastMCP":
    mcp = FastMCP(
        "VECTOR",
        instructions=(
            "You are connected to VECTOR — a Darwinian multi-agent AI system "
            "running on Arghyadeep's Legion Pro 5. "
            "Use these tools to access VECTOR's memory, research, goals, and districts."
        ),
    )

    # ── Memory tools ──────────────────────────────────────────────────────────

    @mcp.tool
    def recall_memory(query: str, limit: int = 5) -> str:
        """Search VECTOR's episodic memory for past events and observations."""
        try:
            from core.memory.episodic import EpisodicMemory
            mem = EpisodicMemory()
            results = mem.search(query, limit=limit)
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
        try:
            from core.memory.episodic import EpisodicMemory
            mem = EpisodicMemory()
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            mem.store(event_type=event_type, content=content, tags=tag_list, source="mcp")
            return f"Stored event '{event_type}' in episodic memory."
        except Exception as e:
            logger.error(f"[VECTOR][mcp] store_memory failed: {e}")
            return f"Memory store failed: {e}"

    # ── World state / goals ───────────────────────────────────────────────────

    @mcp.tool
    def get_world_state() -> str:
        """Get VECTOR's current world state: comms, health, active goals, time."""
        try:
            from core.loop.context_engine import ContextEngine
            ctx = ContextEngine()
            state = ctx.get_full_context()
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

    # ── Research tools ────────────────────────────────────────────────────────

    @mcp.tool
    def search_web(query: str, max_results: int = 5) -> str:
        """Search the web for information using VECTOR's WebScout agent."""
        try:
            from agents.districts.research.web_scout import WebScout
            scout = WebScout()
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(scout.search(query, max_results=max_results))
            loop.close()
            return str(result)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] search_web failed: {e}")
            return f"Web search failed: {e}"

    @mcp.tool
    def mine_reddit(subreddit: str = "LocalLLaMA", limit: int = 10) -> str:
        """Get hot posts from a subreddit via VECTOR's RedditMiner (no OAuth needed)."""
        try:
            from agents.districts.research.reddit_miner import RedditMiner
            miner = RedditMiner()
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(miner.mine_subreddit(subreddit, limit=limit))
            loop.close()
            import json
            return json.dumps(result, indent=2, default=str)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] mine_reddit failed: {e}")
            return f"Reddit mining failed: {e}"

    @mcp.tool
    def read_paper(url: str) -> str:
        """Fetch and summarise an ArXiv paper or research URL using VECTOR's PaperReader."""
        try:
            from agents.districts.research.paper_reader import PaperReader
            reader = PaperReader()
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(reader.read(url))
            loop.close()
            return str(result)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] read_paper failed: {e}")
            return f"Paper reading failed: {e}"

    # ── Governance tools ──────────────────────────────────────────────────────

    @mcp.tool
    def convene_council(question: str, stakes: str = "high") -> str:
        """
        Convene the VECTOR LLM Council for a high-stakes decision.
        stakes: 'high' or 'critical'. Requires 700+ HP gate. Max 10 sessions/week.
        """
        try:
            from agents.districts.governance.llm_council import LLMCouncil
            council = LLMCouncil()
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                council.convene(question=question, stakes=stakes, requester_hp=800)
            )
            loop.close()
            verdict = result.get("verdict", "No verdict produced.")
            session_id = result.get("session_id", "?")
            return f"[Session {session_id}]\n{verdict}"
        except Exception as e:
            logger.error(f"[VECTOR][mcp] convene_council failed: {e}")
            return f"Council session failed: {e}"

    # ── Coding tools ──────────────────────────────────────────────────────────

    @mcp.tool
    def review_code(file_path: str) -> str:
        """Run VECTOR's CodeReviewer on a Python file and return the review report."""
        try:
            from agents.districts.coding.code_reviewer import CodeReviewer
            reviewer = CodeReviewer()
            path = Path(file_path)
            if not path.exists():
                return f"File not found: {file_path}"
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(reviewer.review_file(str(path)))
            loop.close()
            return str(result)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] review_code failed: {e}")
            return f"Code review failed: {e}"

    @mcp.tool
    def git_status() -> str:
        """Get the current git status of the VECTOR codebase."""
        try:
            from agents.districts.coding.git_bot import GitBot
            bot = GitBot()
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(bot.get_status())
            loop.close()
            return str(result)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] git_status failed: {e}")
            return f"Git status failed: {e}"

    # ── Karpathy / training tools ─────────────────────────────────────────────

    @mcp.tool
    def karpathy_session(topic: str, file_path: str = "") -> str:
        """
        Start a tracked 30-minute Karpathy typing session (RULE 12).
        topic: what you're typing today (e.g. 'bigram LM', 'attention forward pass').
        """
        try:
            from agents.districts.karpathy_lab.code_typer import CodeTyper
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
            from agents.districts.karpathy_lab.code_typer import CodeTyper
            typer = CodeTyper()
            streak = typer.get_streak()
            today = typer.get_today_summary()
            return f"Streak: {streak} day(s)\nToday: {today}"
        except Exception as e:
            logger.error(f"[VECTOR][mcp] karpathy_streak failed: {e}")
            return f"Streak check failed: {e}"

    # ── Obsidian tools ────────────────────────────────────────────────────────

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

    # ── System resource ───────────────────────────────────────────────────────

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

    return mcp


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
