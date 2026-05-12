"""VECTOR — interactive coding REPL (Mode A)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from loguru import logger
from agents.districts.coding.vectorcode.session import VectorCodeSession
from agents.districts.coding.vectorcode.router import SemanticRouter
from agents.districts.coding.vectorcode.gsd_loop import GSDLoop


def _ask_ollama(model: str, messages: list) -> str:
    """Call Ollama and stream the response, printing tokens as they arrive."""
    import ollama
    full = []
    try:
        stream = ollama.chat(model=model, messages=messages, stream=True)
        for chunk in stream:
            token = chunk["message"]["content"]
            print(token, end="", flush=True)
            full.append(token)
        print()  # newline after stream ends
    except Exception as e:
        msg = f"[VECTOR] Ollama error ({model}): {e}\nIs Ollama running? Try: ollama serve"
        print(msg)
        return msg
    return "".join(full)


_SYSTEM_PROMPT = """\
You are VECTOR — a Darwinian multi-agent coding AI running locally on Arghyadeep's Legion Pro 5.
You are in VectorCode Mode A (interactive REPL). You help with coding tasks, architecture, debugging,
and anything in the VECTOR codebase. Be concise and direct. No filler phrases.
When showing code, use markdown fences. You have access to file tools, bash tools, code graph,
browser automation, and 300+ MCP tools across 16 categories."""


class VectorREPL:
    """Mode A: interactive terminal REPL with live Ollama streaming."""

    mode = "repl"

    COMMANDS = {
        "/help":    "Show available commands",
        "/status":  "Show session status",
        "/mode":    "Switch mode: /mode auto|repl|hybrid",
        "/model":   "Show or set model: /model vector-coder",
        "/clear":   "Clear conversation history",
        "/reset":   "Reset session",
        "/tools":   "List available tool categories",
        "/quit":    "Exit VECTOR",
    }

    def __init__(self) -> None:
        self.session = VectorCodeSession.get()
        self.session.set_mode("repl")
        self.router = SemanticRouter()
        self.gsd = GSDLoop(mode="repl")
        self._history = [{"role": "system", "content": _SYSTEM_PROMPT}]
        self._running = False

    def _current_model(self) -> str:
        return self.session.current_model

    def handle_command(self, raw: str) -> str:
        """Handle slash commands. Returns response string (not printed here)."""
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
                lines.append(f"    {k:<12} {v}")
            return "\n".join(lines)

        if raw == "/status":
            s = self.get_status()
            return (f"\n  mode    {s['mode']}\n  model   {s['model']}\n"
                    f"  history {s['history']} turns\n  task    {s['task_id'] or 'none'}")

        if raw == "/tools":
            cats = ["agent/swarm", "memory", "hook", "task", "security", "neural",
                    "file", "git", "test", "doc", "browser", "graph", "perf", "worker", "config"]
            return "  Tool categories: " + ", ".join(cats)

        if raw in ("/clear", "/reset"):
            self._history = [{"role": "system", "content": _SYSTEM_PROMPT}]
            self.session.reset()
            return "History cleared."

        if raw == "/quit":
            self._running = False
            return "Goodbye."

        return None  # not a slash command

    def get_status(self) -> dict:
        return {
            "mode":    self.session.mode,
            "model":   self.session.current_model,
            "hp":      500,
            "task_id": self.session.task_id,
            "history": max(0, len(self._history) - 1),
        }

    def run(self) -> None:
        """Blocking REPL loop with streaming LLM responses."""
        self._running = True
        while self._running:
            try:
                raw = input("\nvector> ").strip()
                if not raw:
                    continue

                # Slash commands
                if raw.startswith("/"):
                    result = self.handle_command(raw)
                    if result:
                        print(result)
                    continue

                # Route to best model, update session
                model = self.router.route(raw)
                self.session.current_model = model

                # Add user message to history
                self._history.append({"role": "user", "content": raw})

                # Stream response
                print(f"\n\033[2m[{model}]\033[0m ", end="", flush=True)
                reply = _ask_ollama(model, self._history)

                # Keep history for context
                self._history.append({"role": "assistant", "content": reply})
                self.session.history.append({"role": "user", "content": raw})

            except (KeyboardInterrupt, EOFError):
                print("\nExiting VECTOR.")
                break


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
