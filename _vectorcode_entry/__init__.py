"""Private console entry point for the standalone VectorCode package.

This package intentionally imports only the standard library. The canonical
runtime is a sibling directory in built distributions and is added before
delegating to its existing module entry point.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def main() -> None:
    package_root = Path(__file__).resolve().parent.parent
    runtime_root = package_root / "_vectorcode_runtime"
    required_runtime_files = (
        runtime_root / "core" / "config.py",
        runtime_root / "vectorcode" / "vector.py",
    )
    missing = [path for path in required_runtime_files if not path.is_file()]
    if missing:
        missing_list = ", ".join(str(path) for path in missing)
        raise RuntimeError(
            "VectorCode private runtime is incomplete; missing: " + missing_list
        )

    data_dir = Path(os.environ.setdefault(
        "VECTOR_DATA_DIR", str(Path.home() / ".vector" / "runtime")
    )).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("VECTOR_DB_PATH", str(data_dir / "vector_memory.db"))
    os.environ.setdefault("VECTOR_VAULT_PATH", str(Path.home() / ".vector" / "brain"))

    sys.path.insert(0, str(runtime_root))
    runpy.run_module("vectorcode.vector", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
