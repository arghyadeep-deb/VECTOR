"""VECTOR — interactive coding REPL (Mode A). VectorCode architecture."""
import json
import time
import datetime
import threading
import itertools
from pathlib import Path

from loguru import logger
from vectorcode.src.utils import atomic_json_write
from vectorcode.src.session import VectorCodeSession
from router import GNNRouter
from gsd_loop import GSDLoop

# ── Paths ─────────────────────────────────────────────────────────────────────
_VECTOR_DIR   = Path.home() / ".vector"
_SESSION_DIR  = _VECTOR_DIR / "sessions"
_SOUL_PATH    = Path(__file__).parent.parent.parent.parent / "brain" / "VECTOR" / "SOUL.md"
_SKILLS_DIR   = Path.home() / ".claude" / "skills"
_TRAJ_FILE    = _VECTOR_DIR / "trajectory_samples.jsonl"

# ── Context limits (tokens, rough estimate: 1 token ≈ 4 chars) ────────────────
_COMPRESS_THRESHOLD = 6000   # trigger compression above this many chars in history
_KEEP_LAST_N        = 6      # always keep the last N turns after compression

# ── Spinner ───────────────────────────────────────────────────────────────────
class _Spinner:
    _FRAMES = ["⠋", "⠙", "⠸", "⠴", "⠦", "⠇"]
    def __init__(self, model: str):
        self._model  = model
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        for frame in itertools.cycle(self._FRAMES):
            if self._stop.is_set():
                break
            print(f"\r\033[2m{frame} {self._model} thinking…\033[0m", end="", flush=True)
            time.sleep(0.08)
        print("\r\033[K", end="", flush=True)   # clear the spinner line

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()


# ── System prompt ─────────────────────────────────────────────────────────────
_TOOL_ENFORCEMENT = """
EXECUTION RULES (follow strictly):
- Use tools to act — do not describe what you would do. Do it.
- Always verify prerequisites before acting (file exists, path valid).
- After writing or editing code, confirm the change is complete.
- Never ask permission for GREEN-gate actions — just execute.
- For YELLOW-gate actions (git commit, file write), state you are doing it then do it.
- For RED-gate actions (delete, push, deploy), pause and ask once.
- Prefer absolute paths. Never assume CWD.
- If you cannot complete a step, explain why and offer alternatives."""

_DEFAULT_SOUL = """You are VECTOR — a Darwinian multi-agent coding AI running locally on Arghyadeep's Legion Pro 5.
You are direct, precise, and action-oriented. No filler phrases. No "Certainly!" or "Of course!".
You operate in the VECTOR codebase (Python, FastAPI, Ollama, LangGraph, SQLite, FAISS).
You have access to file tools, bash tools, code graph, browser automation, and 300+ MCP tools."""

# ── Ollama model fetcher ──────────────────────────────────────────────────────
def _fetch_ollama_models() -> list[dict]:
    """Fetch installed Ollama models from http://localhost:11434/api/tags.
    Returns list of {name, size, modified_at, digest} or empty list if unreachable."""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        data = json.loads(req.read().decode())
        return data.get("models", [])
    except Exception:
        return []

def _pick_best_ollama_model(models: list[dict]) -> str | None:
    """Pick the largest (highest param count) Ollama model."""
    if not models:
        return None
    scored = []
    for m in models:
        name = m.get("name", "")
        size = m.get("size", 0)
        scored.append((size, name))
    scored.sort(reverse=True)
    return scored[0][1]

def _load_soul() -> str:
    if _SOUL_PATH.exists():
        try:
            return _SOUL_PATH.read_text(encoding="utf-8").strip()
        except Exception as _sve:
            logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)
    return _DEFAULT_SOUL

def _build_system_prompt(skills_index: str = "", project_dir: "Path | None" = None,
                         personality: "object | None" = None) -> str:
    if isinstance(personality, dict):
        soul = personality.get('identity', '') + '\nStyle: ' + personality.get('style', '')
    elif personality is not None and hasattr(personality, "system_prompt") and personality.system_prompt:
        soul = personality.system_prompt
    else:
        soul = _load_soul()
    parts = [soul, _TOOL_ENFORCEMENT]
    # Inject VECTOR.md project config if present
    if project_dir:
        try:
            from context.vectormd import VectorMD
            vmd_content = VectorMD(project_dir).as_system_block()
            if vmd_content:
                parts.insert(0, vmd_content)
        except Exception as _sve:
            logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)
    if skills_index:
        parts.append(f"\n<available_skills>\n{skills_index}\n</available_skills>")
    parts.append("\nPlatform: CLI terminal. Use plain text and markdown code fences. No MEDIA: tags.")
    return "\n".join(parts)


# ── Skill loader ──────────────────────────────────────────────────────────────
def _scan_skills() -> dict:
    """Return {slug: Path} for every skill with a SKILL.md in ~/.claude/skills/."""
    skills = {}
    if not _SKILLS_DIR.exists():
        return skills
    for skill_dir in _SKILLS_DIR.iterdir():
        if skill_dir.is_dir():
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                skills[skill_dir.name.lower()] = skill_md
    return skills

def _build_skills_index(skills: dict) -> str:
    if not skills:
        return ""
    lines = ["Available skills (type /<name> to invoke):"]
    for slug in sorted(skills):
        lines.append(f"  /{slug}")
    return "\n".join(lines)

def _load_skill(skill_md: Path) -> str:
    try:
        return skill_md.read_text(encoding="utf-8").strip()
    except Exception as e:
        return f"[VECTOR] Could not load skill: {e}"


# ── Context compressor ────────────────────────────────────────────────────────
def _history_size(history: list) -> int:
    return sum(len(m.get("content", "")) for m in history)

def _compress_history(history: list, model: str) -> list:
    """
    Keep system prompt + last N turns intact.
    Summarize the middle into a structured block.
    """
    if len(history) < 4:
        return history

    system_msgs = [m for m in history if m["role"] == "system"]
    tail        = [m for m in history if m["role"] != "system"][-_KEEP_LAST_N:]
    middle      = [m for m in history if m["role"] != "system"][:-_KEEP_LAST_N]

    if not middle:
        return history

    # Build a summary prompt
    mid_text = "\n".join(
        f"[{m['role'].upper()}] {m['content'][:300]}" for m in middle
    )
    summary_prompt = (
        "Summarize this conversation segment in 3 sections:\n"
        "## Active Task\n## Resolved\n## Pending\n\n"
        f"{mid_text}"
    )
    summary = "[Context compressed — continuing from checkpoint]\n"
    import ollama
    try:
        resp = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": summary_prompt}],
        )
        summary = resp["message"]["content"]
    except Exception as _sve:
        logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)

    compressed = system_msgs + [
        {"role": "assistant", "content": f"<context-summary>\n{summary}\n</context-summary>"}
    ] + tail
    logger.debug(f"[VECTOR][repl] context compressed: {len(middle)} turns → 1 summary block")
    return compressed


# ── Session persistence ───────────────────────────────────────────────────────
def _save_session(history: list, model: str, mode: str = "repl",
                  token_usage: "dict | None" = None,
                  tool_calls: "list | None" = None, *, session_id: str | None = None,
                  project: str | None = None, label: str | None = None,
                  title: str | None = None, worker_name: str | None = None,
                  local_images: bool | None = None) -> Path:
    from vectorcode.src.image_attachments import content_has_images
    from vectorcode.src.session import VectorCodeSession
    session_private = VectorCodeSession.get().local_images
    if type(session_private) is not bool or (local_images is not None and type(local_images) is not bool):
        raise ValueError("Image privacy marker is invalid.")
    local_images = session_private or local_images is True or any(
        isinstance(message, dict) and content_has_images(message.get("content")) for message in history)
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    ts   = int(time.time())
    path = _SESSION_DIR / f"session_{ts}.json"
    if session_id:
        import uuid
        path = _SESSION_DIR / f"session_{uuid.UUID(session_id)}.json"
    elif path.exists():
        path = _SESSION_DIR / f"session_{ts}_{time.time_ns()}.json"
    payload = {
        "ts": ts,
        "model": model,
        "mode": mode,
        "history": history,
        "tokens": (token_usage or {}).get("total", sum(
            (token_usage or {}).get(k, 0) for k in ("prompt_tokens", "completion_tokens")
        )),
        "prompt_tokens": (token_usage or {}).get("prompt_tokens", 0),
        "completion_tokens": (token_usage or {}).get("completion_tokens", 0),
        "cache_read_tokens": (token_usage or {}).get("cache_read_tokens", 0),
        "tool_calls": [{key: value for key, value in call.items() if key != 'rollback'}
                       for call in (tool_calls or []) if isinstance(call, dict)],
        "label": label or "",
        "title": title or "",
        "session_id": session_id,
        "project": project,
        "worker_name": worker_name,
        "local_images": local_images,
    }
    atomic_json_write(path, payload)
    return path

def _load_last_session() -> dict | None:
    if not _SESSION_DIR.exists():
        return None
    sessions = sorted(_SESSION_DIR.glob("session_*.json"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    if not sessions:
        return None
    try:
        return json.loads(sessions[0].read_text(encoding="utf-8"))
    except Exception:
        return None

def _save_trajectory(history: list, model: str, completed: bool = True):
    """Append ShareGPT-format conversation to trajectory file for LLM training."""
    _VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    turns = [
        {"from": "human" if m["role"] == "user" else "gpt", "value": m["content"]}
        for m in history if m["role"] in ("user", "assistant")
    ]
    if not turns:
        return
    record = {"conversations": turns, "model": model,
               "completed": completed, "ts": int(time.time())}
    with _TRAJ_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Session listing ────────────────────────────────────────────────────────────
def _list_sessions() -> list[dict]:
    """Return sorted list of saved session metadata dicts."""
    if not _SESSION_DIR.exists():
        return []
    sessions = []
    for p in sorted(_SESSION_DIR.glob("session_*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            sessions.append({
                "path": str(p),
                "ts": data.get("ts", 0),
                "model": data.get("model", "?"),
                "mode": data.get("mode", "?"),
                "turns": len(data.get("history", [])),
                "tokens": data.get("tokens", 0),
                "label": data.get("label", ""),
                "title": data.get("title", ""),
            })
        except Exception as _sve:
            logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)
    return sorted(sessions, key=lambda item: Path(item["path"]).stat().st_mtime_ns, reverse=True)


# ── Project config detection ───────────────────────────────────────────────────
def _detect_project_config(project_dir: Path) -> dict:
    """Scan project directory to detect language, test command, build command."""
    result = {
        "name": project_dir.name,
        "language": "Unknown",
        "build": "",
        "test": "",
        "lint": "",
        "runner": "",
    }

    pkg_json = project_dir / "package.json"
    req_txt = project_dir / "requirements.txt"
    cargo = project_dir / "Cargo.toml"
    pyproject = project_dir / "pyproject.toml"
    gemfile = project_dir / "Gemfile"
    go_mod = project_dir / "go.mod"
    setup_py = project_dir / "setup.py"

    if pkg_json.exists():
        result["language"] = "TypeScript / JavaScript"
        result["runner"] = "node"
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
            if scripts.get("test"):
                result["test"] = scripts["test"]
            elif scripts.get("test:unit"):
                result["test"] = scripts["test:unit"]
            else:
                result["test"] = "npm test"
            if scripts.get("build"):
                result["build"] = scripts["build"]
            elif scripts.get("compile"):
                result["build"] = scripts["compile"]
            else:
                result["build"] = "npm run build"
            if scripts.get("lint"):
                result["lint"] = scripts["lint"]
            elif scripts.get("format"):
                result["lint"] = scripts["format"]
            else:
                result["lint"] = "npm run lint"
        except Exception:
            result["test"] = "npm test"
            result["build"] = "npm run build"
            result["lint"] = "npm run lint"

    elif pyproject.exists() or setup_py.exists():
        result["language"] = "Python"
        result["runner"] = "python"
        if pyproject.exists():
            result["test"] = "pytest"
            result["build"] = "pip install -e ."
            result["lint"] = "ruff check ."
        else:
            result["test"] = "pytest"
            result["build"] = "pip install -r requirements.txt"
            result["lint"] = "ruff check ."

    elif req_txt.exists():
        result["language"] = "Python"
        result["runner"] = "python"
        result["test"] = "pytest"
        result["build"] = "pip install -r requirements.txt"
        result["lint"] = "ruff check ."

    elif cargo.exists():
        result["language"] = "Rust"
        result["runner"] = "cargo"
        result["test"] = "cargo test"
        result["build"] = "cargo build"
        result["lint"] = "cargo clippy"

    elif go_mod.exists():
        result["language"] = "Go"
        result["runner"] = "go"
        result["test"] = "go test ./..."
        result["build"] = "go build ./..."
        result["lint"] = "golangci-lint run"

    elif gemfile.exists():
        result["language"] = "Ruby"
        result["runner"] = "ruby"
        result["test"] = "bundle exec rspec"
        result["build"] = "bundle install"
        result["lint"] = "bundle exec rubocop"

    return result


# ── Ollama streaming ──────────────────────────────────────────────────────────
def _ask_ollama(model: str, messages: list) -> str:
    import ollama
    full = []
    try:
        print(f"\033[2m[{model}]\033[0m ", end="", flush=True)
        stream = ollama.chat(model=model, messages=messages, stream=True)
        for chunk in stream:
            token = chunk["message"]["content"]
            print(token, end="", flush=True)
            full.append(token)
        print()
    except Exception as e:
        msg = f"\n[VECTOR] Ollama error — {e}\nIs Ollama running?  ollama serve"
        print(msg)
        return msg
    return "".join(full)


def _ask_model(model_id: str, messages: list) -> str:
    """
    Route to ModelRouter (multi-provider: Anthropic/OpenAI/Groq/Ollama/…).
    Falls back to direct Ollama call for bare model names or if router fails.
    """
    # Bare model names like "vector-focus" → treat as ollama/ directly
    if "/" not in model_id:
        return _ask_ollama(model_id, messages)
    try:
        from providers import ModelRouter
        router = ModelRouter()
        print(f"\033[2m[{model_id}]\033[0m ", end="", flush=True)
        result = router.complete(model_id, messages, stream=True)
        text = result.message.content
        print(text)
        return text
    except Exception as e:
        logger.warning(f"[VECTOR][repl] ModelRouter failed for {model_id}: {e} — falling back to Ollama")
        bare = model_id.split("/", 1)[1]
        return _ask_ollama(bare, messages)


# ── REPL ──────────────────────────────────────────────────────────────────────
class VectorREPL:
    """Mode A: interactive terminal REPL with streaming, skills, compression, persistence."""

    mode = "repl"

    COMMANDS = {
        "/help":    "Show commands",
        "/status":  "Session status — model, mode, uptime, token count, skills",
        "/mode":    "/mode auto|repl|hybrid|cautious|standard|autonomous|read-only",
        "/model":   "/model <provider/name>  — validate config & switch model",
        "/models":  "List configured providers with ●/● reachability",
        "/connect": "/connect <provider> — save your API key using a hidden prompt",
        "/memory":  "Show session memory (.vector/memory.md)",
        "/compact": "Manually trigger context compaction",
        "/cost":    "Show token usage + per-provider estimated cost",
        "/diff":    "Show all file changes made this session",
        "/commit":  "/commit [msg]  — commit all changes with AI-generated message",
        "/spawn":   "/spawn <task>  — spawn a worker agent for a sub-task",
        "/undo":    "Revert the last file write (shows path to manually undo)",
        "/skills":  "List available skills",
        "/init":    "Generate VECTOR.md by scanning project (language, test, build)",
        "/save":    "Save full session (history, model, mode, tokens) to .vector/",
        "/restore": "List saved sessions — pick one to reload history",
        "/tools":   "List tool categories",
        "/notify":  "/notify <text>  — send notification via comms (all configured channels)",
        "/comms":   "Show comms status — pending/urgent/unread counts",
        "/search":  "/search <query>  — web search via OpenCLI (with DuckDuckGo fallback)",
        "/fetch":   "/fetch <url>  — fetch and summarize a URL",
        "/clear":   "Clear conversation history",
        "/quit":    "Exit VECTOR",
        "/usage":   "/usage [days]  — token + cost analytics for last N days (default 30)",
        "/persona": "/persona <name>  — switch personality (default, mentor, brief, professional, debug)",
    }

    def __init__(self, project_dir: "Path | None" = None) -> None:
        self.session      = VectorCodeSession.get()
        self.session.set_mode("repl")
        self.router       = GNNRouter()          # GNNRouter: 3-layer routing (GNN cosine + EMA keyword + regex fallback)
        self.gsd          = GSDLoop(mode="repl")
        self._skills      = _scan_skills()
        self._project_dir = project_dir or Path.cwd()
        self._personality: str = "default"
        self._history     = [{"role": "system",
                               "content": _build_system_prompt(
                                   _build_skills_index(self._skills),
                                   self._project_dir,
                               )}]
        self._running     = False
        self._last_write:  "str | None" = None  # track last file written for /undo
        try:
            from session_db import get_session_db
            self._db = get_session_db()
            # Auto-migrate to latest schema
            try:
                self._db.migrate_up()
            except Exception as _sve:
                logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)
            self._db.create_session(
                self.session.session_id,
                self.session.current_model,
                str(self._project_dir),
                self.session.mode,
            )
        except Exception as e:
            logger.debug(f"[VECTOR][repl] session_db init: {e}")
            self._db = None

    # ── slash commands ────────────────────────────────────────────────────────

    def handle_command(self, raw: str) -> str | None:
        raw = raw.strip()

        if raw == '/connect' or raw.startswith('/connect '):
            from types import SimpleNamespace
            from vectorcode.src.providers.key_commands import handle_auth

            parts = raw.split()
            if len(parts) != 2:
                return 'Usage: /connect <provider>. Paste the key only into the hidden prompt.'
            try:
                handle_auth(SimpleNamespace(auth_action='add', name=parts[1], provider=parts[1], key=None))
                return f'Connected. Choose /model {parts[1]}/<model-id> to use this provider.'
            except (Exception, SystemExit):
                return 'Connection setup failed. Check provider support and system keyring availability.'

        # ── Must check /model + /models BEFORE /mode (prefix clash!) ──
        if raw.startswith("/model "):
            parts = raw.split(maxsplit=1)
            model_id = parts[1].strip()
            try:
                from providers import ModelRouter
                router = ModelRouter()
                if "/" not in model_id:
                    return f"Invalid format: '{model_id}'. Use provider/name, e.g. ollama/llama4:scout"
                self.session.current_model = model_id
                return f"Switched to {model_id}"
            except Exception as e:
                return f"model error: {e}"

        if raw == "/model":
            return f"Current model: {self.session.current_model}"

        if raw == "/models":
            try:
                import os, urllib.request, urllib.error
                lines = [f"  current : {self.session.current_model}", ""]

                # Check Ollama
                ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
                try:
                    req = urllib.request.urlopen(ollama_url + "/api/tags", timeout=3)
                    data = json.loads(req.read().decode())
                    installed = data.get("models", [])
                    lines.append(f"  [ON]  ollama  ({len(installed)} models)")
                    for m in installed[:10]:
                        size_gb = m.get("size", 0) / 1e9
                        lines.append(f"       {m['name']}  ({size_gb:.1f}GB)")
                except Exception:
                    lines.append("  [OFF] ollama  (offline)")

                from vectorcode.src.cli.auth import AuthManager
                for entry in AuthManager().list_credentials():
                    lines.append(f'  [KEY] {entry.provider}  (stored: {entry.name}; not connectivity-tested)')

                # Check cloud providers via env vars
                cloud = [
                    ("anthropic", "ANTHROPIC_API_KEY"),
                    ("openai", "OPENAI_API_KEY"),
                    ("google", "GOOGLE_API_KEY"),
                    ("groq", "GROQ_API_KEY"),
                ]
                for name, env_var in cloud:
                    from core.security.secrets_manager import get_secret
                    val = get_secret(env_var)
                    status = "[ON] " if val else "[OFF]"
                    lines.append(f"  {status} {name}  (env ${env_var} {'SET' if val else 'MISSING'})")

                return "\n".join(lines)
            except Exception as e:
                return f"models error: {e}"

        if raw.startswith("/mode"):
            parts = raw.split(maxsplit=1)
            new_mode = parts[1].strip() if len(parts) > 1 else ""
            try:
                self.session.set_mode(new_mode)
                return f"Mode \u2192 {new_mode}"
            except ValueError as e:
                return str(e)

        if raw == "/help":
            lines = ["", "  \x1b[36mCommands\x1b[0m"]
            for k, v in self.COMMANDS.items():
                lines.append(f"    \x1b[96m{k:<14}\x1b[0m \x1b[2m{v}\x1b[0m")
            if self._skills:
                lines.append(f"\n  \x1b[36mSkills\x1b[0m \x1b[2m(type /<name>)\x1b[0m")
                for slug in sorted(self._skills)[:20]:
                    lines.append(f"    \x1b[96m/{slug}\x1b[0m")
                if len(self._skills) > 20:
                    lines.append(f"    \x1b[2m+{len(self._skills) - 20} more — see /skills\x1b[0m")
            return "\n".join(lines)

        if raw == "/status":
            s = self.get_status()
            uptime = datetime.datetime.now(datetime.timezone.utc) - self.session.started_at
            uptime_str = str(uptime).split(".")[0]
            tu = self.session.token_usage
            return (f"\n  mode     {s['mode']}\n  model    {s['model']}\n"
                    f"  uptime   {uptime_str}\n"
                    f"  tokens   {tu.prompt_tokens} in / {tu.completion_tokens} out"
                    f" / {tu.cache_read_tokens} cache  (${self.session.cost_usd:.6f})\n"
                    f"  history  {s['history']} turns\n  skills   {len(self._skills)}")

        if raw == "/skills":
            if not self._skills:
                return "No skills found in ~/.claude/skills/"
            return "  Skills:\n" + "\n".join(f"    /{s}" for s in sorted(self._skills))

        if raw == "/tools" or raw.startswith("/tools "):
            from vectorcode.src.tools.registry import ToolRouter

            query = raw.partition(" ")[2].strip().lower()
            schemas = ToolRouter(project_dir=self._project_dir).get_schemas()
            names = sorted(schema["function"]["name"] for schema in schemas)
            found = [name for name in names if query in name.lower()]
            return (f"Available tools in {self.session.mode} mode ({len(found)}/{len(names)}):\n"
                    + ("\n".join(found) if found else "No matching tools. Try /tools without a filter."))

        if raw == "/init":
            try:
                from context.vectormd import VectorMD
                vmd = VectorMD(self._project_dir)
                if vmd.exists():
                    return "\033[93mVECTOR.md already exists at " + str(vmd.path) + "\033[0m"
                cfg = _detect_project_config(self._project_dir)
                template = f"""# VECTOR.md — Project Configuration

## Project
Name: {cfg["name"]}
Language: {cfg["language"]}
Runner: {cfg["runner"]}

## Architecture
(describe your directory layout here)

## Conventions
(coding standards, naming rules, etc.)

## Build & Test
- Build: {cfg["build"]}
- Test:  {cfg["test"]}
- Lint:  {cfg["lint"]}

## Review Checklist
(things to check before committing)
"""
                vmd.path.write_text(template, encoding="utf-8")
                print(f"\033[92mVECTOR.md created → {vmd.path}\033[0m")
                print(f"  Language: {cfg['language']}")
                print(f"  Build:    {cfg['build']}")
                print(f"  Test:     {cfg['test']}")
                print(f"  Lint:     {cfg['lint']}")
                # Rebuild system prompt with new VECTOR.md
                self._history[0] = {"role": "system",
                    "content": _build_system_prompt(_build_skills_index(self._skills), self._project_dir)}
                return ""
            except Exception as e:
                return f"/init error: {e}"

        if raw in ("/clear", "/reset"):
            self._history = [{"role": "system",
                               "content": _build_system_prompt(_build_skills_index(self._skills))}]
            self.session.reset()
            return "History cleared."

        if raw == "/save":
            tu = self.session.token_usage
            path = _save_session(
                self._history,
                self.session.current_model,
                mode=self.session.mode,
                token_usage={
                    "prompt_tokens": tu.prompt_tokens,
                    "completion_tokens": tu.completion_tokens,
                    "cache_read_tokens": tu.cache_read_tokens,
                    "total": tu.total_tokens,
                },
                tool_calls=self.session.tool_calls,
                title=self.session.display_title,
            )
            if self._db:
                try:
                    self._db.end_session(self.session.session_id, "user_save")
                except Exception as e:
                    logger.debug(f"[VECTOR][repl] session_db end_session: {e}")
            return f"Session saved → {path}  ({len(self._history)-1} messages, ${self.session.cost_usd:.6f})"

        if raw == "/restore":
            sessions = _list_sessions()
            if not sessions:
                return "No saved sessions found in .vector/sessions/"
            lines = ["  Saved sessions:", ""]
            for i, s in enumerate(sessions, 1):
                ts = datetime.datetime.fromtimestamp(s["ts"]).strftime("%Y-%m-%d %H:%M")
                lines.append(f"  \033[1m{i}.\033[0m  {ts}  {s['model']}  [{s['mode']}]  "
                             f"{s['turns']} msgs  {s['tokens']} tok")
            lines.append("")
            lines.append("  Enter number to restore, or Enter to cancel: ")
            print("\n".join(lines), end="", flush=True)
            try:
                choice = input().strip()
                if choice.isdigit() and 1 <= int(choice) <= len(sessions):
                    idx = int(choice) - 1
                    sess_path = sessions[idx]["path"]
                    data = json.loads(Path(sess_path).read_text(encoding="utf-8"))
                    from vectorcode.src.image_attachments import saved_image_privacy
                    if saved_image_privacy(data):
                        return "Image conversations require vector tui --resume; plain restore is unavailable."
                    self._history = data.get("history", [])
                    self.session.current_model = data.get("model", self.session.current_model)
                    if data.get("mode"):
                        try:
                            self.session.set_mode(data["mode"])
                        except Exception as _sve:
                            logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)
                    n_msgs = len(self._history) - 1
                    ts = datetime.datetime.fromtimestamp(data["ts"]).strftime("%Y-%m-%d %H:%M")
                    result = [f"\033[92mSession restored — {n_msgs} messages loaded\033[0m"]
                    result.append(f"  from {ts}  model={data.get('model','?')}  mode={data.get('mode','?')}")
                    # Show the last 3 messages as context
                    tail = [m for m in self._history if m["role"] != "system"][-3:]
                    if tail:
                        result.append("\n  Last messages:")
                        for m in tail:
                            preview = m["content"][:80].replace("\n", " ")
                            role = "\033[36muser\033[0m" if m["role"] == "user" else "\033[32mvector\033[0m"
                            result.append(f"    [{role}] {preview}")
                    return "\n".join(result)
                else:
                    return "Restore cancelled."
            except (EOFError, KeyboardInterrupt):
                return "\nRestore cancelled."

        if raw == "/memory":
            try:
                from context.session_memory import read_memory_md
                return read_memory_md()
            except Exception as e:
                return f"memory error: {e}"

        if raw == "/compact":
            try:
                from context.compactor import ContextCompactor
                before = len(self._history)
                compactor = ContextCompactor(model=self.session.current_model,
                                              project_dir=self._project_dir)
                self._history = compactor.compact(self._history)
                return f"Compacted: {before} → {len(self._history)} messages"
            except Exception as e:
                return f"compact error: {e}"

        if raw.startswith("/sparc"):
            parts = raw.split(None, 2)
            stage = parts[1] if len(parts) > 1 else "full"
            task = parts[2] if len(parts) > 2 else ""
            if not task:
                return "Usage: /sparc [stage|full] <task description>"
            try:
                from skills.builtin.sparc.coordinator import sparc_slash_command
                from engine.agent import AIAgent
                agent = AIAgent(model=self.session.current_model)
                return sparc_slash_command(stage, task, agent)
            except Exception as e:
                return f"sparc error: {e}"

        if raw == "/cost":
            u = self.session.token_usage
            model_id = self.session.current_model
            provider = model_id.split("/", 1)[0] if "/" in model_id else "unknown"
            pricing = {
                "anthropic": {"in": 3.0e-6, "out": 15.0e-6, "cache": 0.3e-6},
                "openai":    {"in": 2.5e-6, "out": 10.0e-6, "cache": 1.25e-6},
                "google":    {"in": 1.25e-6, "out": 5.0e-6, "cache": 0.0},
                "mistral":   {"in": 2.0e-6, "out": 6.0e-6, "cache": 0.0},
                "groq":      {"in": 0.7e-6, "out": 2.0e-6, "cache": 0.0},
                "deepseek":  {"in": 0.5e-6, "out": 1.5e-6, "cache": 0.0},
                "cohere":    {"in": 1.5e-6, "out": 3.0e-6, "cache": 0.0},
                "ollama":    {"in": 0.0, "out": 0.0, "cache": 0.0},
            }
            pp = pricing.get(provider, {"in": 1.0e-6, "out": 4.0e-6, "cache": 0.5e-6})
            est_input = u.prompt_tokens * pp["in"]
            est_output = u.completion_tokens * pp["out"]
            est_cache = u.cache_read_tokens * pp["cache"]
            est_total = est_input + est_output + est_cache
            return (
                f"\n  Provider: {provider}  ({model_id})"
                f"\n  Tokens:   {u.prompt_tokens} in / {u.completion_tokens} out"
                f" / {u.cache_read_tokens} cache-read"
                f"\n  Total:    {u.total_tokens} tokens"
                f"\n  Cost:     ${self.session.cost_usd:.6f} USD  (est. ${est_total:.6f})"
            )

        if raw == "/diff":
            try:
                from tools.git_tools import GitTools
                gt = GitTools(repo_root=self._project_dir)
                return gt.git_diff() or "(no changes)"
            except Exception as e:
                return f"diff error: {e}"

        if raw.startswith("/commit"):
            parts = raw.split(maxsplit=1)
            msg = parts[1].strip() if len(parts) > 1 else ""
            try:
                from tools.git_tools import GitTools
                gt = GitTools(repo_root=self._project_dir)
                if not msg:
                    # Generate commit message with the model
                    diff = gt.git_diff(staged=False)[:1500]
                    prompt = f"Write a concise git commit message (one line) for this diff:\n{diff}"
                    self._history.append({"role": "user", "content": prompt})
                    msg = _ask_ollama(self.session.current_model, self._history)
                    self._history.pop()
                    msg = msg.strip().splitlines()[0][:72]
                return gt.git_commit(msg)
            except Exception as e:
                return f"commit error: {e}"

        if raw.startswith("/spawn"):
            parts = raw.split(maxsplit=1)
            task = parts[1].strip() if len(parts) > 1 else ""
            if not task:
                return "Usage: /spawn <task description>"
            try:
                from autonomous import VectorAutonomous
                va = VectorAutonomous()
                task_id = va.submit(task)
                return f"Worker spawned — task_id: {task_id}\nTask: {task}"
            except Exception as e:
                return f"spawn error: {e}"

        if raw == "/undo":
            if self._last_write:
                return (
                    f"Last write: {self._last_write}\n"
                    f"To undo: git checkout -- {self._last_write}"
                )
            return "No file writes recorded this session."

        # ── comms commands ──────────────────────────────────────────────

        if raw.startswith("/notify"):
            parts = raw.split(maxsplit=1)
            text = parts[1].strip() if len(parts) > 1 else ""
            if not text:
                return "Usage: /notify <message text>"
            try:
                import asyncio
                from comms.messenger import MessagingHub
                hub = MessagingHub()
                result = asyncio.run(hub.send_notification(text, priority="normal"))
                status = result.get("status", "?")
                via    = result.get("via", result.get("reason", ""))
                return f"Notification {status}" + (f" via {via}" if via else "")
            except Exception as e:
                return f"notify error: {e}"

        if raw == "/comms":
            try:
                from comms.messenger import MessagingHub
                hub = MessagingHub()
                s = hub.get_comms_status()
                jobs = hub.list_cron_jobs()
                skills = hub.list_skills()
                return (
                    f"\n  urgent   {s['urgent']}\n  unread   {s['unread']}"
                    f"\n  pending  {s['pending']}\n  cron     {len(jobs)} jobs"
                    f"\n  skills   {len(skills)} registered"
                )
            except Exception as e:
                return f"comms error: {e}"

        # ── OpenCLI / web commands ─────────────────────────────────────────────

        if raw.startswith("/search"):
            parts = raw.split(maxsplit=1)
            query = parts[1].strip() if len(parts) > 1 else ""
            if not query:
                return "Usage: /search <query>"
            if self.session.mode == "read-only":
                return "/search is unavailable in read-only mode."
            try:
                from tools.web_tools import search_text
                return search_text(query, 5)
            except Exception as e:
                return f"search error: {e}"

        if raw.startswith("/fetch"):
            parts = raw.split(maxsplit=1)
            url = parts[1].strip() if len(parts) > 1 else ""
            if not url:
                return "Usage: /fetch <url>"
            if self.session.mode == "read-only":
                return "/fetch is unavailable in read-only mode."
            try:
                # Deterministic retrieval through the web backend: no model call, no tool-choice.
                from tools.web_tools import fetch_history_messages, fetch_url_text
                has_content, text = fetch_url_text(url.split()[0])
                if has_content:
                    self._history.extend(fetch_history_messages(raw, text))
                return text[:3000] + ("\n…[truncated; the full text is in the conversation]" if len(text) > 3000 else "")
            except Exception as e:
                return f"fetch error: {e}"

        if raw == "/quit":
            self._running = False
            return "Goodbye."

        if raw.startswith("/usage"):
            parts = raw.split(maxsplit=1)
            days = 30
            if len(parts) > 1:
                try:
                    days = int(parts[1].strip())
                except ValueError:
                    return "Usage: /usage [days]  — e.g. /usage 7"
            try:
                from insights import InsightsEngine
                return InsightsEngine().format_terminal(days=days)
            except Exception as e:
                return f"usage error: {e}"

        if raw.startswith("/persona"):
            parts = raw.split(maxsplit=1)
            persona_name = parts[1].strip() if len(parts) > 1 else ""
            if not persona_name:
                try:
                    from persona.personalities import get_personality, list_personalities
                    items = list_personalities()
                    lines = ["  Personalities:"]
                    for name in items:
                        marker = " *" if name == self._personality else ""
                        lines.append(f"    {name:<16}{get_personality(name).get('style', '')}{marker}")
                    return "\n".join(lines)
                except Exception as e:
                    return f"persona error: {e}"
            try:
                from persona.personalities import get_personality, list_personalities
                if persona_name not in list_personalities():
                    raise KeyError('Unknown personality: ' + persona_name)
                p = get_personality(persona_name)
                self._personality = persona_name
                # Rebuild system prompt using new personality
                self._history[0] = {
                    "role": "system",
                    "content": _build_system_prompt(
                        _build_skills_index(self._skills),
                        self._project_dir,
                        personality=p,
                    ),
                }
                return f"Personality -> {persona_name}: {p.get('style', '')}"
            except KeyError as e:
                return f"persona error: {e}"
            except Exception as e:
                return f"persona error: {e}"

        # Dynamic skill invocation — /skill-name
        slug = raw.lstrip("/").lower()
        if slug in self._skills:
            content = _load_skill(self._skills[slug])
            self._history.append({"role": "user", "content": content})
            model = self.session.current_model
            print(f"\n\033[2m[skill: {slug} → {model}]\033[0m")
            reply = _ask_ollama(model, self._history)
            self._history.append({"role": "assistant", "content": reply})
            return None   # already printed

        if raw.startswith("/"):
            return "Unknown command. Use /help."
        return None  # not a slash command

    def _run_agent_turn(self, user_input: str, model: str) -> str:
        """
        Run one user turn through the VectorAgent execution loop.
        The loop calls tools (read_file, bash, git_status, web_search, etc.)
        and iterates until the model stops issuing tool_calls.

        Falls back to single _ask_model() call if the agent loop fails.
        """
        system_msg = self._history[0]["content"] if self._history else ""
        conv_history = [m for m in self._history if m["role"] != "system"]

        def _on_tool_start(name, args_preview):
            # Claude Code-style: cyan dot + tool name + dim args
            args_str = args_preview[:70] if args_preview else ""
            print(f"  \033[36m●\033[0m \033[1m{name}\033[0m\033[2m({args_str})\033[0m", flush=True)

        def _on_tool_done(name, result_preview, duration_ms):
            # Claude Code-style: green check + dim duration
            preview = (result_preview or "").strip()[:80]
            if preview:
                print(f"    \033[32m✓\033[0m \033[2m{preview} · {duration_ms}ms\033[0m", flush=True)
            else:
                print(f"    \033[32m✓\033[0m \033[2mdone · {duration_ms}ms\033[0m", flush=True)

        try:
            from engine.agent_loop import VectorAgent
            agent = VectorAgent(
                model_id=model,
                project_dir=self._project_dir,
                session_id=self.session.session_id,
                quiet_mode=False,
                save_trajectories=True,
                tool_start_callback=_on_tool_start,
                tool_complete_callback=_on_tool_done,
            )
            result = agent.run_conversation(
                user_input,
                system_message=system_msg,
                conversation_history=conv_history,
            )
            reply = result["response"]

            # Rebuild history from agent's message chain
            # (includes tool_call + tool_result messages)
            system_msgs  = [m for m in self._history if m["role"] == "system"]
            new_messages = [m for m in result["messages"] if m["role"] != "system"]
            self._history = system_msgs + new_messages

            # Update session token usage from agent
            self.session.record_token_usage(
                prompt=result.get("iterations", 1) * max(len(user_input) // 4, 1),
                completion=len(reply) // 4,
            )

            # Record in session DB
            if self._db:
                try:
                    self._db.add_message(
                        self.session.session_id, "user", user_input,
                        token_count=len(user_input) // 4,
                    )
                    self._db.add_message(
                        self.session.session_id, "assistant", reply,
                        token_count=len(reply) // 4,
                        finish_reason="stop",
                    )
                except Exception as _sve:
                    logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)

            return reply

        except Exception as e:
            logger.warning(
                "[VECTOR][repl] agent loop error: %s — falling back to _ask_model()", e
            )
            # Graceful fallback: single model call without tool execution
            self._history.append({"role": "user", "content": user_input})
            reply = _ask_model(model, self._history)
            self._history.append({"role": "assistant", "content": reply})
            self.session.record_token_usage(
                prompt=len(user_input) // 4,
                completion=len(reply) // 4,
            )
            return reply

    def get_status(self) -> dict:
        return {
            "mode":    self.session.mode,
            "model":   self.session.current_model,
            "hp":      500,
            "task_id": self.session.task_id,
            "history": max(0, len(self._history) - 1),
        }

    # ── main loop ─────────────────────────────────────────────────────────────

    def run(self, skip_startup_banner: bool = False) -> None:
        self._running = True

        # ── Startup: auto-select best model (no banner prints — already in cli.py) ──
        if not skip_startup_banner:
            installed_models = _fetch_ollama_models()
            if installed_models:
                best = _pick_best_ollama_model(installed_models)
                if best and (self.session.current_model in ("vector-focus", "vector-focus")
                             or not any(m["name"] == self.session.current_model
                                        for m in installed_models)):
                    self.session.current_model = best

        while self._running:
            try:
                # Claude Code-style prompt: dim context line + bright > on next line
                model_short = (self.session.current_model or "vector").replace("ollama/", "")[:24]
                mode_short = (self.session.mode or "repl")[:8]
                ctx_line = f"\n\x1b[2m{mode_short} · {model_short}\x1b[0m"
                print(ctx_line)
                raw = input("\x1b[96m>\x1b[0m \x1b[97m").strip()
                print("\x1b[0m", end="")  # reset
                if not raw:
                    continue

                # Slash commands and skill invocations
                if raw.startswith("/"):
                    result = self.handle_command(raw)
                    if result:
                        print(result)
                    continue

                # Route → GNNRouter picks best model (reference Layer 1+2+3)
                t_route_start = time.perf_counter()
                model = self.router.route(raw)
                self.session.current_model = model

                # Auto-compact if history is getting large (5-stage pipeline)
                if _history_size(self._history) > _COMPRESS_THRESHOLD:
                    try:
                        from context.compactor import ContextCompactor
                        compactor = ContextCompactor(model=model, project_dir=self._project_dir)
                        self._history = compactor.compact(self._history)
                    except Exception:
                        self._history = _compress_history(self._history, model)

                # Expand context references (@file, @diff, @url, @folder, @git)
                expanded_input = raw
                try:
                    from context.references import expand_context_references
                    ref_result = expand_context_references(raw, self._project_dir)
                    if ref_result.expanded:
                        expanded_input = ref_result.message
                        for w in ref_result.warnings:
                            print(f"  \033[93m⚠ {w}\033[0m")
                except Exception as _sve:
                    logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)

                # Prefetch memory context and inject as context
                try:
                    from memory.manager import get_memory_manager
                    mm = get_memory_manager()
                    mem_ctx = mm.prefetch_all(raw)
                    if mem_ctx:
                        expanded_input = f"[Memory context]\n{mem_ctx}\n\n{expanded_input}"
                except Exception as _sve:
                    logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)

                # ── Agent execution loop (Think→Act→Observe) ──────────────────
                print()
                raw_reply = self._run_agent_turn(expanded_input, model)
                # Strip reasoning tags before displaying; save full for trajectory
                try:
                    from utils.reasoning_stripper import extract_reasoning
                    reply, _reasoning = extract_reasoning(raw_reply)
                except Exception:
                    reply = raw_reply

                # Sync memory after turn
                try:
                    from memory.manager import get_memory_manager
                    mm = get_memory_manager()
                    mm.sync_all(raw, reply, session_id=self.session.session_id)
                except Exception as _sve:
                    logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)

                self.session.history.append({"role": "user", "content": raw})

                # GNNRouter learning — reward=0.9 (good, no exception) + latency
                latency_ms = (time.perf_counter() - t_route_start) * 1000
                try:
                    self.router.learn(raw, model, reward=0.9, latency_ms=latency_ms)
                except Exception as _sve:
                    logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)

            except (KeyboardInterrupt, EOFError):
                print("\nExiting VECTOR.")
                break

        # On exit: persist session + update memory + save trajectory
        if len(self._history) > 1:
            try:
                tu = self.session.token_usage
                _save_session(
                    self._history, self.session.current_model,
                    mode=self.session.mode,
                    token_usage={
                        "prompt_tokens": tu.prompt_tokens,
                        "completion_tokens": tu.completion_tokens,
                        "cache_read_tokens": tu.cache_read_tokens,
                        "total": tu.total_tokens,
                    },
                    tool_calls=self.session.tool_calls,
                    title=self.session.display_title,
                )
                _save_trajectory(self._history, self.session.current_model)
            except Exception as _sve:
                logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)
            try:
                from context.session_memory import update_session_memory
                update_session_memory(self._history)
            except Exception as _sve:
                logger.debug("[VECTOR][repl] suppressed Exception: {}", _sve)


# ── self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    repl = VectorREPL()
    assert repl.mode == "repl"
    assert hasattr(repl, "session")
    assert hasattr(repl, "gsd")
    assert hasattr(repl, "router")
    assert "/help" in repl.COMMANDS
    assert "/notify" in repl.COMMANDS
    assert "/search" in repl.COMMANDS
    assert "/comms" in repl.COMMANDS
    repl.handle_command("/mode auto")
    assert repl.session.mode == "auto"
    status = repl.get_status()
    assert "mode" in status and "model" in status and "hp" in status
    # GNNRouter smoke test
    from router import GNNRouter
    assert isinstance(repl.router, GNNRouter), f"Expected GNNRouter, got {type(repl.router)}"
    print("repl.py OK")


