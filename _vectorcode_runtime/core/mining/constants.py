"""Constants for the Pearl mining subsystem.

Pinned Pearl ref OJ has tested against. Bumped per OJ release after
re-testing the integration end-to-end on a real H100/H200 host. See
spec ``docs/design/2026-05-05-vllm-pearl-mining-integration-design.md``
section 7.3 for the rev-bump workflow.
"""

from __future__ import annotations

__all__ = [
    "CPU_PEARL_DEFAULT_COLS_PATTERN",
    "CPU_PEARL_DEFAULT_K",
    "CPU_PEARL_DEFAULT_M",
    "CPU_PEARL_DEFAULT_N",
    "CPU_PEARL_DEFAULT_RANK",
    "CPU_PEARL_DEFAULT_ROWS_PATTERN",
    "DEFAULT_GATEWAY_METRICS_PORT",
    "DEFAULT_GATEWAY_RPC_PORT",
    "DEFAULT_PEARL_MODEL",
    "DEFAULT_PEARLD_RPC_URL",
    "DEFAULT_VLLM_PORT",
    "MIN_FREE_DISK_GB",
    "PEARL_CACHE_DIR",
    "PEARL_CPU_PACKAGES",
    "PEARL_IMAGE_TAG",
    "PEARL_PINNED_REF",
    "PEARL_REPO",
    "RUNTIME_DIR",
    "SIDECAR_LOCK_PATH",
    "SIDECAR_PATH",
]


from pathlib import Path

PEARL_REPO = "https://github.com/pearl-research-labs/pearl.git"
PEARL_PINNED_REF = "master"
PEARL_IMAGE_TAG = f"vector/pearl-miner:{PEARL_PINNED_REF}"

DEFAULT_PEARL_MODEL = "pearl-ai/Llama-3.3-70B-Instruct-pearl"

DEFAULT_VLLM_PORT = 8000
DEFAULT_GATEWAY_RPC_PORT = 8337
DEFAULT_GATEWAY_METRICS_PORT = 8339

CPU_PEARL_DEFAULT_M = 256
CPU_PEARL_DEFAULT_N = 128
CPU_PEARL_DEFAULT_K = 1024
CPU_PEARL_DEFAULT_RANK = 32
CPU_PEARL_DEFAULT_ROWS_PATTERN = (0, 8, 64, 72)
CPU_PEARL_DEFAULT_COLS_PATTERN = (0, 1, 8, 9, 32, 33, 40, 41)
PEARL_CPU_PACKAGES = (
    "py-pearl-mining",
    "miner-utils",
    "pearl-gateway",
    "miner-base",
)

DEFAULT_PEARLD_RPC_URL = "http://localhost:44107"

MIN_FREE_DISK_GB = 200

RUNTIME_DIR = Path.home() / ".vector" / "runtime"
SIDECAR_PATH = RUNTIME_DIR / "mining.json"
SIDECAR_LOCK_PATH = RUNTIME_DIR / "mining.lock"

PEARL_CACHE_DIR = Path.home() / ".vector" / "cache" / "pearl"
