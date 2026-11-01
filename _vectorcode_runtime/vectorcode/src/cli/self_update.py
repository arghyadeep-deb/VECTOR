# Ported from GitHub/VectorCode_vectorcode/repo/vector_cli/setup.py (self-update)
"""vector self-update — upgrade VectorCode from PyPI."""
import importlib.metadata
import subprocess
import sys
from typing import Optional

def get_current_version() -> str:
    try:
        return importlib.metadata.version("vectorcode")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0-dev"

def get_latest_pypi_version() -> Optional[str]:
    try:
        import httpx
        r = httpx.get("https://pypi.org/pypi/vectorcode/json", timeout=10)
        r.raise_for_status()
        return r.json()["info"]["version"]
    except Exception:
        return None

def self_update(docker: bool = False) -> int:
    """Upgrade VectorCode to the latest version."""
    current = get_current_version()
    print(f"Current version: {current}")

    if docker:
        print("Pulling latest Docker image...")
        return subprocess.call(["docker", "pull", "ghcr.io/arghyadeep/vectorcode:latest"])

    latest = get_latest_pypi_version()
    if latest is None:
        print("[VECTOR] Could not check PyPI — upgrading anyway")
    elif current == latest:
        print(f"[VECTOR] Already up to date ({current})")
        return 0
    else:
        print(f"[VECTOR] Upgrading {current} -> {latest}")

    return subprocess.call([sys.executable, "-m", "pip", "install", "--upgrade", "vectorcode"])
