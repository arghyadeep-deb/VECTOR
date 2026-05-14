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
    from python.vectorcode.cli import main
    main()
