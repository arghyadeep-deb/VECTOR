#!/usr/bin/env python
"""VectorCode CLI launcher."""
import sys
from pathlib import Path

# Add vectorcode/python to path so 'vectorcode' package is importable
sys.path.insert(0, str(Path(__file__).parent / "python"))
# Also add vectorcode/python/vectorcode so bare imports work inside cli.py
sys.path.insert(0, str(Path(__file__).parent / "python" / "vectorcode"))

# cli.py (the file) contains main() — import it directly to avoid
# collision with the cli/ package directory
import importlib.util
_cli_path = Path(__file__).parent / "python" / "vectorcode" / "cli.py"
_spec = importlib.util.spec_from_file_location("vectorcode._cli_main", _cli_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
main = _mod.main

if __name__ == "__main__":
    main()
