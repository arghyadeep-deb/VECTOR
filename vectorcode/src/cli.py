"""
VectorCode CLI — entry point.

Usage:
  vector                           → interactive REPL (Mode A)
  vector run "task"                → one-shot non-interactive
  vector auto "task"               → Mode B (autonomous task queue)
  vector hybrid                    → Mode C (hybrid checkpoint gates)
  vector mcp [--sse]               → start MCP server
  vector status                    → session status
  vector sessions list             → list past sessions
  vector sessions resume <id>      → resume a session
  vector sessions export <id>      → export session as markdown
  vector models list               → list configured models
  vector models test <model>       → test model connection
  vector models set-default <model>→ set default model
  vector models pull <name>        → pull Ollama model
  vector agents list               → list registered agents
  vector agents run <name>         → run a named agent
  vector auth add <name>           → store an API credential
  vector auth list                 → list stored credentials
  vector auth remove <name>        → remove a credential
  vector auth test <name>          → test a credential
  vector auth from-env             → import credentials from environment
  vector profile list              → list named profiles
  vector profile use <name>        → activate a profile
  vector profile show [name]       → show profile details
  vector profile create <name>     → create a new profile
  vector profile delete <name>     → delete a profile
  vector doctor                    → run installation diagnostics

Flags (for repl / run):
  --model <provider/model>         → override model for this session
  --mode  <cautious|standard|autonomous|read-only>
  --dir   <path>                   → project directory (default: CWD)
  --profile <name>                 → use a named profile
"""
import sys
import argparse
import json
from pathlib import Path

# Most subcommands use bare imports (`from session import ...`, `from repl import ...`,
# `from skills.hub import ...`). Those only resolve with vectorcode/src on sys.path, which only
# `tools` set up (via ensure_paths()) -- so `run`, `status`, `sessions`, `skills`, `completion`
# and `plugins` crashed with ModuleNotFoundError when launched via vector.py / vector.bat.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from vectorcode.src.bootstrap import ensure_paths as _ensure_paths
_ensure_paths()


# Suppress INFO/DEBUG logs — only show WARNING+ in interactive CLI
from loguru import logger
logger.remove()
logger.add(sys.stderr, level="WARNING", format="<yellow>[VECTOR]</yellow> {message}")


# ── ANSI constants ────────────────────────────────────────────
R  = "\x1b[0m"
C1 = "\x1b[36m"
C2 = "\x1b[96m"
C3 = "\x1b[94m"
WB = "\x1b[97m\x1b[1m"
DM = "\x1b[2m\x1b[36m"
GR = "\x1b[92m"
AM = "\x1b[93m"

# ── THE LOGO (dense concentric rings + VECTOR beside) ────────
def _print_hud_banner(model_name="", ollama_models=None, has_vectormd=False):
    """Welcome banner — VECTOR pixel mascot (V-core orb) + status, Claude Code style."""
    import sys
    from pathlib import Path

    R  = "\x1b[0m"       # reset
    D  = "\x1b[2m"       # dim
    W  = "\x1b[97;1m"    # white bold

    # Truecolor palette for the mascot
    PAL = {
        "B": (127, 232, 255),  # bright cyan dome
        "C": (63, 184, 214),   # cyan body
        "K": (4, 20, 28),      # dark visor plate
        "V": (95, 216, 242),   # orb ring
        "O": (234, 253, 255),  # orb core (white-hot)
        "G": (157, 255, 176),  # status green
        "A": (127, 232, 255),  # antenna tip
    }

    def _fg(rgb):
        return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"

    def _bg(rgb):
        return f"\x1b[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"

    # 16x14 pixel mascot: dome head, dark visor with glowing core orb, antenna, legs
    sprite = [
        "       AA       ",
        "       CC       ",
        "    BBBBBBBB    ",
        "   BBBBBBBBBB   ",
        "  BBBBBBBBBBBB  ",
        "  CCKKVVVVKKCC  ",
        "  CCKVKKKKVKCC  ",
        "  CCVKKOOKKVCC  ",
        "  CCKVKKKKVKCC  ",
        "  CCKKVVVVKKCC  ",
        "  CCCCCCCCCCCC  ",
        "  CCCCCGCCCCCC  ",
        "   CCCCCCCCCC   ",
        "   CC      CC   ",
    ]

    # Render two pixel rows per text line via the upper half-block (▀):
    # fg paints the top pixel, bg paints the bottom pixel.
    art = []
    for r in range(0, len(sprite), 2):
        top = sprite[r]
        bot = sprite[r + 1] if r + 1 < len(sprite) else " " * len(top)
        line = ""
        for cx in range(len(top)):
            tc = PAL.get(top[cx])
            bc = PAL.get(bot[cx]) if cx < len(bot) else None
            if tc and bc:
                line += _fg(tc) + _bg(bc) + "▀" + R
            elif tc:
                line += _fg(tc) + "▀" + R
            elif bc:
                line += _fg(bc) + "▄" + R
            else:
                line += " "
        art.append(line)

    cwd = str(Path.cwd()).replace(str(Path.home()), "~")
    if len(cwd) > 48:
        cwd = "..." + cwd[-45:]
    mn = (model_name or "vector-focus")[:36]
    n_models = len(ollama_models or [])
    online = (f"{_fg(PAL['G'])}●{R} {D}online{R}" if n_models > 0
              else f"{D}○ offline{R}")
    cyan = _fg(PAL["V"])

    # Text block, vertically centered against the mascot (7 rendered rows)
    right = {
        2: f"{W}VectorCode{R}  {D}v0.1.0{R}",
        3: f"{cyan}{mn}{R}  {D}·{R}  {online}  {D}·{R}  {W}{n_models}{R} {D}models{R}",
        4: f"{D}{cwd}{R}",
    }

    out = sys.stderr
    print(file=out)
    for i, line in enumerate(art):
        print(f"  {line}   {right.get(i, '')}", file=out)
    print(f"  {D}/help{R} {D}·{R} {D}@file{R} {D}·{R} {D}/sparc <task>{R} {D}·{R} {D}/quit{R}", file=out)
    print(file=out)


def _strip_ansi(s: str) -> str:
    """Strip ANSI escape codes for length calculations."""
    import re
    return re.sub(r'\x1b\[[0-9;]*m', '', s)


def cmd_repl(_args):
    from repl import VectorREPL, _fetch_ollama_models

    # Collect startup data
    ollama_models = _fetch_ollama_models()
    model_names = [m.get("name", "") for m in ollama_models]
    vmd_path = Path.cwd() / "VECTOR.md"
    has_vmd = vmd_path.exists()

    # Print HUD banner
    _print_hud_banner("vector-focus", model_names, has_vmd)

    repl = VectorREPL()
    repl.run(skip_startup_banner=True)


def cmd_auto(args):
    task = " ".join(args.task) if args.task else ""
    if not task:
        print("Usage: vector auto \"your task here\"")
        sys.exit(1)
    # Mode B runs the task to completion in the foreground: the old version queued it on a daemon thread
    # and exited immediately, so nothing ever ran (and the "loop" it queued only listed phase names).
    from gsd_loop import GSDLoop
    project_dir = Path(getattr(args, "dir", None) or ".").resolve()
    print(f"[VectorCode] Task: {task}", flush=True)
    outcome = GSDLoop(mode="auto", executor=lambda prompt: _run_agent_task(prompt, project_dir, None)).run(task)
    print(f"[VectorCode] status: {outcome['status']}  phases: {' > '.join(outcome['trace'])}")
    if outcome.get("output"):
        print(outcome["output"])
    if outcome["status"] != "passed":
        sys.exit(1)


def cmd_hybrid(_args):
    from hybrid import VectorHybrid, CheckpointGate
    vh = VectorHybrid()
    _print_hud_banner()
    print("Mode C — Hybrid (checkpoint gates active)")
    print("  PLAN_APPROVAL  : ON")
    print("  RED_ACTION     : ON")
    print("  DESTRUCTIVE_EDIT: ON")
    print("\nSwitch to REPL for interactive use:")
    from repl import VectorREPL
    repl = VectorREPL()
    repl.session.set_mode("hybrid")
    repl.run()


def cmd_mcp(args):
    import subprocess
    mcp_script = Path(__file__).parent.parent.parent / "core" / "mcp_server.py"
    cmd = [sys.executable, str(mcp_script)]
    if getattr(args, "sse", False):
        port = getattr(args, "port", 9000)
        cmd += ["--transport", "sse", "--port", str(port)]
    print(f"[VectorCode] Starting MCP server ({' '.join(cmd[2:] or ['stdio'])})")
    subprocess.run(cmd)


def _run_agent_task(task: str, project_dir: Path, model: "str | None") -> str:
    from agent_task import run_agent_task
    return run_agent_task(task, project_dir, model)


def _run_ipc(args):
    """JSON stdin/stdout IPC mode for VECTOR bridge."""
    import json
    try:
        data = json.loads(sys.stdin.read())
    except Exception as e:
        json.dump({"status": "error", "output": f"IPC parse error: {e}", "exit_code": -1}, sys.stdout)
        sys.stdout.flush()
        return
    task = data.get("task", "").strip()
    if not task:
        json.dump({"status": "error", "output": "Empty task", "exit_code": -1}, sys.stdout)
        sys.stdout.flush()
        return

    project_dir = Path(getattr(args, "dir", None) or ".").resolve()
    try:
        reply = _run_agent_task(task, project_dir, getattr(args, "model", None))
    except Exception as e:
        json.dump({"status": "error", "output": f"agent could not run the task: {e}", "exit_code": 1}, sys.stdout)
        sys.stdout.flush()
        return

    json.dump({"status": "ok", "output": reply, "exit_code": 0}, sys.stdout)
    sys.stdout.flush()


def cmd_run(args):
    if getattr(args, "ipc", False):
        _run_ipc(args)
        return
    """One-shot non-interactive task. Reads from stdin if no task given."""
    import select
    task = " ".join(args.task) if getattr(args, "task", None) else ""

    # Support pipe: cat error.log | vector run "explain this"
    if not task:
        stdin_data = ""
        try:
            if not sys.stdin.isatty():
                stdin_data = sys.stdin.read()
        except Exception as _sve:
            logger.debug("[VECTOR][cli] suppressed Exception: {}", _sve)
        if stdin_data:
            task = stdin_data.strip()

    if not task:
        print("Usage: vector run \"your task here\"  OR  cat file | vector run")
        sys.exit(1)

    project_dir = Path(getattr(args, "dir", None) or ".").resolve()
    model_override = getattr(args, "model", None)
    mode_override  = getattr(args, "mode",  None)

    if mode_override:
        try:
            from session import VectorCodeSession
            VectorCodeSession.get().set_mode(mode_override)
        except ValueError as e:
            print(f"[VECTOR] {e}")

    try:
        reply = _run_agent_task(task, project_dir, model_override)
    except Exception as e:
        print(f"[VectorCode] the agent could not run this task: {e}", file=sys.stderr)
        sys.exit(1)
    print(reply)


def cmd_status(_args):
    from session import VectorCodeSession
    s = VectorCodeSession.get()
    print(f"Mode    : {s.mode}")
    print(f"Model   : {s.current_model}")
    print(f"Task    : {s.task_id or 'none'}")
    print(f"History : {len(s.history)} entries")
    print(f"Agents  : {len(s.active_agents)} active")
    print(f"Tokens  : {s.token_usage.total_tokens} (${s.cost_usd:.4f})")


# ── Sessions subcommands ───────────────────────────────────────────────────────

def cmd_sessions(args):
    from config import SESSION_DIR

    action = getattr(args, "action", "list") or "list"

    if action == "list":
        # Prefer session_db for richer stats; fallback to JSON files
        _printed_from_db = False
        try:
            from vectorcode.session_db import get_session_db
            db = get_session_db()
            rows = db.list_sessions(limit=20)
            if rows:
                print(f"{'ID':<38}  {'Date':<20}  {'Model':<28}  {'Tokens':>8}  Cost")
                print("-" * 110)
                for r in rows:
                    sid   = (r.get("id") or "")[:36]
                    date  = (r.get("started_at") or "")[:19]
                    model = (r.get("model") or "?")[:26]
                    inp   = r.get("input_tokens") or 0
                    out   = r.get("output_tokens") or 0
                    total_tok = inp + out
                    cost  = f"${r.get('cost_usd', 0) or 0:.4f}"
                    print(f"{sid:<38}  {date:<20}  {model:<28}  {total_tok:>8,}  {cost}")
                _printed_from_db = True
        except Exception as _sve:
            logger.debug("[VECTOR][cli] suppressed Exception: {}", _sve)

        if not _printed_from_db:
            if not SESSION_DIR.exists():
                print("No sessions found.")
                return
            sessions = sorted(SESSION_DIR.glob("*.json"), reverse=True)[:20]
            if not sessions:
                print("No sessions found.")
                return
            print(f"{'ID':<38}  {'Date':<20}  {'Model':<30}  Cost")
            print("-" * 100)
            for s_path in sessions:
                try:
                    data = json.loads(s_path.read_text(encoding="utf-8"))
                    sid   = data.get("id", s_path.stem)[:36]
                    date  = data.get("created_at", "")[:19]
                    model = data.get("model", "?")[:28]
                    cost  = f"${data.get('cost_usd', 0):.4f}"
                    print(f"{sid:<38}  {date:<20}  {model:<30}  {cost}")
                except Exception:
                    print(f"  {s_path.name} (unreadable)")

    elif action == "resume":
        session_id = getattr(args, "id", None)
        if not session_id:
            print("Usage: vector sessions resume <session-id>")
            return
        target = SESSION_DIR / f"{session_id}.json"
        if not target.exists():
            # Try prefix match
            matches = list(SESSION_DIR.glob(f"{session_id}*.json"))
            if not matches:
                print(f"Session not found: {session_id}")
                return
            target = matches[0]
        data = json.loads(target.read_text(encoding="utf-8"))
        from repl import VectorREPL
        _print_hud_banner()
        repl = VectorREPL()
        repl._history = data.get("messages", [])
        repl.session.current_model = data.get("model", repl.session.current_model)
        print(f"  Resumed session {data.get('id', '')[:8]}... ({len(repl._history)} messages)\n")
        repl.run()

    elif action == "export":
        session_id = getattr(args, "id", None)
        if not session_id:
            print("Usage: vector sessions export <session-id> [--format markdown|html|json]")
            return
        fmt = getattr(args, "export_format", "markdown") or "markdown"

        # Try session_db first for richer export
        _exported = False
        try:
            from vectorcode.session_db import get_session_db
            db = get_session_db()
            if fmt == "markdown":
                content = db.export_markdown(session_id)
                print(content)
                _exported = True
            elif fmt == "html":
                md = db.export_markdown(session_id)
                print(f"<html><body><pre>{md}</pre></body></html>")
                _exported = True
            elif fmt == "json":
                msgs = db.get_context_window(session_id)
                print(json.dumps(msgs, indent=2, ensure_ascii=False))
                _exported = True
        except Exception as _sve:
            logger.debug("[VECTOR][cli] suppressed Exception: {}", _sve)

        if not _exported:
            # Fallback: JSON file export
            target = SESSION_DIR / f"{session_id}.json"
            if not target.exists():
                matches = list(SESSION_DIR.glob(f"{session_id}*.json"))
                if not matches:
                    print(f"Session not found: {session_id}")
                    return
                target = matches[0]
            data = json.loads(target.read_text(encoding="utf-8"))
            messages = data.get("messages", [])

            if fmt == "json":
                print(json.dumps(messages, indent=2, ensure_ascii=False))
            else:
                lines = [
                    "# VectorCode Session Export",
                    "",
                    f"**ID:** {data.get('id', '')}  ",
                    f"**Date:** {data.get('created_at', '')}  ",
                    f"**Model:** {data.get('model', '')}  ",
                    f"**Project:** {data.get('project', '')}  ",
                    f"**Cost:** ${data.get('cost_usd', 0):.4f}  ",
                    "",
                    "---",
                    "",
                ]
                for msg in messages:
                    role = msg.get("role", "?")
                    content = msg.get("content", "")
                    if role == "system":
                        continue
                    lines.append(f"**{role.title()}:** {content}")
                    lines.append("")
                md_text = "\n".join(lines)
                if fmt == "html":
                    print(f"<html><body><pre>{md_text}</pre></body></html>")
                else:
                    print(md_text)

    else:
        print(f"Unknown sessions action: {action}")


# ── Models subcommands ─────────────────────────────────────────────────────────

def cmd_models(args):
    action = getattr(args, "action", "list") or "list"

    if action == "list":
        from providers import ModelRouter
        from config import VectorConfig
        cfg = VectorConfig()
        router = ModelRouter()
        print("Configured models:")
        for key in ("default", "fast", "local"):
            m = cfg.get("model", key, default="(not set)")
            print(f"  {key:<10}: {m}")
        print("\nConfigured providers:")
        providers_cfg = cfg.get("providers", default={})
        for name in (providers_cfg or {}).keys():
            print(f"  {name}")

    elif action == "test":
        model_id = getattr(args, "model_id", None)
        if not model_id:
            print("Usage: vector models test <provider/model>")
            return
        from providers import ModelRouter
        router = ModelRouter()
        print(f"Testing {model_id}...", flush=True)
        result = router.test_connection(model_id)
        status = "✓ OK" if result.get("ok") else "✗ FAILED"
        print(f"  {status}  latency={result.get('latency_ms', -1)}ms")
        if not result.get("ok"):
            print(f"  Error: {result.get('error', result.get('response', ''))}")

    elif action == "set-default":
        model_id = getattr(args, "model_id", None)
        if not model_id:
            print("Usage: vector models set-default <provider/model>")
            return
        from config import GLOBAL_CONFIG_PATH, GLOBAL_CONFIG_DIR
        GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        content = ""
        if GLOBAL_CONFIG_PATH.exists():
            content = GLOBAL_CONFIG_PATH.read_text(encoding="utf-8")
        import re
        if re.search(r'^\s*default\s*=', content, re.M):
            content = re.sub(r'(^\s*default\s*=\s*")[^"]*"', f'\\g<1>{model_id}"', content, flags=re.M)
        else:
            content += f'\n[model]\ndefault = "{model_id}"\n'
        GLOBAL_CONFIG_PATH.write_text(content, encoding="utf-8")
        print(f"Default model set to: {model_id}")

    elif action == "pull":
        model_name = getattr(args, "model_id", None)
        if not model_name:
            print("Usage: vector models pull <ollama-model-name>")
            return
        import subprocess
        print(f"Pulling {model_name} via Ollama...")
        subprocess.run(["ollama", "pull", model_name])

    else:
        print(f"Unknown models action: {action}")


# ── Agents subcommands ─────────────────────────────────────────────────────────

def cmd_agents(args):
    action = getattr(args, "action", "list") or "list"

    if action == "list":
        try:
            from core.city.agent_registry import get_registry
            agents = get_registry().list_all()
            if not agents:
                print("No agents registered.")
                return
            print(f"{'Name':<30}  {'District':<20}  {'HP':<6}  Model")
            print("-" * 80)
            for a in agents:
                print(f"  {a.get('name','?'):<28}  {a.get('district','?'):<20}  {a.get('health_points','?'):<6}  {a.get('model','?')}")
        except Exception as e:
            print(f"[VECTOR] Could not list agents: {e}")

    elif action == "run":
        agent_name = getattr(args, "agent_name", None)
        if not agent_name:
            print("Usage: vector agents run <agent-name>")
            return
        try:
            from core.city.agent_registry import get_registry
            reg = get_registry()
            agent = reg.get(agent_name)
            if not agent:
                print(f"Agent not found: {agent_name}")
                return
            print(f"[VECTOR] Running agent: {agent_name}")
        except Exception as e:
            print(f"[VECTOR] Agent run failed: {e}")

    else:
        print(f"Unknown agents action: {action}")


def cmd_skills(args):
    """Handle `vector skills` subcommands."""
    from skills.hub import get_skills_hub
    hub = get_skills_hub()
    skills_action = getattr(args, "skills_action", None)

    if skills_action == "list":
        packs = hub.list_packs()
        if not packs:
            print("No skill packs installed.")
            print("Install one with: vector skills install <git-url-or-local-path>")
        else:
            print(f"{'Pack':<28}  {'Skills':>6}  Source")
            print("-" * 72)
            for p in packs:
                print(f"  {p.name:<26}  {p.skill_count:>6}  {p.source}")

    elif skills_action == "search":
        query = getattr(args, "query", "")
        results = hub.search(query)
        if not results:
            print(f"No skills found for query: {query!r}")
        else:
            for r in results:
                desc = r.get("description", "")
                desc_str = f": {desc}" if desc else ""
                print(f"  [{r['pack']}] {r['skill']}{desc_str}")

    elif skills_action == "install":
        source = getattr(args, "source", "")
        name = getattr(args, "name", None)
        try:
            result = hub.install(source, name)
            print(f"Installed '{result['name']}': {result['skill_count']} skill file(s) at {result['path']}")
        except Exception as e:
            print(f"[VECTOR] Install failed: {e}")

    elif skills_action == "uninstall":
        name = getattr(args, "name", "")
        result = hub.uninstall(name)
        if result.get("success"):
            print(f"Removed skill pack: {name}")
        else:
            print(f"[VECTOR] {result.get('error', 'Uninstall failed')}")

    elif skills_action == "sync":
        name = getattr(args, "name", None)
        result = hub.sync(name)
        synced = result.get("synced", [])
        errors = result.get("errors", [])
        if synced:
            print(f"Synced: {', '.join(synced)}")
        if errors:
            for err in errors:
                print(f"  [error] {err}")
        if not synced and not errors:
            print("Nothing to sync.")

    else:
        # Print skills sub-help
        print("Usage: vector skills <list|search|install|uninstall|sync>")
        print("  list                       List installed skill packs")
        print("  search <query>             Search skills by keyword")
        print("  install <source> [--name]  Install from git URL or local path")
        print("  uninstall <name>           Remove a skill pack")
        print("  sync [--name <pack>]       Git pull update(s)")


def cmd_auth(args):
    """Handle `vector auth` subcommands."""
    from cli.auth import handle_auth
    handle_auth(args)


def cmd_profile(args):
    """Handle `vector profile` subcommands."""
    from cli.profiles import handle_profile
    handle_profile(args)


def cmd_doctor(_args):
    """Handle `vector doctor` subcommand."""
    from cli.doctor import run_doctor
    run_doctor()


def cmd_completion(args):
    """Handle `vector completion` subcommand."""
    from cli.completion import get_completion_script, auto_install, get_install_instructions

    do_install = getattr(args, "install", False)
    shell = getattr(args, "shell", None)

    if do_install:
        msg = auto_install(shell)
        print(msg)
        return

    if shell:
        script = get_completion_script(shell)
        if script:
            print(script)
        else:
            print(get_install_instructions(shell))
    else:
        # No shell specified — print instructions for all shells
        print("Shell completion for `vector`")
        print()
        for sh in ("bash", "zsh", "fish"):
            print(f"  {sh}:")
            print(f"    {get_install_instructions(sh)}")
            print()


def cmd_usage(args):
    """Print usage analytics from session DB."""
    days = getattr(args, "days", 30) or 30
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 30
    try:
        from insights import InsightsEngine
        print(InsightsEngine().format_terminal(days=days))
    except Exception as e:
        print(f"[VECTOR] usage error: {e}")


def cmd_gateway(args):
    """Start the HTTP gateway server."""
    action = getattr(args, "action", "start") or "start"
    host = getattr(args, "host", "127.0.0.1") or "127.0.0.1"
    port = int(getattr(args, "port", 8123) or 8123)

    if action == "start":
        from vectorcode.gateway.server import GatewayServer
        import asyncio
        gw = GatewayServer(host=host, port=port)
        print(f"[VECTOR] Starting gateway on http://{host}:{port}")
        asyncio.run(gw.start())
    elif action == "status":
        import httpx
        try:
            r = httpx.get(f"http://{host}:{port}/status", timeout=3)
            print(r.json())
        except Exception as e:
            print(f"[VECTOR] Gateway not reachable: {e}")


def cmd_auth(args):
    """Manage API credentials (auth add/remove/list/test/from-env)."""
    action = getattr(args, "action", "list") or "list"
    import sys
    from pathlib import Path
    try:
        # Try the rich VectorCode auth module
        from vector_cli import auth_commands as _auth_cmds
        # The module's real function names are auth_<action>_command; the old cmd_auth_<action> names
        # never existed, so every `vector auth <action>` raised AttributeError.
        handlers = {
            "add": "auth_add_command", "list": "auth_list_command", "remove": "auth_remove_command",
            "test": "auth_status_command", "status": "auth_status_command",
            "reset": "auth_reset_command", "logout": "auth_logout_command",
        }
        handler = getattr(_auth_cmds, handlers.get(action, ""), None)
        if handler is not None:
            return handler(args)
        print(f"[VECTOR] Unknown or unsupported auth action: {action}")
        print("  Available: add, remove, list, test, status, reset, logout")
    except ImportError as e:
        # Fallback: use basic credentials.py module
        try:
            from credentials import CredentialManager
            cm = CredentialManager.global_instance() if hasattr(CredentialManager, "global_instance") else None
            if action == "list":
                if cm and hasattr(cm, "list_all_creds"):
                    creds = cm.list_all_creds()
                    if creds:
                        print(f"Credentials ({len(creds)}):")
                        for c in creds:
                            print(f"  {c}")
                    else:
                        print("No credentials stored.")
                else:
                    print("[VECTOR] auth list: credential manager unavailable")
            else:
                print(f"[VECTOR] auth {action}: requires vector_cli.auth_commands ({e})")
        except Exception as ex:
            print(f"[VECTOR] auth error: {ex}")


def cmd_profile(args):
    """Manage named profiles."""
    action = getattr(args, "profile_action", "list") or "list"
    import sys
    from pathlib import Path
    try:
        from vector_cli import profiles as _profiles
        if action == "list":
            return _profiles.cmd_profile_list(args) if hasattr(_profiles, "cmd_profile_list") else _profiles.list_profiles()
        elif action == "use":
            return _profiles.cmd_profile_use(args) if hasattr(_profiles, "cmd_profile_use") else _profiles.use_profile(args.name)
        elif action == "show":
            return _profiles.cmd_profile_show(args) if hasattr(_profiles, "cmd_profile_show") else _profiles.show_profile(getattr(args, "name", None))
        elif action == "create":
            return _profiles.cmd_profile_create(args) if hasattr(_profiles, "cmd_profile_create") else None
        elif action == "delete":
            return _profiles.cmd_profile_delete(args) if hasattr(_profiles, "cmd_profile_delete") else None
        else:
            print(f"[VECTOR] Unknown profile action: {action}")
    except ImportError as e:
        print(f"[VECTOR] profile {action}: {e}")
    except AttributeError:
        # Module exists but functions don't — list available
        try:
            from vector_cli import profiles as _profiles
            funcs = [x for x in dir(_profiles) if not x.startswith("_") and callable(getattr(_profiles, x))]
            print(f"[VECTOR] profile module loaded. Available: {', '.join(funcs[:10])}")
        except Exception as ex:
            print(f"[VECTOR] profile error: {ex}")


def cmd_doctor(args):
    """Run diagnostics — comprehensive system + dependency check."""
    import sys, shutil, os
    from pathlib import Path

    print()
    print("VectorCode Doctor")
    print("=" * 60)

    # Python checks
    py_ok = sys.version_info >= (3, 11)
    print(f"  [{'OK' if py_ok else 'FAIL'}] Python 3.11+    : {sys.version.split()[0]}")

    # Required binaries
    for binary, required in [("ollama", False), ("git", True), ("docker", False)]:
        found = shutil.which(binary) is not None
        marker = "OK" if found else ("FAIL" if required else "WARN")
        print(f"  [{marker:<4}] {binary:<13}: {'installed' if found else 'not found'}")

    # Check ollama daemon
    try:
        import urllib.request, json as _json
        r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        data = _json.loads(r.read().decode())
        n = len(data.get("models", []))
        print(f"  [OK]   Ollama daemon: running ({n} models)")
    except Exception:
        print(f"  [WARN] Ollama daemon: not reachable on localhost:11434")

    # Required deps
    print()
    print("Python dependencies:")
    deps = ["loguru", "fastapi", "uvicorn", "pydantic", "httpx", "anthropic", "openai"]
    for dep in deps:
        try:
            __import__(dep)
            print(f"  [OK]   {dep}")
        except ImportError:
            print(f"  [FAIL] {dep:<20} (run: pip install {dep})")

    # VectorCode core
    print()
    print("VectorCode core:")
    for mod in ["engine", "tools.registry", "providers", "session_db", "credentials", "memory.manager"]:
        try:
            __import__(mod)
            print(f"  [OK]   {mod}")
        except Exception as e:
            print(f"  [FAIL] {mod:<25} ({e})")

    # Env vars
    print()
    print("Environment:")
    env_vars = ["VECTOR_HOME", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "OLLAMA_BASE_URL"]
    for v in env_vars:
        val = os.environ.get(v, "")
        if val:
            mask = val[:5] + "..." if len(val) > 8 else "set"
            print(f"  [OK]   {v:<22} = {mask}")
        else:
            print(f"  [--]   {v:<22} (not set)")

    print()
    print("=" * 60)


def cmd_vector_cli_dispatch(module_name: str):
    """Generic dispatcher: invoke any vector_cli/<module>.py main()/cli() if exposed."""
    def _dispatch(args):
        import sys, importlib
        from pathlib import Path
        try:
            mod = importlib.import_module(f"vector_cli.{module_name}")
        except ImportError as e:
            print(f"[VECTOR] {module_name}: module not found ({e})")
            return 1
        # Try common entry points in order of preference
        for entry in ("main", "cli", "run", "execute", f"cmd_{module_name}", "handle"):
            if hasattr(mod, entry):
                fn = getattr(mod, entry)
                if callable(fn):
                    try:
                        # Try with args first
                        try:
                            return fn(args)
                        except TypeError:
                            # Then without
                            return fn()
                    except SystemExit:
                        return 0
                    except Exception as e:
                        print(f"[VECTOR] {module_name}.{entry}() failed: {e}")
                        return 1
        # No standard entry — print module info
        funcs = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        print(f"[VECTOR] {module_name}: no main/cli entry. Public functions: {funcs[:8]}")
        return 0
    return _dispatch


def cmd_self_update(args):
    """Upgrade VectorCode to the latest version."""
    import sys
    from pathlib import Path
    try:
        from cli.self_update import self_update
        docker = getattr(args, "docker", False)
        exit_code = self_update(docker=docker)
        sys.exit(exit_code)
    except ImportError:
        import subprocess
        print("[VECTOR] Upgrading via pip...")
        subprocess.call([sys.executable, "-m", "pip", "install", "--upgrade", "vectorcode"])


def cmd_version(_args):
    """Print VectorCode version."""
    import sys
    from pathlib import Path
    try:
        from cli.self_update import get_current_version
        print(f"vectorcode {get_current_version()}")
    except Exception:
        print("vectorcode 0.1.0")


def cmd_cron(args):
    """Manage scheduled cron jobs (uses ~/.vectorcode/cron.db)."""
    action = getattr(args, "action", "list") or "list"
    import sys, sqlite3, json
    from pathlib import Path

    db_path = Path.home() / ".vectorcode" / "cron.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    def _conn():
        c = sqlite3.connect(str(db_path), check_same_thread=False)
        c.execute("""CREATE TABLE IF NOT EXISTS cron_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule TEXT NOT NULL,
            prompt TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            last_run TEXT,
            run_count INTEGER DEFAULT 0
        )""")
        return c

    if action == "add":
        with _conn() as c:
            cur = c.execute("INSERT INTO cron_jobs (schedule, prompt) VALUES (?, ?)",
                            (args.schedule, args.prompt))
            c.commit()
            print(f"Added cron job #{cur.lastrowid}: {args.schedule} -> {args.prompt[:60]}")

    elif action == "list":
        with _conn() as c:
            rows = c.execute("SELECT id, schedule, prompt, enabled, last_run, run_count "
                             "FROM cron_jobs ORDER BY id").fetchall()
        if not rows:
            print("No cron jobs scheduled.")
            return
        print(f"Cron jobs ({len(rows)}):")
        for (jid, sched, prompt, enabled, last_run, run_count) in rows:
            status = "[ON]" if enabled else "[OFF]"
            last = f" last={last_run}" if last_run else ""
            print(f"  #{jid} {status} {sched:<14} runs={run_count}{last}  -> {prompt[:50]}")

    elif action == "remove":
        with _conn() as c:
            c.execute("DELETE FROM cron_jobs WHERE id = ?", (args.id,))
            c.commit()
            print(f"Removed cron job #{args.id}")

    elif action == "daemon":
        print("[VECTOR] Cron daemon not implemented in this build")


def cmd_acp(args):
    """ACP protocol server."""
    action = getattr(args, "action", "serve") or "serve"
    host = getattr(args, "host", "127.0.0.1") or "127.0.0.1"
    port = int(getattr(args, "port", 8765) or 8765)
    if action == "serve":
        from vectorcode.acp.server import ACPServer
        import asyncio
        srv = ACPServer(host=host, port=port)
        print(f"[VECTOR] Starting ACP server on http://{host}:{port}")
        asyncio.run(srv.start())


def cmd_plugins(args):
    """Manage plugins."""
    action = getattr(args, "action", "list") or "list"
    import sys
    from pathlib import Path
    if action == "list":
        from plugins.loader import discover_plugins
        plugins = discover_plugins()
        if not plugins:
            print("No plugins installed. Add plugins to ~/.vectorcode/plugins/")
        for p in plugins:
            print(f"  {p.name}")
    elif action == "install":
        print(f"[VECTOR] Plugin install: {getattr(args, 'source', '?')} (not yet implemented)")


def cmd_tools(args):
    """List registered tools."""
    action = getattr(args, "action", "list") or "list"
    if action == "list":
        from vectorcode.src.bootstrap import ensure_paths
        ensure_paths()

        # Import tools to trigger self-registration (use discovery from registry)
        from tools.registry import registry, discover_builtin_tools
        try:
            discover_builtin_tools()
        except Exception as _sve:
            logger.debug("[VECTOR][cli] suppressed Exception: {}", _sve)

        names = sorted([e.name for e in registry._snapshot_entries()])
        print(f"Registered tools ({len(names)}):")
        for name in names:
            entry = registry.get_entry(name)
            toolset = getattr(entry, "toolset", "?") if entry else "?"
            print(f"  {name:<30} [{toolset}]")


def main():
    parser = argparse.ArgumentParser(
        prog="vector",
        description="VectorCode — VECTOR's local coding agent",
    )
    # Global flags (apply to repl + run)
    parser.add_argument("--model",   default=None, help="Override model (e.g. anthropic/claude-sonnet-4-6)")
    parser.add_argument("--mode",    default=None, help="Permission mode: cautious|standard|autonomous|read-only")
    parser.add_argument("--dir",     default=None, help="Project directory (default: current dir)")
    parser.add_argument("--profile", default="",   help="Use a named profile (e.g. work, research, readonly)")

    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("repl",   help="Mode A: interactive terminal REPL (default)")

    run_p = sub.add_parser("run", help="One-shot non-interactive task")
    run_p.add_argument("task", nargs="*", help="Task description (or pipe via stdin)")
    run_p.add_argument("--model", default=None)
    run_p.add_argument("--mode",  default=None)
    run_p.add_argument("--dir",   default=None)
    run_p.add_argument("--ipc", action="store_true", help="JSON IPC mode: read task from stdin, write result to stdout")

    auto_p = sub.add_parser("auto", help="Mode B: autonomous single task")
    auto_p.add_argument("task", nargs="*", help="Task description")

    sub.add_parser("hybrid", help="Mode C: hybrid with checkpoint gates")

    mcp_p = sub.add_parser("mcp", help="Start MCP server")
    mcp_p.add_argument("--sse", action="store_true", help="Use SSE transport")
    mcp_p.add_argument("--port", type=int, default=9000, help="SSE port (default: 9000)")

    sub.add_parser("status", help="Show current session status")

    # sessions subcommand
    sess_p = sub.add_parser("sessions", help="Manage past sessions")
    sess_sub = sess_p.add_subparsers(dest="action")
    sess_sub.add_parser("list", help="List past sessions")
    resume_p = sess_sub.add_parser("resume", help="Resume a session by ID")
    resume_p.add_argument("id", help="Session ID (or prefix)")
    export_p = sess_sub.add_parser("export", help="Export session as Markdown/HTML/JSON")
    export_p.add_argument("id", help="Session ID (or prefix)")
    export_p.add_argument(
        "--format", dest="export_format",
        choices=["markdown", "html", "json"], default="markdown",
        help="Output format (default: markdown)"
    )

    # models subcommand
    models_p = sub.add_parser("models", help="Manage model providers")
    models_sub = models_p.add_subparsers(dest="action")
    models_sub.add_parser("list", help="List configured models and providers")
    test_mp = models_sub.add_parser("test", help="Test a model connection")
    test_mp.add_argument("model_id", help="e.g. ollama/vector-focus")
    setdef_p = models_sub.add_parser("set-default", help="Set the default model")
    setdef_p.add_argument("model_id", help="e.g. anthropic/claude-sonnet-4-6")
    pull_p = models_sub.add_parser("pull", help="Pull a model via Ollama")
    pull_p.add_argument("model_id", help="Model name e.g. qwen2.5-coder:32b")

    # agents subcommand
    agents_p = sub.add_parser("agents", help="Manage VECTOR agents")
    agents_sub = agents_p.add_subparsers(dest="action")
    agents_sub.add_parser("list", help="List registered agents")
    run_ap = agents_sub.add_parser("run", help="Run a named agent")
    run_ap.add_argument("agent_name", help="Agent name")

    # skills subcommand
    skills_p = sub.add_parser("skills", help="Skill pack management")
    skills_sub = skills_p.add_subparsers(dest="skills_action")
    skills_sub.add_parser("list", help="List all installed skill packs and skills")
    skills_search_p = skills_sub.add_parser("search", help="Search skills by keyword")
    skills_search_p.add_argument("query", help="Search query")
    skills_install_p = skills_sub.add_parser("install", help="Install skill pack from git URL or local path")
    skills_install_p.add_argument("source", help="Git URL or local directory path")
    skills_install_p.add_argument("--name", default=None, help="Override pack name (default: derived from source)")
    skills_uninstall_p = skills_sub.add_parser("uninstall", help="Uninstall a skill pack")
    skills_uninstall_p.add_argument("name", help="Pack name to remove")
    skills_sync_p = skills_sub.add_parser("sync", help="Sync (git pull) installed packs")
    skills_sync_p.add_argument("--name", default=None, help="Pack name to sync (omit for all)")

    # completion subcommand
    completion_p = sub.add_parser("completion", help="Generate shell completion scripts")
    completion_p.add_argument(
        "shell", nargs="?", choices=["bash", "zsh", "fish"],
        help="Shell type (bash/zsh/fish)"
    )
    completion_p.add_argument(
        "--install", action="store_true",
        help="Auto-detect shell and install completions"
    )

    # usage subcommand
    usage_p = sub.add_parser("usage", help="Show token + cost analytics")
    usage_p.add_argument("--days", type=int, default=30,
                         help="Number of days to include (default: 30)")

    # auth subcommand
    auth_p = sub.add_parser("auth", help="Manage API credentials")
    auth_sub = auth_p.add_subparsers(dest="auth_action")
    auth_add = auth_sub.add_parser("add", help="Add credential")
    auth_add.add_argument("name", help="Credential name (e.g. openai-work)")
    auth_add.add_argument("--provider", required=True,
                          help="Provider (anthropic/openai/ollama/gemini/groq/…)")
    auth_add.add_argument("--key", default=None,
                          help="API key (prompted securely if omitted)")
    auth_sub.add_parser("list", help="List stored credentials")
    auth_remove = auth_sub.add_parser("remove", help="Remove a credential")
    auth_remove.add_argument("name")
    auth_test = auth_sub.add_parser("test", help="Test a credential by probing the provider API")
    auth_test.add_argument("name")
    auth_sub.add_parser("from-env",
                        help="Import credentials from known environment variables")

    # profile subcommand
    profile_p = sub.add_parser("profile", help="Manage named profiles")
    profile_sub = profile_p.add_subparsers(dest="profile_action")
    profile_sub.add_parser("list", help="List all profiles")
    profile_use = profile_sub.add_parser("use", help="Activate a profile")
    profile_use.add_argument("name")
    profile_show = profile_sub.add_parser("show", help="Show profile details")
    profile_show.add_argument("name", nargs="?", default=None,
                              help="Profile name (default: currently active)")
    profile_create = profile_sub.add_parser("create", help="Create a new profile")
    profile_create.add_argument("name")
    profile_create.add_argument("--model",   default="",
                                help="Model override (e.g. ollama/vector-coder)")
    profile_create.add_argument("--mode",    default="standard",
                                choices=["cautious", "standard", "autonomous", "read-only"],
                                help="Permission mode (default: standard)")
    profile_create.add_argument("--toolset", default="full",
                                choices=["full", "coding", "research", "readonly"],
                                help="Toolset (default: full)")
    profile_create.add_argument("--description", default="",
                                help="Short description")
    profile_delete = profile_sub.add_parser("delete", help="Delete a profile")
    profile_delete.add_argument("name")

    # doctor subcommand
    sub.add_parser("doctor", help="Run diagnostics and health checks")

    # gateway subcommand
    gw_p = sub.add_parser("gateway", help="HTTP gateway server")
    gw_sub = gw_p.add_subparsers(dest="action")
    gw_start = gw_sub.add_parser("start", help="Start the gateway")
    gw_start.add_argument("--host", default="127.0.0.1")
    gw_start.add_argument("--port", type=int, default=8123)
    gw_sub.add_parser("status", help="Check gateway status")

    # tools subcommand
    tools_p = sub.add_parser("tools", help="List registered tools")
    tools_sub = tools_p.add_subparsers(dest="action")
    tools_sub.add_parser("list", help="List all registered tools")

    # cron subcommand
    cron_p = sub.add_parser("cron", help="Manage scheduled tasks")
    cron_sub = cron_p.add_subparsers(dest="action")
    cron_add_p = cron_sub.add_parser("add", help="Add a cron job")
    cron_add_p.add_argument("schedule", help="Cron expression e.g. '0 9 * * *'")
    cron_add_p.add_argument("prompt", help="Task to run")
    cron_sub.add_parser("list", help="List cron jobs")
    cron_rm = cron_sub.add_parser("remove", help="Remove a cron job")
    cron_rm.add_argument("id", type=int)
    cron_daemon = cron_sub.add_parser("daemon", help="Cron daemon control")
    cron_daemon.add_argument("daemon_action", choices=["start", "stop"], default="start", nargs="?")

    # acp subcommand
    acp_p = sub.add_parser("acp", help="ACP protocol server")
    acp_sub = acp_p.add_subparsers(dest="action")
    acp_serve = acp_sub.add_parser("serve", help="Start ACP server")
    acp_serve.add_argument("--host", default="127.0.0.1")
    acp_serve.add_argument("--port", type=int, default=8765)

    # plugins subcommand
    plugins_p = sub.add_parser("plugins", help="Manage plugins")
    plugins_sub = plugins_p.add_subparsers(dest="action")
    plugins_sub.add_parser("list", help="List installed plugins")
    plugins_install = plugins_sub.add_parser("install", help="Install a plugin")
    plugins_install.add_argument("source", help="Plugin directory or git URL")

    # self-update subcommand
    update_p = sub.add_parser("self-update", help="Upgrade VectorCode to latest version")
    update_p.add_argument("--docker", action="store_true", help="Pull latest Docker image instead")

    # version subcommand
    sub.add_parser("version", help="Print VectorCode version")

    # ── Wired vector_cli subcommands (catch-all signature) ──────────────────
    _vc_subs = [
        ("backup", "Backup VectorCode state"),
        ("banner", "Print VectorCode banner"),
        ("claw", "Claw integration"),
        ("clipboard", "Clipboard helper"),
        ("copilot-auth", "GitHub Copilot OAuth flow"),
        ("curses-ui", "Full-screen curses TUI"),
        ("debug", "Debug helpers"),
        ("dingtalk-auth", "DingTalk OAuth flow"),
        ("dump", "Dump session/state to JSON"),
        ("fallback", "Configure fallback model"),
        ("hooks", "Plugin hooks management"),
        ("logs", "View VectorCode logs"),
        ("mcp-config", "Configure MCP servers"),
        ("memory-setup", "Initialize memory provider"),
        ("model-catalog", "Browse model catalog"),
        ("model-normalize", "Normalize model identifiers"),
        ("model-switch", "Switch active model"),
        ("nous-subscription", "Manage Nous Research subscription"),
        ("oneshot", "Non-interactive task execution"),
        ("pairing", "Device pairing flow"),
        ("platforms", "List supported platforms"),
        ("plugins-cmd", "Plugin command surface"),
        ("providers", "Manage provider configs"),
        ("pty-bridge", "PTY bridge for terminal multiplexing"),
        ("runtime-provider", "Runtime provider config"),
        ("setup", "Initial setup wizard"),
        ("skills-config", "Configure skills per platform"),
        ("skills-hub", "Skill marketplace"),
        ("skin-engine", "Color theme system"),
        ("slack", "Slack CLI integration"),
        ("tips", "Show contextual tips"),
        ("tools-config", "Configure tool toolsets"),
        ("uninstall", "Uninstall VectorCode"),
        ("voice", "Voice mode"),
        ("webhook", "Webhook server"),
        ("web-server", "Web UI server"),
    ]
    for name, desc in _vc_subs:
        p = sub.add_parser(name, help=desc)
        p.add_argument("rest", nargs="*", help="Pass-through args to underlying module")

    args = parser.parse_args()

    dispatch = {
        "repl":       cmd_repl,
        "run":        cmd_run,
        "auto":       cmd_auto,
        "hybrid":     cmd_hybrid,
        "mcp":        cmd_mcp,
        "status":     cmd_status,
        "sessions":   cmd_sessions,
        "models":     cmd_models,
        "agents":     cmd_agents,
        "skills":     cmd_skills,
        "completion": cmd_completion,
        "usage":      cmd_usage,
        "gateway":    cmd_gateway,
        "auth":       cmd_auth,
        "profile":    cmd_profile,
        "doctor":     cmd_doctor,
        "tools":      cmd_tools,
        "cron":       cmd_cron,
        "acp":        cmd_acp,
        "plugins":    cmd_plugins,
        "self-update": cmd_self_update,
        "version":    cmd_version,
        # Wired vector_cli subcommands (auto-dispatch to vector_cli/<name>.py)
        "backup":      cmd_vector_cli_dispatch("backup"),
        "banner":      cmd_vector_cli_dispatch("banner"),
        "claw":        cmd_vector_cli_dispatch("claw"),
        "clipboard":   cmd_vector_cli_dispatch("clipboard"),
        "copilot-auth": cmd_vector_cli_dispatch("copilot_auth"),
        "curses-ui":   cmd_vector_cli_dispatch("curses_ui"),
        "debug":       cmd_vector_cli_dispatch("debug"),
        "dingtalk-auth": cmd_vector_cli_dispatch("dingtalk_auth"),
        "dump":        cmd_vector_cli_dispatch("dump"),
        "fallback":    cmd_vector_cli_dispatch("fallback_cmd"),
        "hooks":       cmd_vector_cli_dispatch("hooks"),
        "logs":        cmd_vector_cli_dispatch("logs"),
        "mcp-config":  cmd_vector_cli_dispatch("mcp_config"),
        "memory-setup": cmd_vector_cli_dispatch("memory_setup"),
        "model-catalog": cmd_vector_cli_dispatch("model_catalog"),
        "model-normalize": cmd_vector_cli_dispatch("model_normalize"),
        "model-switch": cmd_vector_cli_dispatch("model_switch"),
        "nous-subscription": cmd_vector_cli_dispatch("nous_subscription"),
        "oneshot":     cmd_vector_cli_dispatch("oneshot"),
        "pairing":     cmd_vector_cli_dispatch("pairing"),
        "platforms":   cmd_vector_cli_dispatch("platforms"),
        "plugins-cmd": cmd_vector_cli_dispatch("plugins_cmd"),
        "providers":   cmd_vector_cli_dispatch("providers"),
        "pty-bridge":  cmd_vector_cli_dispatch("pty_bridge"),
        "runtime-provider": cmd_vector_cli_dispatch("runtime_provider"),
        "setup":       cmd_vector_cli_dispatch("setup"),
        "skills-config": cmd_vector_cli_dispatch("skills_config"),
        "skills-hub":  cmd_vector_cli_dispatch("skills_hub"),
        "skin-engine": cmd_vector_cli_dispatch("skin_engine"),
        "slack":       cmd_vector_cli_dispatch("slack_cli"),
        "tips":        cmd_vector_cli_dispatch("tips"),
        "tools-config": cmd_vector_cli_dispatch("tools_config"),
        "uninstall":   cmd_vector_cli_dispatch("uninstall"),
        "voice":       cmd_vector_cli_dispatch("voice"),
        "webhook":     cmd_vector_cli_dispatch("webhook"),
        "web-server":  cmd_vector_cli_dispatch("web_server"),
        None:         cmd_repl,
    }

    # Apply global --model/--mode/--dir to repl command
    if args.cmd in (None, "repl"):
        if getattr(args, "model", None):
            from session import VectorCodeSession
            VectorCodeSession.get().current_model = args.model
        if getattr(args, "mode", None):
            try:
                from session import VectorCodeSession
                VectorCodeSession.get().set_mode(args.mode)
            except ValueError as e:
                print(f"[VECTOR] {e}")

    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
