# VECTOR module -- ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb

"""GPU capability detection -- standalone utilities for VECTOR telemetry.

Each function answers a single yes/no question and returns ``(ok: bool,
info: str)`` where ``info`` is human-readable.
"""

from __future__ import annotations

__all__ = [
    "check_disk_free",
    "check_docker_available",
    "detect_for_engine_model",
    "REQUIRED_COMPUTE_CAPABILITY",
    "REQUIRED_VRAM_GB",
    "SUPPORTED_VLLM_ENGINE_IDS",
]


import shutil
from pathlib import Path
from typing import Tuple

import httpx

from vectorcode.src.vc_core.config import HardwareInfo
from core.mining.models import get_pearl_model_spec, pearl_variant_for_base_model
from core.mining._abc import MiningCapabilities

REQUIRED_COMPUTE_CAPABILITY = "9.0"
REQUIRED_VRAM_GB = 70.0
SUPPORTED_VLLM_ENGINE_IDS = frozenset({"vllm"})

def detect_for_engine_model(
    *,
    hw: HardwareInfo,
    engine_id: str,
    model: str,
    provider_id: str,
) -> MiningCapabilities:
    """Check whether the given hardware/engine/model combo can run a GPU container.

    Pure inspection -- no subprocess, no Docker, no network.
    """
    if provider_id != "vllm-pearl":
        return MiningCapabilities(False, reason=f"unknown provider {provider_id!r}")

    if engine_id not in SUPPORTED_VLLM_ENGINE_IDS:
        return MiningCapabilities(
            False, reason=f"engine '{engine_id}' has no GPU plugin in v1; use vllm",
        )

    if hw.gpu is None:
        return MiningCapabilities(False, reason="no GPU detected")
    if hw.gpu.vendor != "nvidia":
        return MiningCapabilities(
            False, reason=f"GPU container launch requires NVIDIA; detected {hw.gpu.vendor!r}",
        )
    if not hw.gpu.compute_capability.startswith("9.0"):
        return MiningCapabilities(
            False, reason=f"needs compute_capability 9.0 (sm_90a / H100); "
            f"detected {hw.gpu.compute_capability!r} ({hw.gpu.name})",
        )
    spec = get_pearl_model_spec(model)
    required_vram_gb = spec.min_vram_gb if spec else REQUIRED_VRAM_GB
    if hw.gpu.vram_gb < required_vram_gb:
        return MiningCapabilities(
            False, reason=f"needs >= {required_vram_gb:.0f} GB VRAM for {model}; "
            f"detected {hw.gpu.vram_gb:.0f} GB",
        )

    pearl_variant = pearl_variant_for_base_model(model)
    if pearl_variant:
        return MiningCapabilities(
            False, reason=f"model {model!r} is a raw base model; "
            f"planned GPU variant is {pearl_variant!r}",
        )
    if spec is None:
        return MiningCapabilities(
            False, reason=f"model {model!r} is not in the GPU model registry",
        )
    if not spec.is_validated:
        return MiningCapabilities(
            False, reason=f"model {model!r} is {spec.status}; "
            "needs validation",
        )

    return MiningCapabilities(supported=True)

def _docker_client():
    try:
        import docker
    except ImportError as exc:
        raise RuntimeError(
            "Docker SDK not installed; install with `pip install docker`"
        ) from exc
    return docker.from_env()

def check_docker_available() -> Tuple[bool, str]:
    try:
        c = _docker_client()
        c.ping()
        ver = c.version().get("Version", "unknown")
        return True, f"running {ver}"
    except Exception as e:
        return False, str(e).splitlines()[0]

def check_disk_free(path: Path) -> Tuple[bool, str]:
    from core.mining.constants import MIN_FREE_DISK_GB
    usage = shutil.disk_usage(path)
    free_gb = usage.free / (1024 ** 3)
    if free_gb < MIN_FREE_DISK_GB:
        return False, f"only {free_gb:.0f} GB free (need >= {MIN_FREE_DISK_GB} GB)"
    return True, f"{free_gb:.0f} GB free"
