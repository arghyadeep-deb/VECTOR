"""
VectorCode — VECTOR's local coding agent.
Use `from vectorcode.src import X` for all imports.
"""
from vectorcode.src.bootstrap import ensure_paths

ensure_paths()


if __name__ == "__main__":
    assert callable(ensure_paths)
