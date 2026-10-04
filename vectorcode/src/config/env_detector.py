"""Detect runtime environment — Termux, WSL, Docker, bare Linux, Windows, macOS."""
import sys
import os
import shutil
import platform
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


try:
    from core.config import CONFIG  # noqa: F401
except Exception:
    CONFIG = {}

from loguru import logger


class Environment(Enum):
    """Enumeration of supported runtime environments."""

    WINDOWS   = "windows"
    MACOS     = "macos"
    LINUX     = "linux"
    WSL       = "wsl"
    DOCKER    = "docker"
    TERMUX    = "termux"
    CONTAINER = "container"   # generic OCI (Podman, LXC, etc.)


@dataclass
class EnvInfo:
    """Snapshot of the detected runtime environment and available capabilities."""

    environment: Environment
    is_container: bool
    has_gpu: bool
    has_docker: bool
    has_node: bool
    has_ollama: bool
    python_version: str
    platform_string: str

    def adjust_paths(self) -> dict[str, str]:
        """Return environment-appropriate paths for home, tmp, and vector_data."""
        home = str(Path.home())
        if self.environment == Environment.TERMUX:
            prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
            tmp = os.path.join(prefix, "tmp")
            vector_data = os.path.join(home, ".vector")
        elif self.environment in (Environment.DOCKER, Environment.CONTAINER):
            tmp = "/tmp"
            vector_data = os.environ.get("VECTOR_DATA", "/opt/vector/data")
        elif self.environment == Environment.WINDOWS:
            appdata = os.environ.get("APPDATA", home)
            tmp = os.environ.get("TEMP", os.path.join(home, "AppData", "Local", "Temp"))
            vector_data = os.path.join(appdata, "vector")
        else:
            # Linux / macOS / WSL
            tmp = "/tmp"
            vector_data = os.path.join(home, ".vector")
        return {
            "home": home,
            "tmp": tmp,
            "vector_data": vector_data,
        }


# ── Detection helpers ─────────────────────────────────────────────────────────

def _is_termux() -> bool:
    """True when running inside a Termux Android environment."""
    if os.environ.get("TERMUX_VERSION"):
        return True
    prefix = os.environ.get("PREFIX", "")
    return "com.termux/files/usr" in prefix


def _is_wsl() -> bool:
    """True when running inside WSL 1 or WSL 2."""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _is_docker() -> bool:
    """True when running inside a Docker container."""
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "r") as f:
            content = f.read()
            return "docker" in content
    except OSError:
        return False


def _is_container() -> bool:
    """True when running inside any OCI container (Docker, Podman, LXC, etc.)."""
    if _is_docker():
        return True
    if os.path.exists("/run/.containerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "r") as f:
            cgroup = f.read()
            return any(marker in cgroup for marker in ("docker", "podman", "/lxc/"))
    except OSError:
        return False


def _has_gpu() -> bool:
    """True when an NVIDIA GPU is accessible via nvidia-smi."""
    return shutil.which("nvidia-smi") is not None


def _has_docker_cli() -> bool:
    """True when the docker CLI is on PATH."""
    return shutil.which("docker") is not None


def _has_node() -> bool:
    """True when node.js is on PATH."""
    return shutil.which("node") is not None


def _has_ollama() -> bool:
    """True when ollama is on PATH or reachable at the default port."""
    if shutil.which("ollama") is not None:
        return True
    # Also probe the default Ollama API endpoint
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
        return True
    except Exception:
        return False


# ── Main detection function ────────────────────────────────────────────────────

def detect() -> EnvInfo:
    """Detect and return the current runtime EnvInfo (not cached)."""
    plat = platform.system().lower()
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    plat_str = platform.platform()

    is_cont = False
    env = Environment.LINUX  # default

    if plat == "windows":
        env = Environment.WINDOWS
    elif plat == "darwin":
        env = Environment.MACOS
    else:
        # Linux-family: check in specificity order
        if _is_termux():
            env = Environment.TERMUX
        elif _is_wsl():
            env = Environment.WSL
        elif _is_docker():
            env = Environment.DOCKER
            is_cont = True
        elif _is_container():
            env = Environment.CONTAINER
            is_cont = True
        else:
            env = Environment.LINUX

    info = EnvInfo(
        environment=env,
        is_container=is_cont,
        has_gpu=_has_gpu(),
        has_docker=_has_docker_cli(),
        has_node=_has_node(),
        has_ollama=_has_ollama(),
        python_version=py_ver,
        platform_string=plat_str,
    )
    logger.debug(
        f"[VECTOR][env_detector] detected: {env.value} "
        f"(gpu={info.has_gpu}, ollama={info.has_ollama}, node={info.has_node})"
    )
    return info


# ── Cached singleton ──────────────────────────────────────────────────────────

_cached: Optional[EnvInfo] = None


def get_env() -> EnvInfo:
    """Return a cached EnvInfo — calls detect() on first access."""
    global _cached
    if _cached is None:
        _cached = detect()
    return _cached


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    info = detect()
    assert isinstance(info.environment, Environment)
    assert info.python_version
    assert info.platform_string

    paths = info.adjust_paths()
    assert "home" in paths
    assert "tmp" in paths
    assert "vector_data" in paths

    # Cached call must return same object
    _ = get_env()
    cached = get_env()
    assert cached is get_env()  # same instance

    print(f"  environment   : {info.environment.value}")
    print(f"  python        : {info.python_version}")
    print(f"  has_gpu       : {info.has_gpu}")
    print(f"  has_ollama    : {info.has_ollama}")
    print(f"  has_node      : {info.has_node}")
    print(f"  has_docker    : {info.has_docker}")
    print(f"  paths         : {paths}")
    print("config/env_detector.py OK")
