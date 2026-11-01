"""Animated spinner with per-tool emoji and status messages."""
import sys
import threading
import time
import itertools
import random
from typing import Optional


from loguru import logger

TOOL_EMOJI = {
    "read_file":          "📖",
    "write_file":         "✏️",
    "edit_file":          "🔧",
    "bash":               "💻",
    "git_commit":         "📦",
    "git_diff":           "🔍",
    "git_status":         "📊",
    "web_search":         "🌐",
    "web_extract":        "🌍",
    "create_checkpoint":  "💾",
    "restore_checkpoint": "⏮️",
    "delegate_task":      "🤖",
    "memory_read":        "🧠",
    "memory_write":       "💭",
    "generate_image":     "🎨",
    "text_to_speech":     "🔊",
    "speech_to_text":     "🎤",
    "list_directory":     "📂",
    "search_files":       "🔎",
    "code_execution":     "⚡",
    "_default":           "⚙️",
}

TOOL_MESSAGES = {
    "read_file":   ["Reading file...", "Loading content...", "Scanning file..."],
    "write_file":  ["Writing file...", "Saving changes...", "Committing to disk..."],
    "edit_file":   ["Editing file...", "Applying changes...", "Patching content..."],
    "bash":        ["Running command...", "Executing shell...", "Processing..."],
    "web_search":  ["Searching the web...", "Looking it up...", "Fetching results..."],
    "web_extract": ["Fetching URL...", "Downloading page...", "Loading resource..."],
    "git_commit":  ["Committing changes...", "Saving to git...", "Recording snapshot..."],
    "git_diff":    ["Computing diff...", "Comparing versions...", "Analysing changes..."],
    "git_status":  ["Checking status...", "Reading git state...", "Scanning repo..."],
    "memory_read": ["Reading memory...", "Recalling context...", "Loading memories..."],
    "memory_write":["Saving memory...", "Persisting context...", "Storing thought..."],
    "delegate_task":["Delegating task...", "Spawning agent...", "Assigning work..."],
    "_default":    ["Working...", "Processing...", "Thinking..."],
}

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class VectorSpinner:
    """Thread-based spinner that writes to stderr."""

    def __init__(self, message: str = "Working...", tool_name: str = "") -> None:
        self.message = message
        self.tool_name = tool_name
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._frames = itertools.cycle(SPINNER_FRAMES)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> "VectorSpinner":
        """Start spinning. Returns self for context-manager use."""
        # Hide cursor
        sys.stderr.write("\x1b[?25l")
        sys.stderr.flush()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        logger.debug(f"[VECTOR][spinner] started — {self.tool_name or 'default'}")
        return self

    def stop(self, final_message: str = "") -> None:
        """Stop spinning and optionally print a final message."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        # Clear spinner line, restore cursor
        sys.stderr.write("\r\x1b[K\x1b[?25h")
        if final_message:
            sys.stderr.write(f"{final_message}\n")
        sys.stderr.flush()
        logger.debug("[VECTOR][spinner] stopped")

    def update(self, message: str, tool_name: str = "") -> None:
        """Update message and optional tool name while running."""
        with self._lock:
            self.message = message
            if tool_name:
                self.tool_name = tool_name

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _spin(self) -> None:
        while not self._stop_event.is_set():
            frame = next(self._frames)
            with self._lock:
                emoji = TOOL_EMOJI.get(self.tool_name, TOOL_EMOJI["_default"])
                msg = self.message
            line = f"\r\x1b[36m{frame}\x1b[0m {emoji} \x1b[2m{msg}\x1b[0m"
            sys.stderr.write(line)
            sys.stderr.flush()
            time.sleep(0.08)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "VectorSpinner":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def get_tool_emoji(tool_name: str) -> str:
    """Return the emoji associated with *tool_name*."""
    return TOOL_EMOJI.get(tool_name, TOOL_EMOJI["_default"])


def get_tool_message(tool_name: str) -> str:
    """Return a random status message for *tool_name*."""
    messages = TOOL_MESSAGES.get(tool_name, TOOL_MESSAGES["_default"])
    return random.choice(messages)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("[VECTOR][spinner] smoke test starting")

    spinner = VectorSpinner(message="Reading file...", tool_name="read_file")
    spinner.start()
    time.sleep(0.2)
    spinner.update("Writing file...", tool_name="write_file")
    time.sleep(0.2)
    spinner.stop(final_message="✅ spinner.py OK")

    # Context-manager form
    with VectorSpinner(message="bash running...", tool_name="bash"):
        time.sleep(0.2)

    # Helpers
    emoji = get_tool_emoji("git_commit")
    msg = get_tool_message("bash")
    assert emoji == "📦", f"Expected 📦, got {emoji}"
    assert msg in TOOL_MESSAGES["bash"], f"Unexpected message: {msg}"

    sys.stdout.buffer.write(b"\xe2\x9c\x85 spinner.py OK\n")
    sys.stdout.buffer.flush()
