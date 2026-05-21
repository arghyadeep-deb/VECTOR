#!/usr/bin/env python
"""VectorCode CLI launcher."""
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, Exception):
    logger.debug("[VECTOR] suppressed exception", exc_info=True)

sys.path.insert(0, str(Path(__file__).parent / "src"))

import importlib.util
_cli_path = Path(__file__).parent / "src" / "cli.py"
_spec = importlib.util.spec_from_file_location("vectorcode._cli_main", _cli_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
main = _mod.main

if __name__ == "__main__":
    main()
