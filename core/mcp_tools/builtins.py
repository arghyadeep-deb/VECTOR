"""MCP built-in VECTOR tool registrations.

These are the original core tool registrations that used to live inline in
``core.mcp_server._make_server``. They stay grouped here so the server module
can focus on transport setup and registration orchestration.
"""

import asyncio
from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.mcp_tools.security import mcp_secure_call as _mcp_secure_call


_ROOT = Path(__file__).resolve().parents[2]


def add_builtin_tools(mcp) -> None:
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
        cli_dir = _ROOT / "districts" / "marketing" / "tools" / "clis"
        script = (cli_dir / f"{tool_name}.js").resolve()
        if not script.is_relative_to(cli_dir.resolve()):
            return "Access denied: tool path outside CLI directory."
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
            if result.returncode != 0:
                logger.warning(
                    "[VECTOR][mcp] marketing_cli {} exited rc={}: {}",
                    tool_name, result.returncode, out[:200],
                )
                return f"CLI error for '{tool_name}': exit code {result.returncode}: {out}"
            logger.info(f"[VECTOR][mcp] marketing_cli {tool_name} → {len(out)} chars")
            return out
        except subprocess.TimeoutExpired:
            return f"CLI tool '{tool_name}' timed out after 30s"
        except Exception as e:
            return f"CLI error for '{tool_name}': {e}"

    @mcp.tool
    def list_marketing_tools() -> str:
        """List all available marketing CLI tools grouped by category."""
        cli_dir = _ROOT / "districts" / "marketing" / "tools" / "clis"
        tools = sorted(f.stem for f in cli_dir.glob("*.js"))
        skills_dir = _ROOT / "districts" / "marketing" / "skills"
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
        import re as _re
        if not _re.fullmatch(r"[A-Za-z0-9_]{1,21}", subreddit):
            return f"Reddit mining failed: invalid subreddit '{subreddit}'"
        try:
            from districts.research.reddit_miner import RedditMiner
            miner = RedditMiner()
            result = await miner.fetch_hot(subreddit, limit=limit)
            if not result:
                return f"Reddit mining failed: no posts returned for r/{subreddit}"
            import json
            return json.dumps(result, indent=2, default=str)
        except Exception as e:
            logger.error(f"[VECTOR][mcp] mine_reddit failed: {e}")
            return f"Reddit mining failed: {e}"

    @mcp.tool
    async def read_paper(url: str) -> str:
        """Fetch and summarise an ArXiv paper or research URL using VECTOR's PaperReader."""
        try:
            query = url.strip()
            if query.lower().startswith(("http://", "https://")):
                from core.security.ssrf_guard import get_ssrf_guard
                check = get_ssrf_guard().check_url(query)
                if not check.safe:
                    return f"Paper reading failed: URL blocked ({check.reason})"
                # PaperReader has no read(); look the paper up by its arXiv id.
                query = query.rstrip("/").rsplit("/", 1)[-1].removesuffix(".pdf")
            from districts.research.paper_reader import PaperReader
            reader = PaperReader()
            result = await reader.search_papers(query, max_results=1)
            if not result:
                return f"Paper reading failed: no paper found for '{url}'"
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
            _root = _ROOT
            path = Path(file_path).resolve()
            if not path.is_relative_to(_root.resolve()):
                return f"Access denied: '{file_path}' is outside the VECTOR codebase."
            if path.suffix != ".py":
                return f"Access denied: '{file_path}' is not a Python file."
            if not path.exists():
                return f"File not found: {file_path}"
            # review_file is synchronous (returns a dict) -- awaiting it raised TypeError.
            result = await asyncio.to_thread(reviewer.review_file, str(path))
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
            if not result:
                return "Git status failed: no repository status available"
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
        # title becomes "<vault>/<folder>/<title>.md"; ObsidianSync only validates the
        # folder, so a title such as "../../x" would escape the vault (CWE-22).
        if not title.strip() or "/" in title or "\\" in title or ".." in title or "\x00" in title:
            return f"Note write failed: invalid title '{title}'"
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
    async def search_vault(query: str, top_k: int = 5) -> str:
        """Search the VECTOR Obsidian vault via LightRAG semantic search."""
        try:
            from core.memory.obsidian_sync import ObsidianSync
            sync = ObsidianSync()
            # ObsidianSync.query is async and takes (text, mode) -- it has no top_k.
            results = await sync.query(query)
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
            # NudgeEngine.push is synchronous (returns a dict) and priority is 0-1.
            nudge.push(message, source="ask_user_question", priority=1.0)
            return f"Question sent to owner: {question}"
        except Exception as e:
            from loguru import logger
            logger.warning("[VECTOR][mcp] ask_user_question failed: {}", e)
            return f"Could not send question: {e}"
