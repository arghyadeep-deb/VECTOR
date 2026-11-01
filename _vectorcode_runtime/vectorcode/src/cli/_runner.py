"""vectorcode/src/cli/_runner.py — re-exports from _commands for backward compat."""
from ._commands import main, _run_ipc, _print_hud_banner, _strip_ansi  # noqa: F401
__all__ = ["main", "_run_ipc", "_print_hud_banner", "_strip_ansi"]
