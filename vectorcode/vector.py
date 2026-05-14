#!/usr/bin/env python
"""VectorCode CLI launcher."""
import sys
from pathlib import Path

# Force UTF-8 output on Windows (Python 3.7+) so Unicode UI chars don't crash
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, Exception):
    pass

# Add vectorcode/python to path
sys.path.insert(0, str(Path(__file__).parent / "python"))
sys.path.insert(0, str(Path(__file__).parent / "python" / "vectorcode"))

# cli.py (file) contains main() — load via importlib to avoid cli/ package collision
import importlib.util
_cli_path = Path(__file__).parent / "python" / "vectorcode" / "cli.py"
_spec = importlib.util.spec_from_file_location("vectorcode._cli_main", _cli_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
main = _mod.main

if __name__ == "__main__":
    main()
