"""VECTOR — interactive coding REPL (Mode A). Hermes-inspired architecture."""
import sys
import json
import time
import datetime
import threading
import itertools
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent))  # vectorcode package

from loguru import logger
from session import VectorCodeSession
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
        except Exception:
            pass
    return _DEFAULT_SOUL

def _build_system_prompt(skills_index: str = "", project_dir: "Path | None" = None) -> str:
    soul  = _load_soul()
    parts = [soul, _TOOL_ENFORCEMENT]
    # Inject VECTOR.md project config if present
    if project_dir:
        try:
            from context.vectormd import VectorMD
            vmd_content = VectorMD(project_dir).as_system_block()
            if vmd_content:
                parts.insert(0, vmd_content)
        except Exception:
            pass
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
    except Exception:
        pass

    compressed = system_msgs + [
        {"role": "assistant", "content": f"<context-summary>\n{summary}\n</context-summary>"}
    ] + tail
    logger.debug(f"[VECTOR][repl] context compressed: {len(middle)} turns → 1 summary block")
    return compressed


# ── Session persistence ───────────────────────────────────────────────────────
def _save_session(history: list, model: str, mode: str = "repl",
                  token_usage: "dict | None" = None,
                  tool_calls: "list | None" = None) -> Path:
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    ts   = int(time.time())
    path = _SESSION_DIR / f"session_{ts}.json"
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
        "tool_calls": tool_calls or [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def _load_last_session() -> dict | None:
    if not _SESSION_DIR.exists():
        return None
    sessions = sorted(_SESSION_DIR.glob("session_*.json"), reverse=True)
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
            })
        except Exception:
            pass
    return sessions


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
        "/notify":  "/notify <text>  — send notification via Hermes (all configured channels)",
        "/comms":   "Show Hermes comms status — pending/urgent/unread counts",
        "/search":  "/search <query>  — web search via OpenCLI (with DuckDuckGo fallback)",
        "/fetch":   "/fetch <url>  — fetch and summarize a URL",
        "/clear":   "Clear conversation history",
        "/quit":    "Exit VECTOR",
    }

    def __init__(self, project_dir: "Path | None" = None) -> None:
        self.session      = VectorCodeSession.get()
        self.session.set_mode("repl")
        self.router       = GNNRouter()          # Ruflo NeuralDomainMapper (Layer 1+2+3)
        self.gsd          = GSDLoop(mode="repl")
        self._skills      = _scan_skills()
        self._project_dir = project_dir or Path.cwd()
        self._history     = [{"role": "system",
                               "content": _build_system_prompt(
                                   _build_skills_index(self._skills),
                                   self._project_dir,
                               )}]
        self._running     = False
        self._last_write:  "str | None" = None  # track last file written for /undo

    # ── slash commands ────────────────────────────────────────────────────────

    def handle_command(self, raw: str) -> str | None:
        raw = raw.strip()

        # ── Must check /model + /models BEFORE /mode (prefix clash!) ──
        if raw.startswith("/model "):
            parts = raw.split(maxsplit=1)
            model_id = parts[1].strip()
            try:
                from config import VectorConfig
                cfg = VectorConfig(self._project_dir)
                providers = cfg.get("providers", default={})
                if "/" not in model_id:
                    return (f"Invalid format: '{model_id}'. Use provider/name, "
                            f"e.g. ollama/llama4:scout")
                provider = model_id.split("/", 1)[0]
                if provider not in providers:
                    available = list(providers.keys())
                    return (f"Unknown provider '{provider}'. "
                            f"Configured: {available}")
                self.session.current_model = model_id
                self.session.started_at = datetime.datetime.now(datetime.timezone.utc)
                return f"Switched to {model_id}"
            except Exception as e:
                return f"model error: {e}"

        if raw == "/model":
            return f"Current model: {self.session.current_model}"

        if raw == "/models":
            try:
                import os
                import urllib.request
                import urllib.error
                from config import VectorConfig
                cfg = VectorConfig(self._project_dir)
                providers = cfg.get("providers", default={})
                lines = []
                lines.append(f"  current : {self.session.current_model}")
                lines.append("")
                for prov_name, prov_cfg in providers.items():
                    api_key_env = prov_cfg.get("api_key_env", "")
                    base_url = prov_cfg.get("base_url", "")
                    reachable = False
                    check_method = ""
                    if prov_name == "ollama":
                        check_url = base_url.rstrip("/") + "/api/tags"
                        try:
                            req = urllib.request.urlopen(check_url, timeout=3)
                            data = json.loads(req.read().decode())
                            installed = data.get("models", [])
                            reachable = True
                            check_method = f"{len(installed)} models"
                        except Exception:
                            pass
                    elif api_key_env:
                        env_val = os.environ.get(api_key_env, "")
                        if env_val:
                            reachable = True
                        check_method = f"env ${api_key_env} {'SET' if reachable else 'MISSING'}"
                    elif base_url:
                        try:
                            urllib.request.urlopen(base_url, timeout=3)
                            reachable = True
                        except Exception:
                            pass
                        check_method = f"ping {base_url}"
                    else:
                        check_method = "no endpoint"
                    dot = "\033[32m●\033[0m" if reachable else "\033[31m●\033[0m"
                    label = f"{dot}  {prov_name}"
                    extras = f"  ({check_method})" if check_method else ""
                    lines.append(f"  {label}{extras}")
                    if prov_name == "ollama" and reachable and installed:
                        for m in installed:
                            size_gb = m.get("size", 0) / 1e9
                            lines.append(f"       {m['name']}  ({size_gb:.1f}GB)")
                lines.append("")
                lines.append(f"  default: {cfg.default_model}")
                lines.append(f"  fast:    {cfg.fast_model}")
                lines.append(f"  local:   {cfg.local_model}")
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
            lines = ["", "  Commands:"]
            for k, v in self.COMMANDS.items():
                lines.append(f"    \033[1m{k:<14}\033[0m {v}")
            if self._skills:
                lines.append("\n  Skills (type /<name>):")
                for slug in sorted(self._skills)[:20]:
                    lines.append(f"    /{slug}")
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

        if raw == "/tools":
            cats = ["agent/swarm", "memory", "hook", "task", "security", "neural",
                    "file", "git", "test", "doc", "browser", "graph", "perf", "worker", "config"]
            return "  Tool categories: " + ", ".join(cats)

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
            )
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
                    self._history = data.get("history", [])
                    self.session.current_model = data.get("model", self.session.current_model)
                    if data.get("mode"):
                        try:
                            self.session.set_mode(data["mode"])
                        except Exception:
                            pass
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

        # ── Hermes comms commands ──────────────────────────────────────────────

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
            try:
                from tools.opencli_tool import OpenCLITool
                oc = OpenCLITool()
                results = oc.search(query, max_results=5)
                return oc.format_results(results)
            except Exception as e:
                # Fallback: WebTools
                try:
                    from tools.web_tools import WebTools
                    wt = WebTools()
                    results = wt.web_search(query, max_results=5)
                    return wt.format_search_results(results)
                except Exception as e2:
                    return f"search error: {e} / {e2}"

        if raw.startswith("/fetch"):
            parts = raw.split(maxsplit=1)
            url = parts[1].strip() if len(parts) > 1 else ""
            if not url:
                return "Usage: /fetch <url>"
            try:
                from tools.web_tools import WebTools
                wt = WebTools()
                content = wt.web_fetch(url)
                return content[:3000] + ("\n…[truncated]" if len(content) > 3000 else "")
            except Exception as e:
                return f"fetch error: {e}"

        if raw == "/quit":
            self._running = False
            return "Goodbye."

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

        return None  # not a slash command

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
                if best and (self.session.current_model in ("vector-fast", "vector-focus")
                             or not any(m["name"] == self.session.current_model
                                        for m in installed_models)):
                    self.session.current_model = best

        while self._running:
            try:
                raw = input("\n\x1b[96mvector\u276F\x1b[0m ").strip()
                if not raw:
                    continue

                # Slash commands and skill invocations
                if raw.startswith("/"):
                    result = self.handle_command(raw)
                    if result:
                        print(result)
                    continue

                # Route → pick best Ollama model
                model = self.router.route(raw)
                self.session.current_model = model

                # Auto-compact if history is getting large (5-stage pipeline)
                if _history_size(self._history) > _COMPRESS_THRESHOLD:
                    try:
                        from context.compactor import ContextCompactor
                        compactor = ContextCompactor(model=model, project_dir=self._project_dir)
                        self._history = compactor.compact(self._history)
                    except Exception:
                        # Fallback to old compressor
                        self._history = _compress_history(self._history, model)

                # Add user turn and stream response
                self._history.append({"role": "user", "content": raw})
                print()
                reply = _ask_ollama(model, self._history)
                self._history.append({"role": "assistant", "content": reply})
                self.session.history.append({"role": "user", "content": raw})
                # Approximate token count (4 chars ≈ 1 token)
                self.session.record_token_usage(
                    prompt=len(raw) // 4,
                    completion=len(reply) // 4,
                )

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
                )
                _save_trajectory(self._history, self.session.current_model)
            except Exception:
                pass
            try:
                from context.session_memory import update_session_memory
                update_session_memory(self._history)
            except Exception:
                pass


# ── self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    repl = VectorREPL()
    assert repl.mode == "repl"
    assert hasattr(repl, "session")
    assert hasattr(repl, "gsd")
    assert "/help" in repl.COMMANDS
    assert "/status" in repl.COMMANDS
    repl.handle_command("/mode auto")
    assert repl.session.mode == "auto"
    status = repl.get_status()
    assert "mode" in status and "model" in status and "hp" in status
    print("repl.py OK")





