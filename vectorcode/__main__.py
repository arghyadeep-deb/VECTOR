"""
VectorCode — terminal-native, model-agnostic agentic coding tool.
Run with: python -m vectorcode repl
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    import sys as _sys
    _sys.argv = _sys.argv[1:] if len(_sys.argv) > 1 and _sys.argv[0].endswith("__main__.py") else _sys.argv

    import importlib.util
    _cli_path = Path(__file__).parent / "src" / "cli.py"
    _spec = importlib.util.spec_from_file_location("vectorcode._cli_main", _cli_path)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _mod.main()
