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

    # ── Marketing CLI tools ───────────────────────────────────────────────────

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
        cli_dir = Path(__file__).parent.parent / "districts" / "marketing" / "tools" / "clis"
        script = cli_dir / f"{tool_name}.js"
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

    # ── Intelligence tools (VectorIntel / Shadowbroker) ─────────────────────

    @mcp.tool
    def intelligence_query(
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
        import asyncio
        from districts.intelligence.vectorintel_agent import VectorIntelAgent
        agent = VectorIntelAgent()
        if not agent._available:
            return "VectorIntel offline. Start: cd Shadowbroker-main && docker-compose up -d"
        task = {
            "type": action,
            "params": {"lat": lat, "lon": lon, "radius_km": radius_km, "label": label},
        }
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(agent.run(task))
        loop.close()
        return result.get("message", str(result))

    # ── Memory tools ──────────────────────────────────────────────────────────

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

    # ── Research tools ────────────────────────────────────────────────────────

    @mcp.tool
    def search_web(query: str, max_results: int = 5) -> str:
        """Search the web for information using VECTOR's WebScout agent."""
        try:
            from districts.research.web_scout import WebScout
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
            from districts.research.reddit_miner import RedditMiner
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
            from districts.research.paper_reader import PaperReader
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
            from districts.governance.llm_council import LLMCouncil
            council = LLMCouncil()
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                council.convene(question=question, stakes=stakes)
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
            from districts.coding.code_reviewer import CodeReviewer
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
            from districts.coding.git_bot import GitBot
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

    # ── OpenMythos training tools ─────────────────────────────────────────────

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

    _add_expansion_tools(mcp)
    _add_claims_tools(mcp)
    _add_guidance_tools(mcp)
    _add_kanban_tools(mcp)
    _add_email_tools(mcp)
    _add_research_tools(mcp)
    return mcp


# Public alias required by tests and VectorCode MCP client
create_mcp_app = _make_server


def _reg(mcp, name: str, doc: str = "") -> None:
    """Register a named stub tool on mcp so it appears in list_tools()."""
    def _fn(input: str = "") -> str:
        return f"[{name}] not yet wired"
    _fn.__name__ = name
    _fn.__doc__ = doc or f"VectorCode {name} tool."
    mcp.tool(_fn)


def _add_expansion_tools(mcp) -> None:
    """Register 300 new VectorCode tools across 16 categories."""

    # ── agent_* (8) ──────────────────────────────────────────────────────────
    for n, d in [
        ("agent_spawn",   "Spawn a new VectorCode agent by type"),
        ("agent_list",    "List all active agents in the swarm"),
        ("agent_status",  "Get status and HP of a specific agent"),
        ("agent_stop",    "Stop and deregister an agent"),
        ("agent_metrics", "Get performance metrics for an agent"),
        ("agent_pool",    "Show the full agent pool with domains"),
        ("agent_health",  "Check health of all running agents"),
        ("agent_logs",    "Retrieve recent logs for an agent"),
    ]:
        _reg(mcp, n, d)

    # ── swarm_* (9) ──────────────────────────────────────────────────────────
    for n, d in [
        ("swarm_init",     "Initialise a new swarm with topology"),
        ("swarm_submit",   "Submit a task to the swarm"),
        ("swarm_assign",   "Assign a subtask to a specific agent"),
        ("swarm_execute",  "Execute a swarm plan"),
        ("swarm_status",   "Get current swarm status and topology"),
        ("swarm_shutdown", "Shut down all swarm agents"),
        ("swarm_topology", "Get or change the swarm topology"),
        ("swarm_agents",   "List agents grouped by domain"),
        ("swarm_report",   "Generate a swarm execution report"),
    ]:
        _reg(mcp, n, d)

    # ── memory_* (12) ────────────────────────────────────────────────────────
    for n, d in [
        ("memory_faiss_add",       "Add an embedding to the FAISS index"),
        ("memory_faiss_search",    "Search FAISS index by embedding similarity"),
        ("memory_pattern_save",    "Save a task→plan→outcome pattern"),
        ("memory_pattern_recall",  "Recall a pattern for a task by similarity"),
        ("memory_bridge_sync",     "Trigger bidirectional memory bridge sync"),
        ("memory_export",          "Export memory index to file"),
        ("memory_import",          "Import memory index from file"),
        ("memory_stats",           "Get memory index statistics"),
        ("memory_clear",           "Clear all entries from memory index"),
        ("memory_semantic_search", "Semantic search over stored patterns"),
        ("memory_recent",          "Get most recently added memory entries"),
        ("memory_categories",      "List all insight categories in memory"),
    ]:
        _reg(mcp, n, d)

    # ── hook_* (17) ──────────────────────────────────────────────────────────
    for n, d in [
        ("hook_register",        "Register a handler on a named hook"),
        ("hook_fire",            "Fire a hook with a context payload"),
        ("hook_list",            "List all registered hooks and handler counts"),
        ("hook_pre_edit",        "Fire PRE_EDIT hook"),
        ("hook_post_edit",       "Fire POST_EDIT hook"),
        ("hook_pre_task",        "Fire PRE_TASK hook"),
        ("hook_post_task",       "Fire POST_TASK hook"),
        ("hook_session_start",   "Fire SESSION_START hook"),
        ("hook_session_end",     "Fire SESSION_END hook"),
        ("hook_route",           "Fire ROUTE hook"),
        ("hook_explain",         "Fire EXPLAIN hook"),
        ("hook_notify",          "Fire NOTIFY hook"),
        ("hook_intelligence",    "Fire INTELLIGENCE hook"),
        ("hook_task_complete",   "Fire TASK_COMPLETE hook"),
        ("hook_session_restore", "Fire SESSION_RESTORE hook"),
        ("hook_post_command",    "Fire POST_COMMAND hook"),
        ("hook_transfer",        "Fire TRANSFER hook"),
    ]:
        _reg(mcp, n, d)

    # ── task_* (8) ───────────────────────────────────────────────────────────
    for n, d in [
        ("task_create",    "Create a new task in the queue"),
        ("task_assign",    "Assign a task to an agent"),
        ("task_complete",  "Mark a task as complete"),
        ("task_list",      "List all tasks with status"),
        ("task_update",    "Update task metadata or status"),
        ("task_delete",    "Delete a task from the queue"),
        ("task_status",    "Get detailed status of a specific task"),
        ("task_submit_bg", "Submit a background low-priority task"),
    ]:
        _reg(mcp, n, d)

    # ── security_* (10) ──────────────────────────────────────────────────────
    for n, d in [
        ("security_scan",            "Scan a file or directory for threats"),
        ("security_audit",           "Run a full security audit"),
        ("security_validate",        "Validate input against security rules"),
        ("security_path_check",      "Check if a path is within the allowed root"),
        ("security_cve_scan",        "Scan dependencies for known CVEs"),
        ("security_threats",         "List current detected threats"),
        ("security_report",          "Generate a security report"),
        ("security_input_validate",  "Validate tool input for injection patterns"),
        ("security_executor_check",  "Check if a command is in the allowlist"),
        ("security_allowlist",       "View or update the command allowlist"),
    ]:
        _reg(mcp, n, d)

    # ── neural_* (8) ─────────────────────────────────────────────────────────
    for n, d in [
        ("neural_pattern_save",   "Save a neural pattern to PatternStore"),
        ("neural_pattern_recall", "Recall the best matching neural pattern"),
        ("neural_train",          "Trigger background pattern training"),
        ("neural_status",         "Get PatternStore index status"),
        ("neural_predict",        "Predict the best plan for a task"),
        ("neural_optimize",       "Optimise stored patterns by reward"),
        ("neural_reward",         "Update the reward for a stored pattern"),
        ("neural_stats",          "Get neural cache hit/miss statistics"),
    ]:
        _reg(mcp, n, d)

    # ── file_* (10) ──────────────────────────────────────────────────────────
    for n, d in [
        ("file_read",     "Read a file within the repo root"),
        ("file_write",    "Write content to a file"),
        ("file_edit",     "Apply a string replacement edit to a file"),
        ("file_grep",     "Grep for a pattern in files"),
        ("file_glob",     "Glob for files matching a pattern"),
        ("file_delete",   "Delete a file (RED gate)"),
        ("file_exists",   "Check if a file exists"),
        ("file_diff",     "Show unified diff for a file"),
        ("file_list_dir", "List contents of a directory"),
        ("file_copy",     "Copy a file to a new path"),
    ]:
        _reg(mcp, n, d)

    # ── git_* (12) ───────────────────────────────────────────────────────────
    for n, d in [
        ("git_commit",    "Create a git commit with a message (YELLOW gate)"),
        ("git_push",      "Push current branch to remote (RED gate)"),
        ("git_pr_create", "Create a GitHub pull request (RED gate)"),
        ("git_diff",      "Show git diff for staged or unstaged changes"),
        ("git_blame",     "Show git blame for a file"),
        ("git_log",       "Show recent git log"),
        ("git_branch",    "List or create branches"),
        ("git_checkout",  "Checkout a branch or file"),
        ("git_stash",     "Stash or pop working changes"),
        ("git_merge",     "Merge a branch (RED gate)"),
        ("git_rebase",    "Rebase onto a branch (RED gate)"),
    ]:
        _reg(mcp, n, d)

    # ── test_* (30) ──────────────────────────────────────────────────────────
    for n, d in [
        ("test_run",         "Run the full test suite"),
        ("test_watch",       "Watch files and re-run tests on change"),
        ("test_coverage",    "Generate test coverage report"),
        ("test_report",      "Get the last test run report"),
        ("test_create",      "Create a new test file from a template"),
        ("test_generate",    "Generate tests for a module using LLM"),
        ("test_fix",         "Attempt to auto-fix failing tests"),
        ("test_status",      "Show pass/fail status of all test files"),
        ("test_discover",    "Discover all test files in the repo"),
        ("test_parallel",    "Run tests in parallel"),
        ("test_filter",      "Run tests matching a keyword filter"),
        ("test_benchmark",   "Run performance benchmarks"),
        ("test_snapshot",    "Create/compare snapshot tests"),
        ("test_mock",        "Generate mock objects for a module"),
        ("test_assert",      "Check assertion helpers"),
        ("test_setup",       "Configure test environment"),
        ("test_teardown",    "Clean up test environment"),
        ("test_fixtures",    "List available pytest fixtures"),
        ("test_data",        "Load test data fixtures"),
        ("test_clean",       "Remove test artefacts and caches"),
        ("test_profile",     "Profile a test run"),
        ("test_compare",     "Compare two test runs"),
        ("test_validate",    "Validate test structure"),
        ("test_integration", "Run integration tests only"),
        ("test_unit",        "Run unit tests only"),
        ("test_e2e",         "Run end-to-end tests"),
        ("test_smoke",       "Run smoke tests"),
        ("test_regression",  "Run regression test suite"),
        ("test_perf",        "Run performance regression tests"),
        ("test_debug",       "Run tests with verbose debug output"),
    ]:
        _reg(mcp, n, d)

    # ── doc_* (28) ───────────────────────────────────────────────────────────
    for n, d in [
        ("doc_generate",   "Generate documentation from source code"),
        ("doc_update",     "Update existing documentation"),
        ("doc_search",     "Search documentation content"),
        ("doc_export",     "Export docs to HTML/PDF"),
        ("doc_import",     "Import external documentation"),
        ("doc_render",     "Render a markdown doc to HTML"),
        ("doc_validate",   "Validate documentation completeness"),
        ("doc_lint",       "Lint documentation for issues"),
        ("doc_version",    "Version or tag documentation"),
        ("doc_publish",    "Publish docs to a target"),
        ("doc_draft",      "Create a draft documentation page"),
        ("doc_review",     "Review documentation for accuracy"),
        ("doc_approve",    "Approve and finalise documentation"),
        ("doc_archive",    "Archive old documentation"),
        ("doc_index",      "Rebuild documentation index"),
        ("doc_tag",        "Tag documentation entries"),
        ("doc_link",       "Add cross-references between docs"),
        ("doc_unlink",     "Remove cross-references"),
        ("doc_move",       "Move a documentation file"),
        ("doc_copy",       "Copy a documentation file"),
        ("doc_delete",     "Delete a documentation file"),
        ("doc_restore",    "Restore deleted documentation"),
        ("doc_format",     "Format documentation to style guide"),
        ("doc_translate",  "Translate documentation to another language"),
        ("doc_summarize",  "Summarize a documentation page"),
        ("doc_extract",    "Extract key facts from documentation"),
        ("doc_embed",      "Embed documentation in vector index"),
        ("doc_compare",    "Compare two documentation versions"),
    ]:
        _reg(mcp, n, d)

    # ── browser_* (28) ───────────────────────────────────────────────────────
    for n, d in [
        ("browser_open",       "Open a new browser session"),
        ("browser_close",      "Close browser session"),
        ("browser_navigate",   "Navigate to a URL (YELLOW gate)"),
        ("browser_screenshot", "Take a screenshot of current page"),
        ("browser_click",      "Click an element by selector (YELLOW gate)"),
        ("browser_type",       "Type text into an input element"),
        ("browser_scroll",     "Scroll the page"),
        ("browser_extract",    "Extract text content from page"),
        ("browser_wait",       "Wait for an element or condition"),
        ("browser_eval",       "Evaluate JavaScript on page"),
        ("browser_cookie",     "Get or set browser cookies"),
        ("browser_storage",    "Get or set localStorage/sessionStorage"),
        ("browser_network",    "Intercept and inspect network requests"),
        ("browser_console",    "Get browser console logs"),
        ("browser_pdf",        "Export page as PDF"),
        ("browser_record",     "Record a browser session"),
        ("browser_replay",     "Replay a recorded browser session"),
        ("browser_assert",     "Assert a page condition"),
        ("browser_element",    "Get info about a page element"),
        ("browser_form",       "Fill a form"),
        ("browser_select",     "Select a dropdown option"),
        ("browser_hover",      "Hover over an element"),
        ("browser_drag",       "Drag and drop an element"),
        ("browser_upload",     "Upload a file to an input"),
        ("browser_download",   "Download a resource"),
        ("browser_resize",     "Resize the browser viewport"),
        ("browser_back",       "Navigate back in history"),
        ("browser_forward",    "Navigate forward in history"),
    ]:
        _reg(mcp, n, d)

    # ── graph_* (28) ─────────────────────────────────────────────────────────
    for n, d in [
        ("graph_index",       "Index a file into the code graph"),
        ("graph_query",       "Query the code graph"),
        ("graph_blast_radius","Get blast radius for a changed symbol"),
        ("graph_dependents",  "Get files that depend on a symbol"),
        ("graph_visualize",   "Visualize the code graph as DOT/SVG"),
        ("graph_export",      "Export code graph to JSON"),
        ("graph_import",      "Import code graph from JSON"),
        ("graph_clean",       "Remove stale entries from graph"),
        ("graph_rebuild",     "Rebuild the full code graph from scratch"),
        ("graph_diff",        "Show graph changes between two commits"),
        ("graph_symbols",     "List all symbols in a file"),
        ("graph_callers",     "Get callers of a symbol"),
        ("graph_callees",     "Get callees of a function"),
        ("graph_cycles",      "Detect circular dependencies"),
        ("graph_stats",       "Get code graph statistics"),
        ("graph_search",      "Search for symbols by name pattern"),
        ("graph_filter",      "Filter graph by domain or file"),
        ("graph_merge",       "Merge two code graphs"),
        ("graph_compare",     "Compare code graphs across branches"),
        ("graph_trace",       "Trace call path between two symbols"),
        ("graph_annotate",    "Annotate a symbol with metadata"),
        ("graph_highlight",   "Highlight a symbol's connections"),
        ("graph_cluster",     "Cluster related symbols together"),
        ("graph_path",        "Find shortest path between symbols"),
        ("graph_distance",    "Get graph distance between symbols"),
        ("graph_centrality",  "Compute symbol centrality score"),
        ("graph_rank",        "Rank symbols by importance"),
        ("graph_report",      "Generate a code graph health report"),
    ]:
        _reg(mcp, n, d)

    # ── perf_* (28) ──────────────────────────────────────────────────────────
    for n, d in [
        ("perf_profile",      "Profile a Python file or function"),
        ("perf_benchmark",    "Run a performance benchmark"),
        ("perf_trace",        "Trace execution for performance"),
        ("perf_report",       "Get the last performance report"),
        ("perf_compare",      "Compare two performance baselines"),
        ("perf_analyze",      "Analyse performance bottlenecks"),
        ("perf_optimize",     "Suggest performance optimisations"),
        ("perf_memory",       "Profile memory usage"),
        ("perf_cpu",          "Profile CPU usage"),
        ("perf_io",           "Profile I/O operations"),
        ("perf_network",      "Profile network latency"),
        ("perf_cache",        "Analyse cache hit rates"),
        ("perf_gc",           "Analyse garbage collection"),
        ("perf_allocations",  "Track memory allocations"),
        ("perf_flame_graph",  "Generate a flame graph"),
        ("perf_hotspots",     "Identify performance hotspots"),
        ("perf_regression",   "Detect performance regressions"),
        ("perf_baseline",     "Set a performance baseline"),
        ("perf_monitor",      "Monitor performance in real time"),
        ("perf_alert",        "Set a performance alert threshold"),
        ("perf_history",      "View performance history"),
        ("perf_export",       "Export performance data"),
        ("perf_import",       "Import performance baseline data"),
        ("perf_simulate",     "Simulate a load scenario"),
        ("perf_load",         "Run a load test"),
        ("perf_stress",       "Run a stress test"),
        ("perf_concurrent",   "Test concurrent request handling"),
        ("perf_latency",      "Measure latency distribution"),
    ]:
        _reg(mcp, n, d)

    # ── worker_* (26) ────────────────────────────────────────────────────────
    for n, d in [
        ("worker_list",       "List all background workers"),
        ("worker_status",     "Get status of a worker"),
        ("worker_submit",     "Submit a worker task"),
        ("worker_cancel",     "Cancel a running worker"),
        ("worker_pause",      "Pause a worker"),
        ("worker_resume",     "Resume a paused worker"),
        ("worker_priority",   "Change worker task priority"),
        ("worker_logs",       "Get worker execution logs"),
        ("worker_metrics",    "Get worker performance metrics"),
        ("worker_health",     "Check worker health"),
        ("worker_restart",    "Restart a worker"),
        ("worker_stop",       "Stop a worker"),
        ("worker_start",      "Start a worker by name"),
        ("worker_scale",      "Scale worker concurrency"),
        ("worker_assign",     "Assign worker to an agent"),
        ("worker_queue",      "View worker task queue"),
        ("worker_drain",      "Drain the worker queue"),
        ("worker_flush",      "Flush completed worker tasks"),
        ("worker_retry",      "Retry a failed worker task"),
        ("worker_timeout",    "Set worker task timeout"),
        ("worker_heartbeat",  "Send a worker heartbeat"),
        ("worker_checkpoint", "Save worker checkpoint state"),
        ("worker_migrate",    "Migrate workers to new queue"),
        ("worker_export",     "Export worker state"),
        ("worker_import",     "Import worker state"),
        ("worker_reset",      "Reset all workers to initial state"),
    ]:
        _reg(mcp, n, d)

    # ── config_* (26) ────────────────────────────────────────────────────────
    for n, d in [
        ("config_get",      "Get a VECTOR config value"),
        ("config_set",      "Set a VECTOR config value (YELLOW gate)"),
        ("config_list",     "List all config keys and values"),
        ("config_reset",    "Reset config to defaults"),
        ("config_export",   "Export config to JSON file"),
        ("config_import",   "Import config from JSON file"),
        ("config_validate", "Validate config against schema"),
        ("config_diff",     "Diff current config against defaults"),
        ("config_apply",    "Apply a config change set"),
        ("config_rollback", "Rollback to previous config"),
        ("config_backup",   "Backup current config"),
        ("config_restore",  "Restore a config backup"),
        ("config_version",  "Get config schema version"),
        ("config_env",      "View or set environment variables"),
        ("config_secrets",  "Manage secret config values"),
        ("config_models",   "View or change model routing config"),
        ("config_agents",   "View or update agent config"),
        ("config_hooks",    "View or update hook config"),
        ("config_workers",  "View or update worker config"),
        ("config_memory",   "View or update memory config"),
        ("config_security", "View or update security config"),
        ("config_logging",  "View or update logging config"),
        ("config_network",  "View or update network config"),
        ("config_storage",  "View or update storage config"),
        ("config_auth",     "View or update auth config"),
        ("config_metrics",  "View or update metrics config"),
    ]:
        _reg(mcp, n, d)


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
    import json as _json
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))
        from tools.kanban_tools import (
            list_kanban_tasks,
            create_kanban_task,
            update_kanban_task,
            complete_kanban_task,
        )

        @mcp.tool
        def kanban_list(status: str = "active", limit: int = 20) -> str:
            """List VECTOR kanban tasks. status: active|done|all."""
            try:
                return _json.dumps(list_kanban_tasks(status=status, limit=limit))
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def kanban_create(title: str, description: str = "", priority: str = "normal") -> str:
            """Create a new kanban task in VECTOR's task board."""
            try:
                return _json.dumps(create_kanban_task(title=title, description=description, priority=priority))
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def kanban_update(task_id: str, status: str = None, description: str = None) -> str:
            """Update a kanban task's status or description."""
            try:
                return _json.dumps(update_kanban_task(task_id=task_id, status=status, description=description))
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def kanban_complete(task_id: str) -> str:
            """Mark a kanban task as complete."""
            try:
                return _json.dumps(complete_kanban_task(task_id=task_id))
            except Exception as e:
                return _json.dumps({"error": str(e)})

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
