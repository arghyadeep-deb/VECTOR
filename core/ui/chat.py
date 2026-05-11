"""
VECTOR Terminal Chat Interface.

Run:  python -m core.ui.chat
Or:   python core/ui/chat.py

RULE 1:  session_hydration_prompt() on every LLM call.
RULE 11: all inference via ollama_safe (no Claude API).
RULE 8:  every conversation stored in episodic memory.
"""
import sys
import asyncio
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.live import Live
    from rich.prompt import Prompt
    from rich.rule import Rule
    from rich import box
    _RICH = True
except ImportError:
    _RICH = False

from core.config import CONFIG

_BANNER = r"""
 __   __ _____ ____ _____ ___  ____
 \ \ / /| ____/ ___|_   _/ _ \|  _ \
  \ V / |  _|| |     | || | | | |_) |
   | |  | |__| |___  | || |_| |  _ <
   |_|  |_____\____| |_| \___/|_| \_\
"""

_VERSION = CONFIG.get("version", "1.0.0")
_OWNER = CONFIG.get("owner_name", "Arghyadeep")
_MODEL = CONFIG["models"]["focus"]
_REASONING = CONFIG["models"]["reasoning"]


def _get_status_line() -> str:
    """One-line status: Ollama ping, goals count, time."""
    from core.inference.ollama_safe import ping
    ollama_ok = ping()

    try:
        from core.brain.goal_system import GoalSystem
        gs = GoalSystem()
        actions = gs.generate_immediate_actions()
        goal_count = len(actions)
    except Exception:
        goal_count = 0

    now = datetime.datetime.now().strftime("%H:%M")
    ollama_status = "[green]Ollama: OK[/green]" if ollama_ok else "[red]Ollama: DOWN[/red]"
    return f"[bold cyan]HP: 500[/bold cyan]  │  {ollama_status}  │  [yellow]Goals: {goal_count}[/yellow]  │  [dim]{now}[/dim]"


def _render_header(console: "Console") -> None:
    banner_text = Text(_BANNER, style="bold green")
    console.print(banner_text)
    console.print(f"  [dim]V{_VERSION}  •  Virtual Entity for Cognitive Tasks & Operational Reasoning[/dim]")
    console.print(Rule(style="green"))
    console.print("  " + _get_status_line())
    console.print(Rule(style="green"))
    console.print()
    console.print("[dim]  Commands: /status  /goals  /search <q>  /note <title>  /districts  /council <q>  /help  /quit[/dim]")
    console.print()


def _handle_command(cmd: str, console: "Console") -> bool:
    """Handle slash commands. Returns True to continue, False to quit."""
    parts = cmd.strip().split(None, 1)
    verb = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if verb in ("/quit", "/exit", "/q"):
        console.print("[dim]VECTOR shutting down. Goodbye.[/dim]")
        return False

    if verb == "/help":
        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        t.add_column("cmd", style="cyan")
        t.add_column("desc")
        for row in [
            ("/status", "System status, model health, HP"),
            ("/goals", "Active goals across all horizons"),
            ("/search <q>", "Web search via research district"),
            ("/note <title>", "Write a quick note to Obsidian vault"),
            ("/districts", "All 25 districts and their status"),
            ("/council <q>", "Convene LLM council for high-stakes question"),
            ("/karpathy", "Today's Karpathy session streak"),
            ("/quit", "Exit VECTOR terminal"),
        ]:
            t.add_row(*row)
        console.print(Panel(t, title="[bold green]VECTOR Commands[/bold green]", border_style="green"))
        return True

    if verb == "/status":
        try:
            from core.loop.context_engine import ContextEngine
            ctx = ContextEngine()
            state = ctx.get_full_context()
            t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
            t.add_column("key", style="cyan", width=20)
            t.add_column("value")
            t.add_row("Time", state.get("current_time", "?"))
            t.add_row("Ollama", str(state.get("ollama_available", "?")))
            comms = state.get("comms", {})
            t.add_row("Comms", f"urgent={comms.get('urgent',0)} unread={comms.get('unread',0)}")
            health = state.get("owner_health", {})
            t.add_row("Fatigue", str(health.get("fatigue_score", "?")))
            t.add_row("Model", _MODEL)
            console.print(Panel(t, title="[bold green]VECTOR Status[/bold green]", border_style="green"))
        except Exception as e:
            console.print(f"[red]Status error: {e}[/red]")
        return True

    if verb == "/goals":
        try:
            from core.brain.goal_system import GoalSystem
            actions = GoalSystem().generate_immediate_actions()
            if not actions:
                console.print("[dim]No active immediate actions.[/dim]")
            else:
                t = Table(box=box.SIMPLE, padding=(0, 1))
                t.add_column("#", style="dim", width=3)
                t.add_column("Action", style="cyan")
                t.add_column("Priority", style="yellow", width=10)
                for i, a in enumerate(actions[:10], 1):
                    t.add_row(str(i), str(a.get("action", a))[:70], str(a.get("priority", "")))
                console.print(Panel(t, title="[bold green]Active Goals[/bold green]", border_style="green"))
        except Exception as e:
            console.print(f"[red]Goals error: {e}[/red]")
        return True

    if verb == "/search":
        if not arg:
            console.print("[yellow]Usage: /search <query>[/yellow]")
            return True
        console.print(f"[dim]Searching: {arg}...[/dim]")
        try:
            from agents.districts.research.research_hub import ResearchHub
            hub = ResearchHub()
            results = asyncio.run(hub.search_web(arg, max_results=5))  # noqa: asyncio.run OK in sync handler
            if results:
                for r in results[:5]:
                    console.print(f"  [cyan]{r.get('title', '?')}[/cyan]")
                    console.print(f"  [dim]{r.get('url', '')}[/dim]")
                    console.print(f"  {r.get('snippet', '')[:120]}")
                    console.print()
            else:
                console.print("[dim]No results found.[/dim]")
        except Exception as e:
            console.print(f"[red]Search error: {e}[/red]")
        return True

    if verb == "/note":
        title = arg or f"Quick Note {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        console.print(f"[dim]Note title: {title}[/dim]")
        console.print("[dim]Enter content (blank line to finish):[/dim]")
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
        content = "\n".join(lines)
        if content:
            try:
                from core.memory.obsidian_sync import ObsidianSync
                ObsidianSync().write_note(title=title, content=content, folder="00 Notes", tags=["terminal", "vector"])
                console.print(f"[green]Note '{title}' saved to vault.[/green]")
            except Exception as e:
                console.print(f"[red]Note save error: {e}[/red]")
        return True

    if verb == "/districts":
        districts = [
            ("governance", "LLM Council, Mayor"),
            ("security", "ThreatScout, MalwareHunter"),
            ("coding", "GitBot, CodeReviewer, BugHunter"),
            ("time_calendar", "KIITScraper, DeadlineManager"),
            ("communications", "Hermes, multi-platform"),
            ("memory_curator", "LightRAG, ConsolidationBot"),
            ("research", "WebScout, PaperReader, NewsAggregator"),
            ("intelligence", "PatternDetective, NewsTrends"),
            ("skills", "SkillMapper, GapAnalyst"),
            ("languages", "HI/BN/AS/JA/EN coaches"),
            ("interview_prep", "MockInterviewer, ReportGenerator"),
            ("learning", "VideoIngestor, ConceptExtractor"),
            ("finance", "UPIParser, BudgetAnalyst"),
            ("health", "SleepTracker, FatigueMonitor"),
            ("reflection", "DailyReviewer, JournalWriter"),
            ("startups", "MarketScanner, IdeaValidator"),
            ("investment", "StockAnalyst NSE/BSE"),
            ("content", "ScriptGen, VideoMerger"),
            ("agency", "ClientManager, ContentStrategist"),
            ("karpathy_lab", "30min/day, OpenMythos"),
            ("projects", "ProjectPlanner, DocWriter"),
            ("relationships", "ContactManager, CommAnalyst"),
            ("privacy", "DataFlowAuditor"),
            ("pattern_detective", "BehaviorAnalyst, HabitFinder"),
            ("news_trends", "AINewsBot, OpportunitySpotter"),
        ]
        t = Table(box=box.SIMPLE, padding=(0, 1))
        t.add_column("#", style="dim", width=3)
        t.add_column("District", style="cyan", width=20)
        t.add_column("Agents", style="dim")
        for i, (d, agents) in enumerate(districts, 1):
            t.add_row(str(i), d, agents)
        console.print(Panel(t, title="[bold green]VECTOR — 25 Districts[/bold green]", border_style="green"))
        return True

    if verb == "/council":
        if not arg:
            console.print("[yellow]Usage: /council <high-stakes question>[/yellow]")
            return True
        console.print("[dim]Convening council (this takes 2-5 minutes)...[/dim]")
        try:
            from agents.districts.governance.llm_council import LLMCouncil
            result = asyncio.run(
                LLMCouncil().convene(question=arg, stakes="high", requester_hp=800)
            )
            console.print(Panel(
                Markdown(result.get("verdict", "No verdict.")),
                title=f"[bold green]Council Verdict — Session {result.get('session_id', '?')}[/bold green]",
                border_style="green",
            ))
        except Exception as e:
            console.print(f"[red]Council error: {e}[/red]")
        return True

    if verb == "/karpathy":
        try:
            from agents.districts.karpathy_lab.code_typer import CodeTyper
            typer = CodeTyper()
            streak = typer.get_streak()
            today = typer.get_today_summary()
            console.print(Panel(
                f"[bold green]Streak: {streak} days[/bold green]\n\n{today}",
                title="[bold green]Karpathy Track — RULE 12[/bold green]",
                border_style="green",
            ))
        except Exception as e:
            console.print(f"[red]Karpathy error: {e}[/red]")
        return True

    console.print(f"[yellow]Unknown command: {verb}. Type /help for commands.[/yellow]")
    return True


def _chat_with_vector(user_input: str, history: list[dict], console: "Console") -> str:
    """Send a message to vector-focus, return response text."""
    from core.inference.ollama_safe import chat
    from core.loop.context_engine import ContextEngine
    from core.memory.episodic import EpisodicMemory

    hydration = ContextEngine().session_hydration_prompt()
    messages = [{"role": "system", "content": hydration}]
    messages += history[-10:]  # keep last 10 exchanges for context
    messages.append({"role": "user", "content": user_input})

    response = chat(model=_MODEL, messages=messages, timeout=120.0) or "…"

    # RULE 8 — store in episodic memory
    try:
        mem = EpisodicMemory()
        mem.store(
            event_type="terminal_chat",
            content=f"User: {user_input}\nVECTOR: {response[:500]}",
            tags=["chat", "terminal"],
            source="terminal_ui",
        )
    except Exception:
        pass

    return response


def run_chat() -> None:
    if not _RICH:
        print("ERROR: rich not installed. Run: pip install rich")
        sys.exit(1)

    console = Console()
    _render_header(console)

    history: list[dict] = []

    while True:
        try:
            user_input = Prompt.ask("[bold green]VECTOR[/bold green]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]VECTOR shutting down.[/dim]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.startswith("/"):
            keep_running = _handle_command(user_input, console)
            if not keep_running:
                break
            continue

        # Regular chat
        console.print(f"[dim]  ↳ vector-focus thinking...[/dim]")
        try:
            response = _chat_with_vector(user_input, history, console)
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": response})

            console.print()
            console.print(Panel(
                Markdown(response),
                title="[bold green]VECTOR[/bold green]",
                border_style="green",
                padding=(1, 2),
            ))
            console.print()
        except Exception as e:
            console.print(f"[red]Chat error: {e}[/red]")
            logger.error(f"[VECTOR][chat] {e}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    run_chat()
