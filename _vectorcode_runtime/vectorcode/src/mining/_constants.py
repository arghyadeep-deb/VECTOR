"""VECTOR mining constants."""
from pathlib import Path

DEFAULT_GATEWAY_RPC_PORT: int = 8765
DEFAULT_GATEWAY_METRICS_PORT: int = 8766
DEFAULT_PEARLD_RPC_URL: str = "http://127.0.0.1:9999"
SIDECAR_PATH: Path = Path.home() / ".vector" / "mining" / "sidecar.json"
CPU_PEARL_DEFAULT_M: int = 256
CPU_PEARL_DEFAULT_N: int = 256
CPU_PEARL_DEFAULT_K: int = 32
CPU_PEARL_DEFAULT_RANK: int = 4

MIN_FREE_DISK_GB: float = 2.0
PEARL_IMAGE_TAG: str = "pearl-mining:latest"
PEARL_PINNED_REF: str = "master"
PEARL_REPO: str = "https://github.com/vectorcode/pearl-mining.git"
PEARL_CACHE_DIR = Path.home() / ".vector" / "mining" / "cache"
DEFAULT_PEARL_MODEL: str = "pearl-3"

