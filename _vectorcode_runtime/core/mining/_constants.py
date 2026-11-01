# Canonical source is constants.py (better docstrings).
# This file is a backward-compat re-export so existing imports keep working.
from core.mining.constants import *  # noqa: F401, F403
from core.mining.constants import (
    PEARL_REPO, PEARL_PINNED_REF, PEARL_IMAGE_TAG, DEFAULT_PEARL_MODEL,
    DEFAULT_VLLM_PORT, DEFAULT_GATEWAY_RPC_PORT, DEFAULT_GATEWAY_METRICS_PORT,
    CPU_PEARL_DEFAULT_M, CPU_PEARL_DEFAULT_N, CPU_PEARL_DEFAULT_K,
    CPU_PEARL_DEFAULT_RANK, CPU_PEARL_DEFAULT_ROWS_PATTERN,
    CPU_PEARL_DEFAULT_COLS_PATTERN, PEARL_CPU_PACKAGES,
    DEFAULT_PEARLD_RPC_URL, MIN_FREE_DISK_GB,
    RUNTIME_DIR, SIDECAR_PATH, SIDECAR_LOCK_PATH, PEARL_CACHE_DIR,
)
