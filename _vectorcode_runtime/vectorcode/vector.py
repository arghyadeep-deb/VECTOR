#!/usr/bin/env python
"""VectorCode CLI launcher."""
from loguru import logger
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, Exception):
    logger.debug("[VECTOR] suppressed exception", exc_info=True)


import importlib.util
_cli_path = Path(__file__).parent / "src" / "cli.py"
_spec = importlib.util.spec_from_file_location("vectorcode._cli_main", _cli_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
main = _mod.main

if __name__ == "__main__":
    # Coding-session marker: tells a running VECTOR instance the owner is
    # actively coding in this terminal (project = os.getcwd()). VECTOR then
    # defers its heavy LLM ticks (shared single-model GPU) and arms proactive
    # stuck detection. Best-effort — never blocks or breaks the CLI.
    _clear_marker = None
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.sensing.stuck_detector import write_session_marker, clear_session_marker
        write_session_marker()
        _clear_marker = clear_session_marker
    except Exception:
        logger.debug("[VECTOR] session marker unavailable", exc_info=True)
    try:
        main()
    finally:
        try:
            if _clear_marker:
                _clear_marker()
        except Exception:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)
