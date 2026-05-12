"""VECTOR — interactive coding REPL (Mode A). Hermes-inspired architecture."""
import sys
import json
import time
import threading
import itertools
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from loguru import logger
from agents.districts.coding.vectorcode.session import VectorCodeSession
from agents.districts.coding.vectorcode.router import SemanticRouter
from agents.districts.coding.vectorcode.gsd_loop import GSDLoop

# ── Paths ─────────────────────────────────────────────────────────────────────
_VECTOR_DIR   = Path.home() / ".vector"
_SESSION_DIR  = _VECTOR_DIR / "sessions"
_SOUL_PATH    = Path(__file__).parent.parent.parent.parent.parent / "brain" / "VECTOR" / "SOUL.md"
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

def _load_soul() -> str:
    if _SOUL_PATH.exists():
        try:
            return _SOUL_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return _DEFAULT_SOUL

def _build_system_prompt(skills_index: str = "") -> str:
    soul  = _load_soul()
    parts = [soul, _TOOL_ENFORCEMENT]
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
def _save_session(history: list, model: str) -> Path:
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    ts   = int(time.time())
    path = _SESSION_DIR / f"session_{ts}.json"
    payload = {"ts": ts, "model": model, "history": history}
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


# ── REPL ──────────────────────────────────────────────────────────────────────
class VectorREPL:
    """Mode A: interactive terminal REPL with streaming, skills, compression, persistence."""

    mode = "repl"

    COMMANDS = {
        "/help":    "Show commands",
        "/status":  "Session status",
        "/mode":    "/mode auto|repl|hybrid",
        "/model":   "/model <name>  — force a model",
        "/skills":  "List available skills",
        "/clear":   "Clear conversation history",
        "/save":    "Save session to disk",
        "/restore": "Restore last session",
        "/tools":   "List MCP tool categories",
        "/quit":    "Exit VECTOR",
    }

    def __init__(self) -> None:
        self.session  = VectorCodeSession.get()
        self.session.set_mode("repl")
        self.router   = SemanticRouter()
        self.gsd      = GSDLoop(mode="repl")
        self._skills  = _scan_skills()
        self._history = [{"role": "system",
                          "content": _build_system_prompt(_build_skills_index(self._skills))}]
        self._running = False

    # ── slash commands ────────────────────────────────────────────────────────

    def handle_command(self, raw: str) -> str | None:
        raw = raw.strip()

        if raw.startswith("/mode"):
            parts = raw.split(maxsplit=1)
            new_mode = parts[1].strip() if len(parts) > 1 else ""
            try:
                self.session.set_mode(new_mode)
                return f"Mode → {new_mode}"
            except ValueError as e:
                return str(e)

        if raw.startswith("/model"):
            parts = raw.split(maxsplit=1)
            if len(parts) > 1:
                self.session.current_model = parts[1].strip()
                return f"Model → {self.session.current_model}"
            return f"Current model: {self.session.current_model}"

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
            return (f"\n  mode     {s['mode']}\n  model    {s['model']}\n"
                    f"  history  {s['history']} turns\n  skills   {len(self._skills)}")

        if raw == "/skills":
            if not self._skills:
                return "No skills found in ~/.claude/skills/"
            return "  Skills:\n" + "\n".join(f"    /{s}" for s in sorted(self._skills))

        if raw == "/tools":
            cats = ["agent/swarm", "memory", "hook", "task", "security", "neural",
                    "file", "git", "test", "doc", "browser", "graph", "perf", "worker", "config"]
            return "  Tool categories: " + ", ".join(cats)

        if raw in ("/clear", "/reset"):
            self._history = [{"role": "system",
                               "content": _build_system_prompt(_build_skills_index(self._skills))}]
            self.session.reset()
            return "History cleared."

        if raw == "/save":
            path = _save_session(self._history, self.session.current_model)
            return f"Session saved → {path}"

        if raw == "/restore":
            sess = _load_last_session()
            if not sess:
                return "No saved sessions found."
            self._history = sess["history"]
            self.session.current_model = sess.get("model", self.session.current_model)
            import datetime
            ts = datetime.datetime.fromtimestamp(sess["ts"]).strftime("%Y-%m-%d %H:%M")
            return f"Restored session from {ts}  ({len(self._history)-1} turns)"

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

    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                raw = input("\nvector> ").strip()
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

                # Auto-compress if history is getting long
                if _history_size(self._history) > _COMPRESS_THRESHOLD:
                    self._history = _compress_history(self._history, model)

                # Add user turn and stream response
                self._history.append({"role": "user", "content": raw})
                print()
                reply = _ask_ollama(model, self._history)
                self._history.append({"role": "assistant", "content": reply})
                self.session.history.append({"role": "user", "content": raw})

            except (KeyboardInterrupt, EOFError):
                print("\nExiting VECTOR.")
                break

        # On exit: persist session + save trajectory for training
        if len(self._history) > 1:
            try:
                _save_session(self._history, self.session.current_model)
                _save_trajectory(self._history, self.session.current_model)
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
