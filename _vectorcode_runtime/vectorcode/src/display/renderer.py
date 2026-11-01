"""Central display renderer — coordinates spinner, diff preview, and output."""
import sys
import io
from pathlib import Path
from typing import Optional


# Re-wrap stdout/stderr as UTF-8 on Windows so emoji/box-drawing output works
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

from loguru import logger

from vectorcode.display.spinner import VectorSpinner, get_tool_emoji, get_tool_message
from vectorcode.display.diff_preview import (
    build_tool_preview,
    diff_stats,
    render_diff,
    format_tool_result,
)

# ---------------------------------------------------------------------------
# ANSI shortcuts (kept local so renderer.py has no circular imports)
# ---------------------------------------------------------------------------
_RED   = "\x1b[31m"
_GREEN = "\x1b[32m"
_CYAN  = "\x1b[36m"
_DIM   = "\x1b[2m"
_BOLD  = "\x1b[1m"
_RESET = "\x1b[0m"

# Tools that mutate files and should trigger diff preview
_FILE_MUTATING_TOOLS = {"write_file", "edit_file"}

# Tools where we should snapshot the file *before* execution
_SNAPSHOT_BEFORE_TOOLS = {"write_file", "edit_file"}


class VectorRenderer:
    """
    Stateful renderer for a VectorCode session.

    - Tracks file snapshots for diff preview
    - Controls spinner lifecycle
    - Formats final responses and tool call summaries
    """

    def __init__(self, *, use_color: bool = True, verbose: bool = False) -> None:
        self.use_color = use_color
        self.verbose = verbose
        self._file_snapshots: dict[str, str] = {}      # path → content before edit
        self._current_spinner: Optional[VectorSpinner] = None

    # ------------------------------------------------------------------
    # Tool lifecycle hooks — called by the agent/REPL harness
    # ------------------------------------------------------------------

    def on_tool_start(self, tool_name: str, args: dict) -> None:
        """Called before a tool executes. Starts spinner with appropriate message."""
        logger.debug(f"[VECTOR][renderer] tool_start: {tool_name}")

        # Snapshot file if needed (so we can diff after)
        if tool_name.lower() in _SNAPSHOT_BEFORE_TOOLS:
            path = args.get("path", args.get("file_path", args.get("filename", "")))
            if path:
                self.snapshot_file(str(path))

        message = get_tool_message(tool_name)
        self._stop_spinner()
        spinner = VectorSpinner(message=message, tool_name=tool_name)
        self._current_spinner = spinner
        spinner.start()

    def on_tool_end(self, tool_name: str, args: dict, result: str) -> None:
        """Called after a tool executes. Stops spinner and shows diff/preview."""
        logger.debug(f"[VECTOR][renderer] tool_end: {tool_name}")
        self._stop_spinner()

        if not self.verbose and tool_name.lower() not in _FILE_MUTATING_TOOLS:
            # Non-verbose: only show file mutations and errors
            if "error" in result.lower()[:120]:
                self.print_error(f"[{tool_name}] {result[:200]}")
            return

        # Verbose or file-mutating tool
        if tool_name.lower() in _FILE_MUTATING_TOOLS:
            path = args.get("path", args.get("file_path", args.get("filename", "")))
            if path:
                new_content = args.get("new_content", args.get("content", result or ""))
                self.show_diff(str(path), new_content)
            else:
                preview = build_tool_preview(tool_name, args, result)
                self._write(preview + "\n")
        elif self.verbose:
            preview = build_tool_preview(tool_name, args, result)
            self._write(preview + "\n")

    def on_response(self, text: str) -> None:
        """Print final assistant response with optional formatting."""
        self._stop_spinner()
        if not text:
            return
        if self.use_color:
            # Wrap in subtle bright-white — readable, not glaring
            self._write(f"\x1b[97m{text}{_RESET}\n")
        else:
            self._write(text + "\n")

    # ------------------------------------------------------------------
    # File snapshot & diff
    # ------------------------------------------------------------------

    def snapshot_file(self, path: str) -> None:
        """Save current file content for later diff. Call before write/edit."""
        try:
            p = Path(path)
            if p.exists() and p.is_file():
                self._file_snapshots[path] = p.read_text(encoding="utf-8", errors="replace")
                logger.debug(f"[VECTOR][renderer] snapshot saved: {path}")
            else:
                self._file_snapshots[path] = ""
        except OSError as exc:
            logger.warning(f"[VECTOR][renderer] snapshot failed for {path}: {exc}")
            self._file_snapshots[path] = ""

    def show_diff(self, path: str, new_content: str) -> None:
        """Show diff between the stored snapshot and *new_content*."""
        old_content = self._file_snapshots.get(path, "")
        stats = diff_stats(old_content, new_content)

        emoji = get_tool_emoji("write_file")
        header = (
            f"{_BOLD}{_CYAN}{emoji} {path}{_RESET}  "
            f"{_GREEN}+{stats.additions}{_RESET}  "
            f"{_RED}-{stats.deletions}{_RESET}"
        )
        self._write(header + "\n")

        diff_text = render_diff(old_content, new_content, filename=path)
        self._write(diff_text + "\n")

    # ------------------------------------------------------------------
    # Printing helpers
    # ------------------------------------------------------------------

    def print_tool_call(self, tool_name: str, args: dict) -> None:
        """Print a one-line summary of a tool call."""
        emoji = get_tool_emoji(tool_name)
        args_summary = ", ".join(
            f"{k}={str(v)[:40]}" for k, v in list(args.items())[:3]
        )
        line = f"{_DIM}{emoji} {tool_name}({args_summary}){_RESET}"
        self._write(line + "\n")

    def print_error(self, message: str) -> None:
        """Print error in red."""
        self._write(f"{_RED}{_BOLD}✖ {message}{_RESET}\n")

    def print_info(self, message: str) -> None:
        """Print info in dim/gray."""
        self._write(f"{_DIM}ℹ {message}{_RESET}\n")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _stop_spinner(self) -> None:
        if self._current_spinner is not None:
            self._current_spinner.stop()
            self._current_spinner = None

    def _write(self, text: str) -> None:
        """Write to stdout, stripping ANSI if color is disabled."""
        if not self.use_color:
            import re
            text = re.sub(r"\x1b\[[0-9;]*m", "", text)
        sys.stdout.write(text)
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_renderer_instance: Optional[VectorRenderer] = None


def get_renderer() -> VectorRenderer:
    """Return the process-level singleton VectorRenderer."""
    global _renderer_instance
    if _renderer_instance is None:
        _renderer_instance = VectorRenderer()
    return _renderer_instance


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("[VECTOR][renderer] smoke test starting")

    r = VectorRenderer(verbose=True)

    # Basic print helpers — must not crash
    r.print_info("test info message")
    r.print_error("test error message")
    r.on_response("Hello, I am VECTOR.")

    # Spinner via on_tool_start / on_tool_end
    import time
    r.on_tool_start("bash", {"command": "echo hello"})
    time.sleep(0.2)
    r.on_tool_end("bash", {"command": "echo hello"}, "hello")

    # Snapshot + diff flow
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write("x = 1\ny = 2\n")
        tmp_path = f.name

    try:
        r.snapshot_file(tmp_path)
        r.show_diff(tmp_path, "x = 1\ny = 99\n")
    finally:
        os.unlink(tmp_path)

    # Singleton
    a = get_renderer()
    b = get_renderer()
    assert a is b, "get_renderer() must return the same instance"

    sys.stdout.write("✅ renderer.py OK\n")
    sys.stdout.flush()
