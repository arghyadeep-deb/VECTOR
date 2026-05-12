"""VectorREPL — VectorCode VC-4 Mode A. Blocking terminal REPL."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from loguru import logger
from agents.districts.coding.vectorcode.session import VectorCodeSession
from agents.districts.coding.vectorcode.gsd_loop import GSDLoop


class VectorREPL:
    """Mode A: interactive terminal REPL sharing VectorCodeSession state."""

    mode = "repl"

    COMMANDS = {
        "/help":   "Show available commands",
        "/status": "Show current session status",
        "/mode":   "Switch interaction mode (/mode auto|repl|hybrid)",
        "/quit":   "Exit the REPL",
        "/reset":  "Reset session history",
    }

    def __init__(self) -> None:
        self.session = VectorCodeSession.get()
        self.session.set_mode("repl")
        self.gsd = GSDLoop(mode="repl")
        self._running = False
        logger.info("[VECTOR][repl] VectorREPL initialised")

    def handle_command(self, raw: str) -> str:
        """Dispatch a slash command or task string. Returns response text."""
        raw = raw.strip()
        if raw.startswith("/mode"):
            parts = raw.split(maxsplit=1)
            new_mode = parts[1].strip() if len(parts) > 1 else ""
            try:
                self.session.set_mode(new_mode)
                return f"Mode switched to '{new_mode}'"
            except ValueError as e:
                return str(e)
        if raw == "/help":
            return "\n".join(f"  {k}: {v}" for k, v in self.COMMANDS.items())
        if raw == "/status":
            return str(self.get_status())
        if raw == "/reset":
            self.session.reset()
            return "Session reset."
        if raw == "/quit":
            self._running = False
            return "Goodbye."
        # Non-command: treat as a task
        return f"[repl] Received task: {raw}"

    def get_status(self) -> dict:
        return {
            "mode":    self.session.mode,
            "model":   self.session.current_model,
            "hp":      500,
            "task_id": self.session.task_id,
            "history": len(self.session.history),
        }

    def run(self) -> None:
        """Blocking REPL loop. Exits on /quit or KeyboardInterrupt."""
        self._running = True
        print("VectorREPL ready. Type /help for commands.")
        while self._running:
            try:
                raw = input("vector> ").strip()
                if not raw:
                    continue
                response = self.handle_command(raw)
                print(response)
            except (KeyboardInterrupt, EOFError):
                break
        logger.info("[VECTOR][repl] REPL exited")


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
