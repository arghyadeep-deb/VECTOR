# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Re-fixed imports: 2026-05-15

"""Telemetry — SQLite-backed inference recording, energy measurement,
FLOPs/MFU estimation, and instrumented model wrappers.

Provides energy-per-token, intelligence-per-watt, and steady-state
detection metrics used by VECTOR to measure and optimize itself.
"""

from __future__ import annotations

# Core aggregation + storage (always available)
from core.telemetry.aggregator import (
    AggregatedStats,
    EngineStats,
    ModelStats,
    TelemetryAggregator,
)
from core.telemetry.store import TelemetryStore
from core.telemetry.batch import BatchMetrics, EnergyBatch
from core.telemetry.steady_state import (
    SteadyStateConfig,
    SteadyStateDetector,
    SteadyStateResult,
)

# Optional: GPU monitor (requires nvidia-ml-py / pyamdgpuinfo)
try:
    from core.telemetry.gpu_monitor import (
        GpuHardwareSpec,
        GpuMonitor,
        GpuSample,
        GpuSnapshot,
    )
    _HAS_GPU = True
except ImportError:
    _HAS_GPU = False

# Optional: Efficiency / Intelligence-Per-Watt
try:
    from core.telemetry.efficiency import EfficiencyMetrics, compute_efficiency
    _HAS_EFFICIENCY = True
except ImportError:
    _HAS_EFFICIENCY = False

# Optional: vLLM metrics scraper
try:
    from core.telemetry.vllm_metrics import VLLMMetrics, VLLMMetricsScraper
    _HAS_VLLM = True
except ImportError:
    _HAS_VLLM = False

# Energy monitor (vendor-aware factory — always importable, vendor adapters lazy-loaded)
try:
    from core.telemetry.energy_monitor import (
        EnergyMonitor,
        EnergySample,
        EnergyVendor,
        create_energy_monitor,
    )
    _HAS_ENERGY = True
except ImportError:
    _HAS_ENERGY = False

# Optional: TelemetrySession + TelemetrySample (requires events bus)
try:
    from core.telemetry.session import TelemetrySample, TelemetrySession
    _HAS_SESSION = True
except ImportError:
    _HAS_SESSION = False

# Optional: phase metrics + ITL
try:
    from core.telemetry.phase_metrics import compute_phase_metrics, split_at_ttft
except ImportError:
    __import__("logging").getLogger(__name__).warning("optional dep import failed", exc_info=True)
try:
    from core.telemetry.itl import compute_itl_stats
except ImportError:
    __import__("logging").getLogger(__name__).warning("optional dep import failed", exc_info=True)
# FLOPs / MFU estimation
try:
    from core.telemetry.flops import (
        GPU_PEAK_TFLOPS_BF16,
        MODEL_PARAMS_B,
        compute_mfu,
        estimate_flops,
        estimate_flops_no_kv_cache,
    )
    _HAS_FLOPS = True
except ImportError:
    _HAS_FLOPS = False

# Instrumented wrapper (depends on oj_core events bus)
try:
    from core.telemetry.wrapper import instrumented_generate
    _HAS_WRAPPER = True
except ImportError:
    _HAS_WRAPPER = False

# ── Public capability flags ─────────────────────────────────────────────────

def capabilities() -> dict[str, bool]:
    """Return a dict of which telemetry subsystems are available on this host.

    Useful for the doctor command and the dashboard to show what's wired up.
    """
    return {
        "gpu_monitor":     _HAS_GPU,
        "efficiency":      _HAS_EFFICIENCY,
        "vllm_metrics":    _HAS_VLLM,
        "energy_monitor":  _HAS_ENERGY,
        "session":         _HAS_SESSION,
        "flops":           _HAS_FLOPS,
        "instrumented":    _HAS_WRAPPER,
    }

__all__ = [
    # Always-available
    "AggregatedStats",
    "BatchMetrics",
    "EnergyBatch",
    "EngineStats",
    "ModelStats",
    "SteadyStateConfig",
    "SteadyStateDetector",
    "SteadyStateResult",
    "TelemetryAggregator",
    "TelemetryStore",
    "capabilities",
]

# Conditionally-exported symbols (populated only if their try/except above succeeded)
if _HAS_GPU:
    __all__ += ["GpuHardwareSpec", "GpuMonitor", "GpuSample", "GpuSnapshot"]
if _HAS_EFFICIENCY:
    __all__ += ["EfficiencyMetrics", "compute_efficiency"]
if _HAS_VLLM:
    __all__ += ["VLLMMetrics", "VLLMMetricsScraper"]
if _HAS_ENERGY:
    __all__ += ["EnergyMonitor", "EnergySample", "EnergyVendor", "create_energy_monitor"]
if _HAS_SESSION:
    __all__ += ["TelemetrySample", "TelemetrySession"]
if _HAS_FLOPS:
    __all__ += [
        "GPU_PEAK_TFLOPS_BF16", "MODEL_PARAMS_B",
        "compute_mfu", "estimate_flops", "estimate_flops_no_kv_cache",
    ]
if _HAS_WRAPPER:
    __all__ += ["instrumented_generate"]
